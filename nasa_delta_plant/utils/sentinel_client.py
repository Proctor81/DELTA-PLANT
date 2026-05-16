"""Copernicus Dataspace Sentinel-1 client with token refresh and SAFE parsing."""

from __future__ import annotations

import asyncio
import re
import zipfile
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

import httpx
import numpy as np
from shapely.geometry import Point, shape

from nasa_delta_plant.config import Settings, get_settings


COPERNICUS_TOKEN_URL = "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"
COPERNICUS_CATALOG_URL = "https://catalogue.dataspace.copernicus.eu/odata/v1/Products"
COPERNICUS_ZIPPER_URL = "https://zipper.dataspace.copernicus.eu/odata/v1/Products({product_id})/$value"
MEASUREMENT_PATTERN = re.compile(r"measurement/.*-(hh|hv|vh|vv)-.*\.tiff?$", re.IGNORECASE)


@dataclass(slots=True)
class SentinelProduct:
    product_id: str
    name: str
    start_time: datetime
    end_time: datetime
    footprint_wkt: str
    orbit_direction: str | None
    polarization: str | None
    download_url: str

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["start_time"] = self.start_time.isoformat()
        payload["end_time"] = self.end_time.isoformat()
        return payload


@dataclass(slots=True)
class SentinelRasterBundle:
    product: SentinelProduct
    channels: dict[str, np.ndarray]
    annotation: dict[str, Any]


