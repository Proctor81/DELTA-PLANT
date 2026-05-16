from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

from nasa_delta_plant.utils.sentinel_client import SentinelClient, SentinelProduct


def test_sentinel_fetch_offloads_safe_parsing(monkeypatch):
    client = SentinelClient.__new__(SentinelClient)
    product = SentinelProduct(
        product_id="product-1",
        name="S1_TEST_PRODUCT",
        start_time=datetime(2026, 4, 30, tzinfo=timezone.utc),
        end_time=datetime(2026, 4, 30, 0, 6, tzinfo=timezone.utc),
        footprint_wkt="POINT (9.19 45.46)",
        orbit_direction="ASCENDING",
        polarization="VV,VH",
        download_url="https://example.invalid/product.zip",
    )

    async def fake_search_sentinel1(geo_data, start, end, max_results=2):
        return [product]

    async def fake_download_product(item):
        return b"zip-bytes"

    recorded_calls: list[tuple[object, tuple[object, ...]]] = []

    async def fake_to_thread(func, *args, **kwargs):
        recorded_calls.append((func, args))
        return func(*args, **kwargs)

    def fake_parse_safe_bundle(item, payload):
        return SimpleNamespace(product=SimpleNamespace(as_dict=lambda: {"name": item.name}), channels={}, annotation={})

    client.search_sentinel1 = fake_search_sentinel1
    client.download_product = fake_download_product
    client._parse_safe_bundle = fake_parse_safe_bundle
    monkeypatch.setattr(asyncio, "to_thread", fake_to_thread)

    result = asyncio.run(
        client.fetch(
            geo_data={"type": "circle", "center": {"lat": 45.46, "lng": 9.19}, "radius": 250.0},
            start=datetime(2026, 4, 1, tzinfo=timezone.utc).date(),
            end=datetime(2026, 4, 30, tzinfo=timezone.utc).date(),
            max_results=1,
        )
    )

    assert recorded_calls == [(fake_parse_safe_bundle, (product, b"zip-bytes"))]
    assert result["primary"].product.as_dict()["name"] == "S1_TEST_PRODUCT"
    assert result["secondary"] is None