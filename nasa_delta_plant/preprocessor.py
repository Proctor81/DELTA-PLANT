"""SAR preprocessing pipeline for NASA DeltaPlant."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

import numpy as np

from nasa_delta_plant.utils.sentinel_client import SentinelRasterBundle


EPSILON = 1e-8
SENTINEL_1_WAVELENGTH_METERS = 0.0555


@dataclass(slots=True)
class PolarimetricProducts:
    pauli_rgb: dict[str, np.ndarray]
    freeman_durden: dict[str, np.ndarray]
    yamaguchi_4c: dict[str, np.ndarray]
    cloude_pottier: dict[str, np.ndarray]
    mode: str


@dataclass(slots=True)
class InSARProducts:
    coherence: np.ndarray
    phase_unwrapped: np.ndarray
    displacement_m: np.ndarray
    temporal_baseline_days: float


@dataclass(slots=True)
class ProcessedSARData:
    source: str
    acquisition_time: str
    backscatter_db: dict[str, np.ndarray]
    filtered_linear: dict[str, np.ndarray]
    polarimetric: PolarimetricProducts
    insar: InSARProducts | None
    soil_moisture_grid: np.ndarray
    soil_moisture_sample_points: np.ndarray
    soil_moisture_sample_values: np.ndarray
    metadata: dict[str, Any]


class SARPreprocessor:
    """Preprocess Sentinel SAR data into analytic products."""

    def preprocess(
        self,
        primary: SentinelRasterBundle,
        secondary: SentinelRasterBundle | None = None,
    ) -> ProcessedSARData:
        calibrated = {name: self._radiometric_calibration(channel) for name, channel in primary.channels.items()}
        filtered = {name: self._lee_filter(power) for name, power in calibrated.items()}
        backscatter_db = {name: 10.0 * np.log10(np.maximum(power, EPSILON)) for name, power in filtered.items()}

        hh, hv, vv, mode = self._coerce_polarimetric_channels(primary.channels)
        pauli_rgb = self._pauli_decomposition(hh, hv, vv)
        freeman_durden = self._freeman_durden(hh, hv, vv)
        yamaguchi_4c = self._yamaguchi_4c(hh, hv, vv)
        cloude_pottier = self._cloude_pottier(hh, hv, vv)
        polarimetric = PolarimetricProducts(
            pauli_rgb=pauli_rgb,
            freeman_durden=freeman_durden,
            yamaguchi_4c=yamaguchi_4c,
            cloude_pottier=cloude_pottier,
            mode=mode,
        )

        primary_channel_name = "VV" if "VV" in filtered else next(iter(filtered))
        cross_channel_name = "VH" if "VH" in filtered else ("HV" if "HV" in filtered else primary_channel_name)
        soil_moisture_proxy = self._soil_moisture_proxy(
            backscatter_primary=backscatter_db[primary_channel_name],
            backscatter_cross=backscatter_db[cross_channel_name],
        )
        sample_points, sample_values, moisture_grid, interpolation_method = self._interpolate_soil_moisture(soil_moisture_proxy)
        insar = self._compute_insar(primary, secondary)

        return ProcessedSARData(
            source="Sentinel-1",
            acquisition_time=primary.product.start_time.isoformat(),
            backscatter_db=backscatter_db,
            filtered_linear=filtered,
            polarimetric=polarimetric,
            insar=insar,
            soil_moisture_grid=moisture_grid,
            soil_moisture_sample_points=sample_points,
            soil_moisture_sample_values=sample_values,
            metadata={
                "polarimetric_mode": mode,
                "interpolation_method": interpolation_method,
                "primary_product": primary.product.as_dict(),
                "secondary_product": secondary.product.as_dict() if secondary else None,
                "available_channels": sorted(primary.channels.keys()),
            },
        )

    @staticmethod
    def _radiometric_calibration(channel: np.ndarray) -> np.ndarray:
        magnitude = np.abs(channel).astype(np.float32)
        power = np.square(np.maximum(magnitude, EPSILON))
        return power

    def _lee_filter(self, image: np.ndarray, size: int = 7) -> np.ndarray:
        local_mean = self._box_filter(image, size)
        local_mean_sq = self._box_filter(np.square(image), size)
        local_variance = np.maximum(local_mean_sq - np.square(local_mean), 0.0)
        noise_variance = float(np.mean(local_variance))
        weights = local_variance / (local_variance + noise_variance + EPSILON)
        filtered = local_mean + (weights * (image - local_mean))
        return filtered.astype(np.float32)

    @staticmethod
    def _box_filter(image: np.ndarray, size: int) -> np.ndarray:
        pad = size // 2
        padded = np.pad(image, ((pad, pad), (pad, pad)), mode="reflect")
        integral = np.pad(padded, ((1, 0), (1, 0)), mode="constant").cumsum(axis=0).cumsum(axis=1)
        window_sum = integral[size:, size:] - integral[:-size, size:] - integral[size:, :-size] + integral[:-size, :-size]
        return window_sum / float(size * size)

    def _coerce_polarimetric_channels(self, channels: dict[str, np.ndarray]) -> tuple[np.ndarray, np.ndarray, np.ndarray, str]:
        upper = {name.upper(): np.asarray(array) for name, array in channels.items()}
        if {"HH", "HV", "VV"}.issubset(upper):
            hh, hv, vv = upper["HH"], upper["HV"], upper["VV"]
            mode = "full-pol"
        elif {"VV", "VH"}.issubset(upper):
            vv = upper["VV"]
            hh = vv.astype(np.complex64)
            hv = (upper["VH"] / math.sqrt(2.0)).astype(np.complex64)
            mode = "pseudo-dual-pol-vv-vh"
        elif {"HH", "HV"}.issubset(upper):
            hh = upper["HH"]
            hv = upper["HV"]
            vv = hh.astype(np.complex64)
            mode = "pseudo-dual-pol-hh-hv"
        else:
            dominant_name = "VV" if "VV" in upper else next(iter(upper))
            dominant = upper[dominant_name].astype(np.complex64)
            hh = dominant
            hv = dominant * 0.15
            vv = dominant
            mode = "single-pol-proxy"

        hh, hv, vv = self._crop_to_common_shape(hh.astype(np.complex64), hv.astype(np.complex64), vv.astype(np.complex64))
        return hh, hv, vv, mode

    @staticmethod
    def _crop_to_common_shape(*arrays: np.ndarray) -> tuple[np.ndarray, ...]:
        min_rows = min(array.shape[0] for array in arrays)
        min_cols = min(array.shape[1] for array in arrays)
        return tuple(array[:min_rows, :min_cols] for array in arrays)

    @staticmethod
    def _pauli_decomposition(hh: np.ndarray, hv: np.ndarray, vv: np.ndarray) -> dict[str, np.ndarray]:
        red = np.abs((hh - vv) / math.sqrt(2.0)) ** 2
        green = np.abs(math.sqrt(2.0) * hv) ** 2
        blue = np.abs((hh + vv) / math.sqrt(2.0)) ** 2
        return {"red": red.astype(np.float32), "green": green.astype(np.float32), "blue": blue.astype(np.float32)}

    @staticmethod
    def _freeman_durden(hh: np.ndarray, hv: np.ndarray, vv: np.ndarray) -> dict[str, np.ndarray]:
        surface = np.abs((hh + vv) / math.sqrt(2.0)) ** 2
        double_bounce = np.abs((hh - vv) / math.sqrt(2.0)) ** 2
        volume = 2.0 * (np.abs(hv) ** 2)
        total = surface + double_bounce + volume + EPSILON
        return {
            "surface": (surface / total).astype(np.float32),
            "double_bounce": (double_bounce / total).astype(np.float32),
            "volume": (volume / total).astype(np.float32),
        }

    @staticmethod
    def _yamaguchi_4c(hh: np.ndarray, hv: np.ndarray, vv: np.ndarray) -> dict[str, np.ndarray]:
        surface = np.abs((hh + vv) / math.sqrt(2.0)) ** 2
        double_bounce = np.abs((hh - vv) / math.sqrt(2.0)) ** 2
        volume = 2.0 * (np.abs(hv) ** 2)
        helix = np.abs(np.imag((hh * np.conjugate(hv)) - (vv * np.conjugate(hv))))
        total = surface + double_bounce + volume + helix + EPSILON
        return {
            "surface": (surface / total).astype(np.float32),
            "double_bounce": (double_bounce / total).astype(np.float32),
            "volume": (volume / total).astype(np.float32),
            "helix": (helix / total).astype(np.float32),
        }

    @staticmethod
    def _cloude_pottier(hh: np.ndarray, hv: np.ndarray, vv: np.ndarray) -> dict[str, np.ndarray]:
        k1 = (hh + vv) / math.sqrt(2.0)
        k2 = (hh - vv) / math.sqrt(2.0)
        k3 = math.sqrt(2.0) * hv
        coherency = np.empty(hh.shape + (3, 3), dtype=np.complex64)
        coherency[..., 0, 0] = k1 * np.conjugate(k1)
        coherency[..., 0, 1] = k1 * np.conjugate(k2)
        coherency[..., 0, 2] = k1 * np.conjugate(k3)
        coherency[..., 1, 0] = np.conjugate(coherency[..., 0, 1])
        coherency[..., 1, 1] = k2 * np.conjugate(k2)
        coherency[..., 1, 2] = k2 * np.conjugate(k3)
        coherency[..., 2, 0] = np.conjugate(coherency[..., 0, 2])
        coherency[..., 2, 1] = np.conjugate(coherency[..., 1, 2])
        coherency[..., 2, 2] = k3 * np.conjugate(k3)

        eigenvalues, eigenvectors = np.linalg.eigh(coherency)
        eigenvalues = np.clip(np.real(eigenvalues), EPSILON, None)
        eigenvalue_sum = np.sum(eigenvalues, axis=-1, keepdims=True)
        probabilities = eigenvalues / eigenvalue_sum
        entropy = -np.sum(probabilities * (np.log(probabilities) / np.log(3.0)), axis=-1)
        anisotropy = (eigenvalues[..., 1] - eigenvalues[..., 0]) / (eigenvalues[..., 1] + eigenvalues[..., 0] + EPSILON)
        alpha_angles = np.arccos(np.clip(np.abs(eigenvectors[..., 0, :]), 0.0, 1.0))
        alpha = np.sum(probabilities * np.moveaxis(alpha_angles, -1, -1), axis=-1)

        return {
            "entropy": entropy.astype(np.float32),
            "anisotropy": anisotropy.astype(np.float32),
            "alpha": np.degrees(alpha).astype(np.float32),
        }

    @staticmethod
    def _soil_moisture_proxy(backscatter_primary: np.ndarray, backscatter_cross: np.ndarray) -> np.ndarray:
        moisture_from_primary = 100.0 / (1.0 + np.exp(0.55 * (backscatter_primary + 11.5)))
        depolarization = np.clip((backscatter_cross - backscatter_primary + 12.0) / 12.0, 0.0, 1.0)
        proxy = (0.8 * moisture_from_primary) + (20.0 * depolarization)
        return np.clip(proxy, 0.0, 100.0).astype(np.float32)

    def _interpolate_soil_moisture(self, moisture_proxy: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray, str]:
        rows, cols = moisture_proxy.shape
        step = max(min(rows, cols) // 18, 12)
        y_coords = np.arange(0, rows, step)
        x_coords = np.arange(0, cols, step)
        yy, xx = np.meshgrid(y_coords, x_coords, indexing="ij")
        sample_points = np.column_stack((xx.ravel(), yy.ravel())).astype(np.float32)
        sample_values = moisture_proxy[yy, xx].ravel().astype(np.float32)
        grid_x = np.linspace(0.0, float(cols - 1), num=min(64, cols))
        grid_y = np.linspace(0.0, float(rows - 1), num=min(64, rows))
        grid, method = self._ordinary_kriging(sample_points, sample_values, grid_x, grid_y)
        return sample_points, sample_values, grid.astype(np.float32), method

    @staticmethod
    def _ordinary_kriging(
        sample_points: np.ndarray,
        sample_values: np.ndarray,
        grid_x: np.ndarray,
        grid_y: np.ndarray,
    ) -> tuple[np.ndarray, str]:
        try:
            from pykrige.ok import OrdinaryKriging  # type: ignore

            kriging = OrdinaryKriging(
                sample_points[:, 0],
                sample_points[:, 1],
                sample_values,
                variogram_model="spherical",
                enable_plotting=False,
                verbose=False,
            )
            interpolated, _ = kriging.execute("grid", grid_x, grid_y)
            return np.asarray(interpolated), "ordinary_kriging"
        except Exception:
            xx, yy = np.meshgrid(grid_x, grid_y)
            grid_points = np.column_stack((xx.ravel(), yy.ravel()))
            deltas = grid_points[:, None, :] - sample_points[None, :, :]
            distances = np.sqrt(np.sum(np.square(deltas), axis=-1)) + EPSILON
            weights = 1.0 / np.square(distances)
            interpolated = np.sum(weights * sample_values[None, :], axis=1) / np.sum(weights, axis=1)
            return interpolated.reshape(len(grid_y), len(grid_x)), "inverse_distance_weighting"

    def _compute_insar(
        self,
        primary: SentinelRasterBundle,
        secondary: SentinelRasterBundle | None,
    ) -> InSARProducts | None:
        if secondary is None:
            return None

        preferred_channels = ["VV", "HH", "VH", "HV"]
        channel_name = next((name for name in preferred_channels if name in primary.channels and name in secondary.channels), None)
        if channel_name is None:
            return None

        first = np.asarray(primary.channels[channel_name]).astype(np.complex64)
        second = np.asarray(secondary.channels[channel_name]).astype(np.complex64)
        first, second = self._crop_to_common_shape(first, second)
        coherence = self._coherence(first, second)
        phase = np.angle(first * np.conjugate(second))
        phase_unwrapped = self._unwrap_phase(phase)
        displacement = (phase_unwrapped * SENTINEL_1_WAVELENGTH_METERS) / (4.0 * math.pi)
        temporal_baseline = (secondary.product.start_time - primary.product.start_time) / timedelta(days=1)
        return InSARProducts(
            coherence=coherence.astype(np.float32),
            phase_unwrapped=phase_unwrapped.astype(np.float32),
            displacement_m=displacement.astype(np.float32),
            temporal_baseline_days=float(abs(temporal_baseline)),
        )

    def _coherence(self, first: np.ndarray, second: np.ndarray, size: int = 5) -> np.ndarray:
        numerator = self._box_filter(np.abs(first * np.conjugate(second)), size)
        denominator = np.sqrt(
            self._box_filter(np.abs(first) ** 2, size)
            * self._box_filter(np.abs(second) ** 2, size)
        )
        return numerator / np.maximum(denominator, EPSILON)

    @staticmethod
    def _unwrap_phase(phase: np.ndarray) -> np.ndarray:
        try:
            from skimage.restoration import unwrap_phase  # type: ignore

            return np.asarray(unwrap_phase(phase))
        except Exception:
            return np.unwrap(np.unwrap(phase, axis=0), axis=1)