class SentinelClient:
    """Async Copernicus Dataspace client with OAuth token refresh."""

    def __init__(self, settings: Settings | None = None, timeout: float = 120.0) -> None:
        self.settings = settings or get_settings()
        self.timeout = timeout
        self._access_token: str | None = None
        self._token_expiry: datetime = datetime.now(timezone.utc)
        self._lock = asyncio.Lock()

    async def _ensure_access_token(self) -> str:
        if self._access_token and datetime.now(timezone.utc) < (self._token_expiry - timedelta(seconds=90)):
            return self._access_token

        async with self._lock:
            if self._access_token and datetime.now(timezone.utc) < (self._token_expiry - timedelta(seconds=90)):
                return self._access_token

            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    COPERNICUS_TOKEN_URL,
                    data={
                        "client_id": "cdse-public",
                        "grant_type": "password",
                        "username": self.settings.copernicus_username,
                        "password": self.settings.copernicus_password.get_secret_value(),
                    },
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )
                response.raise_for_status()
                payload = response.json()

            expires_in = int(payload.get("expires_in", 600))
            self._access_token = str(payload["access_token"])
            self._token_expiry = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
            return self._access_token

    async def search_sentinel1(
        self,
        geo_data: dict,
        start: date,
        end: date,
        max_results: int = 2,
    ) -> list[SentinelProduct]:
        token = await self._ensure_access_token()
        geometry_wkt = self._geometry_to_wkt(geo_data)
        filter_query = " and ".join(
            [
                "Collection/Name eq 'SENTINEL-1'",
                f"ContentDate/Start ge {start.isoformat()}T00:00:00.000Z",
                f"ContentDate/Start le {end.isoformat()}T23:59:59.999Z",
                f"OData.CSC.Intersects(area=geography'SRID=4326;{geometry_wkt}')",
            ]
        )

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(
                COPERNICUS_CATALOG_URL,
                params={
                    "$filter": filter_query,
                    "$orderby": "ContentDate/Start desc",
                    "$top": str(max_results),
                },
                headers={"Authorization": f"Bearer {token}"},
            )
            response.raise_for_status()
            payload = response.json()

        products: list[SentinelProduct] = []
        for item in payload.get("value", []):
            attributes = {entry.get("Name"): entry.get("Value") for entry in item.get("Attributes", [])}
            products.append(
                SentinelProduct(
                    product_id=str(item["Id"]),
                    name=str(item["Name"]),
                    start_time=datetime.fromisoformat(item["ContentDate"]["Start"].replace("Z", "+00:00")),
                    end_time=datetime.fromisoformat(item["ContentDate"]["End"].replace("Z", "+00:00")),
                    footprint_wkt=str(item.get("Footprint") or geometry_wkt),
                    orbit_direction=attributes.get("orbitDirection"),
                    polarization=attributes.get("polarisationChannels"),
                    download_url=COPERNICUS_ZIPPER_URL.format(product_id=item["Id"]),
                )
            )
        return products

    async def fetch(
        self,
        geo_data: dict,
        start: date,
        end: date,
        max_results: int = 2,
    ) -> dict[str, Any]:
        products = await self.search_sentinel1(geo_data, start, end, max_results=max_results)
        if not products:
            raise LookupError("No Sentinel-1 scenes found for the requested area and time range.")

        bundles: list[SentinelRasterBundle] = []
        for product in products:
            product_bytes = await self.download_product(product)
            bundles.append(self._parse_safe_bundle(product, product_bytes))

        return {
            "source": "Sentinel-1",
            "primary": bundles[0],
            "secondary": bundles[1] if len(bundles) > 1 else None,
            "products": [bundle.product.as_dict() for bundle in bundles],
        }

    async def download_product(self, product: SentinelProduct) -> bytes:
        token = await self._ensure_access_token()
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(product.download_url, headers={"Authorization": f"Bearer {token}"})
            if response.status_code == 401:
                token = await self._ensure_access_token()
                response = await client.get(product.download_url, headers={"Authorization": f"Bearer {token}"})
            response.raise_for_status()
            return response.content

    def _parse_safe_bundle(self, product: SentinelProduct, product_bytes: bytes) -> SentinelRasterBundle:
        try:
            import tifffile  # type: ignore
        except ImportError as exc:  # pragma: no cover - runtime dependency check
            raise RuntimeError("tifffile is required to parse Sentinel-1 SAFE products.") from exc

        channels: dict[str, np.ndarray] = {}
        annotation: dict[str, Any] = {}
        archive = zipfile.ZipFile(BytesIO(product_bytes))

        for member in archive.namelist():
            match = MEASUREMENT_PATTERN.search(member)
            if not match:
                continue
            channel = match.group(1).upper()
            with archive.open(member) as handle:
                array = tifffile.imread(handle)
            channels[channel] = self._downsample(np.asarray(array, dtype=np.float32))

        for member in archive.namelist():
            if not member.lower().endswith(".xml") or "annotation/" not in member.lower():
                continue
            if not any(pol.lower() in Path(member).name.lower() for pol in channels):
                continue
            with archive.open(member) as handle:
                annotation[Path(member).name] = self._parse_annotation_xml(handle.read())

        if not channels:
            raise RuntimeError(f"SAFE archive {product.name} did not expose measurement TIFF bands.")

        return SentinelRasterBundle(product=product, channels=channels, annotation=annotation)

    @staticmethod
    def _downsample(array: np.ndarray, max_size: int = 1024) -> np.ndarray:
        if array.ndim != 2:
            return np.squeeze(array)
        factor = max(int(max(array.shape) / max_size), 1)
        if factor == 1:
            return array
        return array[::factor, ::factor]

    @staticmethod
    def _parse_annotation_xml(xml_bytes: bytes) -> dict[str, Any]:
        root = ET.fromstring(xml_bytes)
        parsed: dict[str, Any] = {}
        for tag in ("missionId", "swath", "polarisation", "pass", "absoluteOrbitNumber"):
            element = root.find(f".//{tag}")
            if element is not None and element.text:
                parsed[tag] = element.text.strip()
        return parsed

    @staticmethod
    def _geometry_to_wkt(geo_data: dict) -> str:
        geo_type = str(geo_data.get("type", "")).lower()
        if geo_type == "circle":
            center = geo_data.get("center") or {}
            lon = float(center.get("lng", center.get("lon")))
            lat = float(center.get("lat"))
            radius_m = float(geo_data.get("radius", 0.0))
            degrees = max(radius_m / 111_320.0, 0.0001)
            geometry = Point(lon, lat).buffer(degrees, resolution=48)
            return geometry.wkt

        if "geojson" in geo_data:
            geometry = shape(geo_data["geojson"].get("geometry", geo_data["geojson"]))
            return geometry.wkt

        raise ValueError("Unsupported geo_data payload for Sentinel search.")