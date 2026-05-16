"""Feature extraction for fused climate and SAR field analysis."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from nasa_delta_plant.preprocessor import ProcessedSARData


@dataclass(slots=True)
class FieldFeatureVector:
    soil_moisture_percent: float
    biomass_index: float
    crop_height_estimate_cm: float
    canopy_structure_metric: float
    disease_risk_composite: float
    yield_forecast_index: float
    support_metrics: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "soil_moisture_percent": self.soil_moisture_percent,
            "biomass_index": self.biomass_index,
            "crop_height_estimate_cm": self.crop_height_estimate_cm,
            "canopy_structure_metric": self.canopy_structure_metric,
            "disease_risk_composite": self.disease_risk_composite,
            "yield_forecast_index": self.yield_forecast_index,
            "support_metrics": self.support_metrics,
        }


class FeatureExtractor:
    """Extract agronomic field features from processed SAR and POWER data."""

    def extract(
        self,
        processed_sar: ProcessedSARData,
        power_payload: dict[str, Any],
        crop_class: str | None = None,
    ) -> FieldFeatureVector:
        freeman = processed_sar.polarimetric.freeman_durden
        yamaguchi = processed_sar.polarimetric.yamaguchi_4c
        cloude = processed_sar.polarimetric.cloude_pottier
        power_daily = power_payload.get("daily", [])
        power_summary = power_payload.get("summary", {})

        recent_window = power_daily[-7:] if power_daily else []
        recent_precip = sum(float(day.get("PRECTOTCORR", 0.0)) for day in recent_window)
        recent_et0 = sum(float(day.get("ET0", 0.0)) for day in recent_window)
        climate_balance = np.clip((recent_precip - recent_et0) / 20.0, -1.0, 1.0)

        soil_moisture = float(np.mean(processed_sar.soil_moisture_grid)) + float(climate_balance * 12.0)
        soil_moisture = float(np.clip(soil_moisture, 0.0, 100.0))

        volume_component = float(np.mean(freeman["volume"]))
        yamaguchi_volume = float(np.mean(yamaguchi["volume"]))
        gdd_factor = float(np.clip(power_summary.get("gdd_total", 0.0) / 900.0, 0.0, 1.0))
        biomass_index = float(np.clip(100.0 * ((0.5 * volume_component) + (0.3 * yamaguchi_volume) + (0.2 * gdd_factor)), 0.0, 100.0))

        entropy_mean = float(np.mean(cloude["entropy"]))
        anisotropy_mean = float(np.mean(cloude["anisotropy"]))
        alpha_mean = float(np.mean(cloude["alpha"]))
        canopy_structure_metric = float(
            np.clip(100.0 * ((0.45 * entropy_mean) + (0.25 * (1.0 - abs(anisotropy_mean))) + (0.30 * (alpha_mean / 90.0))), 0.0, 100.0)
        )

        coherence_mean = 0.65
        displacement_cm = 0.0
        if processed_sar.insar is not None:
            coherence_mean = float(np.clip(np.mean(processed_sar.insar.coherence), 0.0, 1.0))
            displacement_cm = float(np.mean(np.abs(processed_sar.insar.displacement_m)) * 100.0)

        crop_height_estimate_cm = float(
            np.clip(12.0 + (biomass_index * 0.85) + (canopy_structure_metric * 0.35) + (displacement_cm * 3.5), 5.0, 450.0)
        )

        fungal_peak = float(power_summary.get("fungal_risk_peak", 0.0))
        water_stress_mean = float(power_summary.get("water_stress_mean", 0.0))
        wet_surface_factor = float(np.mean(freeman["surface"]))
        disease_risk = float(
            np.clip(
                100.0
                * (
                    (0.40 * fungal_peak)
                    + (0.20 * water_stress_mean)
                    + (0.15 * wet_surface_factor)
                    + (0.15 * (soil_moisture / 100.0))
                    + (0.10 * (1.0 - coherence_mean))
                ),
                0.0,
                100.0,
            )
        )

        yield_forecast = float(
            np.clip(
                100.0
                * (
                    (0.25 * (1.0 - water_stress_mean))
                    + (0.20 * (soil_moisture / 100.0))
                    + (0.25 * (biomass_index / 100.0))
                    + (0.20 * (canopy_structure_metric / 100.0))
                    + (0.10 * (1.0 - disease_risk / 100.0))
                ),
                0.0,
                100.0,
            )
        )

        support_metrics = {
            "crop_class": crop_class,
            "recent_precip_mm": round(recent_precip, 3),
            "recent_et0_mm": round(recent_et0, 3),
            "volume_component_mean": round(volume_component, 4),
            "entropy_mean": round(entropy_mean, 4),
            "anisotropy_mean": round(anisotropy_mean, 4),
            "alpha_mean_degrees": round(alpha_mean, 3),
            "insar_coherence_mean": round(coherence_mean, 4),
            "mean_displacement_cm": round(displacement_cm, 3),
        }
        return FieldFeatureVector(
            soil_moisture_percent=round(soil_moisture, 3),
            biomass_index=round(biomass_index, 3),
            crop_height_estimate_cm=round(crop_height_estimate_cm, 3),
            canopy_structure_metric=round(canopy_structure_metric, 3),
            disease_risk_composite=round(disease_risk, 3),
            yield_forecast_index=round(yield_forecast, 3),
            support_metrics=support_metrics,
        )