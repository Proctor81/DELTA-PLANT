"""Fuse SAR, weather, and local sensor data into a single field state."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import numpy as np

from nasa_delta_plant.feature_extractor import FieldFeatureVector
from nasa_delta_plant.preprocessor import ProcessedSARData


@dataclass(slots=True)
class FieldState:
    sar_features: dict[str, Any]
    power_data: dict[str, Any]
    local_sensor_data: dict[str, Any] | None
    analysis_timestamp: str
    geo_area: dict[str, Any]
    crop_class: str | None
    confidence_score: float
    raw_sar_summary: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "sar_features": self.sar_features,
            "power_data": self.power_data,
            "local_sensor_data": self.local_sensor_data,
            "analysis_timestamp": self.analysis_timestamp,
            "geo_area": self.geo_area,
            "crop_class": self.crop_class,
            "confidence_score": self.confidence_score,
            "raw_sar_summary": self.raw_sar_summary,
        }


class FieldIntegrator:
    """Build the field state consumed by the diagnosis and API layers."""

    def fuse(
        self,
        features: FieldFeatureVector,
        processed_sar: ProcessedSARData,
        power_data: dict[str, Any],
        geo_area: dict[str, Any],
        local_sensor_data: dict[str, Any] | None = None,
        crop_class: str | None = None,
    ) -> FieldState:
        confidence = 0.40
        if power_data.get("daily"):
            confidence += 0.18
        if len(processed_sar.metadata.get("available_channels", [])) >= 2:
            confidence += 0.14
        if processed_sar.insar is not None:
            confidence += 0.12
        if local_sensor_data:
            confidence += 0.08
        if crop_class:
            confidence += 0.08
        if processed_sar.metadata.get("interpolation_method") == "ordinary_kriging":
            confidence += 0.05

        confidence = float(np.clip(confidence, 0.0, 0.99))
        primary_channel_name = "VV" if "VV" in processed_sar.backscatter_db else next(iter(processed_sar.backscatter_db))
        primary_backscatter = processed_sar.backscatter_db[primary_channel_name]

        raw_sar_summary = {
            "source": processed_sar.source,
            "acquisition_time": processed_sar.acquisition_time,
            "available_channels": processed_sar.metadata.get("available_channels", []),
            "polarimetric_mode": processed_sar.metadata.get("polarimetric_mode"),
            "interpolation_method": processed_sar.metadata.get("interpolation_method"),
            "mean_backscatter_db": round(float(np.mean(primary_backscatter)), 3),
            "std_backscatter_db": round(float(np.std(primary_backscatter)), 3),
            "mean_soil_moisture_grid": round(float(np.mean(processed_sar.soil_moisture_grid)), 3),
            "insar_available": processed_sar.insar is not None,
        }
        if processed_sar.insar is not None:
            raw_sar_summary.update(
                {
                    "mean_coherence": round(float(np.mean(processed_sar.insar.coherence)), 4),
                    "mean_displacement_cm": round(float(np.mean(np.abs(processed_sar.insar.displacement_m)) * 100.0), 3),
                    "temporal_baseline_days": round(processed_sar.insar.temporal_baseline_days, 3),
                }
            )

        return FieldState(
            sar_features=features.as_dict(),
            power_data=power_data,
            local_sensor_data=local_sensor_data,
            analysis_timestamp=datetime.now(timezone.utc).isoformat(),
            geo_area=geo_area,
            crop_class=crop_class,
            confidence_score=round(confidence, 3),
            raw_sar_summary=raw_sar_summary,
        )