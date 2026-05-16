"""Geometry validation, crop questioning, and diagnosis generation."""

from __future__ import annotations

import json
import math
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from shapely.geometry import Point, shape
from shapely.geometry.base import BaseGeometry
from shapely.ops import transform

from chat.chat_engine import ChatEngine
from nasa_delta_plant.integrator import FieldState


DATASET_33_CLASSES = [
    "Apple_Apple_scab",
    "Apple_Black_rot",
    "Apple_Cedar_apple_rust",
    "Apple_healthy",
    "Bell_pepper_Bacterial_spot",
    "Bell_pepper_healthy",
    "Blueberry_healthy",
    "Cherry_healthy",
    "Cherry_Powdery_mildew",
    "Corn_Cercospora",
    "Corn_Common_rust",
    "Corn_healthy",
    "Corn_Northern_Leaf_Blight",
    "Grape_Black_rot",
    "Grape_Esca",
    "Grape_healthy",
    "Grape_Leaf_blight",
    "Peach_healthy",
    "Potato_Early_blight",
    "Potato_healthy",
    "Potato_Late_blight",
    "Squash_Powdery_mildew",
    "Strawberry_healthy",
    "Strawberry_Leaf_scorch",
    "Tomato_Bacterial_spot",
    "Tomato_Early_blight",
    "Tomato_healthy",
    "Tomato_Late_blight",
    "Tomato_Leaf_Mold",
    "Tomato_mosaic_virus",
    "Tomato_Septoria_leaf_spot",
    "Tomato_Target_Spot",
    "Tomato_Yellow_Leaf_Curl",
]

SPECIES_TRAITS = {
    "Apple": {"growth_form": "tree", "production": "fruit", "management": "orchard_vineyard", "leaf": "broad_leaf", "harvest": "fruit_cluster"},
    "Bell_pepper": {"growth_form": "herbaceous", "production": "vegetable", "management": "greenhouse", "leaf": "broad_leaf", "harvest": "fleshy_fruit"},
    "Blueberry": {"growth_form": "shrub", "production": "berry", "management": "orchard_vineyard", "leaf": "broad_leaf", "harvest": "berries"},
    "Cherry": {"growth_form": "tree", "production": "fruit", "management": "orchard_vineyard", "leaf": "broad_leaf", "harvest": "fruit_cluster"},
    "Corn": {"growth_form": "grass", "production": "cereal", "management": "row_crop", "leaf": "grass_blade", "harvest": "ears_cobs"},
    "Grape": {"growth_form": "vine", "production": "fruit", "management": "orchard_vineyard", "leaf": "broad_leaf", "harvest": "fruit_cluster"},
    "Peach": {"growth_form": "tree", "production": "fruit", "management": "orchard_vineyard", "leaf": "broad_leaf", "harvest": "fleshy_fruit"},
    "Potato": {"growth_form": "herbaceous", "production": "tuber", "management": "open_field", "leaf": "compound_leaf", "harvest": "tubers"},
    "Squash": {"growth_form": "vine", "production": "vegetable", "management": "open_field", "leaf": "broad_leaf", "harvest": "fleshy_fruit"},
    "Strawberry": {"growth_form": "herbaceous", "production": "berry", "management": "open_field", "leaf": "compound_leaf", "harvest": "berries"},
    "Tomato": {"growth_form": "herbaceous", "production": "vegetable", "management": "greenhouse", "leaf": "compound_leaf", "harvest": "fruit_cluster"},
}

QUESTION_FLOW = [
    {
        "number": 1,
        "id": "growth_form",
        "prompt": "Quale architettura ha la coltura dominante nell'area?",
        "options": ["tree", "vine", "herbaceous", "shrub", "grass"],
    },
    {
        "number": 2,
        "id": "production",
        "prompt": "Quale produzione prevale?",
        "options": ["fruit", "berry", "vegetable", "cereal", "tuber"],
    },
    {
        "number": 3,
        "id": "management",
        "prompt": "Che tipo di gestione agronomica osservi?",
        "options": ["orchard_vineyard", "greenhouse", "open_field", "row_crop"],
    },
    {
        "number": 4,
        "id": "leaf",
        "prompt": "Che tipo di foglia prevale?",
        "options": ["broad_leaf", "compound_leaf", "grass_blade"],
    },
    {
        "number": 5,
        "id": "harvest",
        "prompt": "Quale organo raccogli principalmente?",
        "options": ["fruit_cluster", "berries", "fleshy_fruit", "tubers", "ears_cobs"],
    },
]

DISEASE_KEYWORDS = ["blight", "rust", "rot", "mildew", "mold", "virus", "spot", "scorch", "esca"]


def _extract_species(class_name: str) -> str:
    for species in SPECIES_TRAITS:
        if class_name.startswith(species):
            return species
    return class_name.split("_")[0]


def _level_from_score(score: float, moderate: float = 40.0, high: float = 70.0) -> str:
    if score >= high:
        return "high"
    if score >= moderate:
        return "moderate"
    return "low"


@dataclass(slots=True)
class CropQuestionState:
    answers: dict[str, str] = field(default_factory=dict)
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class CropQuestionEngine:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._state: dict[str, CropQuestionState] = {}
        self._ttl = timedelta(hours=2)

    def ask(
        self,
        session_id: str,
        question_number: int,
        answer: str | None,
        sar_signature: dict[str, Any],
    ) -> dict[str, Any]:
        with self._lock:
            self._purge()
            state = self._state.setdefault(session_id, CropQuestionState())
            if question_number > 0 and answer:
                question = QUESTION_FLOW[min(question_number - 1, len(QUESTION_FLOW) - 1)]
                state.answers[question["id"]] = str(answer).strip().lower()
                state.updated_at = datetime.now(timezone.utc)

            candidate_species = self._candidate_species(state.answers, sar_signature)
            candidate_classes = self._rank_candidate_classes(candidate_species, sar_signature)
            probable_crop = candidate_classes[0] if candidate_classes else None
            confidence = self._confidence(candidate_species, state.answers, sar_signature)

            next_question = None
            if len(state.answers) < len(QUESTION_FLOW) and len(candidate_species) > 1:
                next_question = QUESTION_FLOW[len(state.answers)]

            return {
                "next_question": next_question,
                "candidate_crops": candidate_classes[:8],
                "probable_crop": probable_crop,
                "confidence": confidence,
            }

    def resolve_from_answers(self, answers: list[str] | None, sar_signature: dict[str, Any]) -> dict[str, Any]:
        mapped_answers: dict[str, str] = {}
        for question, answer in zip(QUESTION_FLOW, answers or []):
            mapped_answers[question["id"]] = str(answer).strip().lower()
        candidate_species = self._candidate_species(mapped_answers, sar_signature)
        candidate_classes = self._rank_candidate_classes(candidate_species, sar_signature)
        return {
            "candidate_species": candidate_species,
            "candidate_crops": candidate_classes,
            "probable_crop": candidate_classes[0] if candidate_classes else None,
            "confidence": self._confidence(candidate_species, mapped_answers, sar_signature),
        }

    def _candidate_species(self, answers: dict[str, str], sar_signature: dict[str, Any]) -> list[str]:
        species = list(SPECIES_TRAITS.keys())
        for question_id, answer in answers.items():
            species = [item for item in species if SPECIES_TRAITS[item].get(question_id) == answer]
            if species:
                continue
            species = list(SPECIES_TRAITS.keys())

        species = self._bias_species_from_signature(species, sar_signature)
        return species or list(SPECIES_TRAITS.keys())

    @staticmethod
    def _bias_species_from_signature(species: list[str], sar_signature: dict[str, Any]) -> list[str]:
        biomass = float(sar_signature.get("biomass_index", 0.0))
        canopy = float(sar_signature.get("canopy_structure_metric", 0.0))
        height = float(sar_signature.get("crop_height_estimate_cm", 0.0))
        if height > 220.0:
            species = [item for item in species if SPECIES_TRAITS[item]["growth_form"] in {"tree", "grass"}]
        elif height > 120.0:
            species = [item for item in species if SPECIES_TRAITS[item]["growth_form"] in {"vine", "tree", "grass"}]
        if biomass > 65.0 and canopy > 55.0:
            species = [item for item in species if SPECIES_TRAITS[item]["management"] != "row_crop"] or species
        return species

    @staticmethod
    def _rank_candidate_classes(candidate_species: list[str], sar_signature: dict[str, Any]) -> list[str]:
        disease_risk = float(sar_signature.get("disease_risk_composite", 0.0))
        scored: list[tuple[float, str]] = []
        for class_name in DATASET_33_CLASSES:
            species = _extract_species(class_name)
            if species not in candidate_species:
                continue
            healthy = "healthy" in class_name.lower()
            fungal_match = any(keyword in class_name.lower() for keyword in DISEASE_KEYWORDS)
            score = 0.5
            if healthy:
                score += max(0.0, 55.0 - disease_risk) / 100.0
            else:
                score += disease_risk / 100.0
            if fungal_match:
                score += float(sar_signature.get("disease_risk_composite", 0.0)) / 250.0
            scored.append((score, class_name))
        scored.sort(key=lambda item: item[0], reverse=True)
        return [class_name for _, class_name in scored]

    @staticmethod
    def _confidence(candidate_species: list[str], answers: dict[str, str], sar_signature: dict[str, Any]) -> float:
        base = 0.35 + (0.10 * len(answers))
        if len(candidate_species) == 1:
            base += 0.25
        elif len(candidate_species) <= 3:
            base += 0.12
        disease_risk = float(sar_signature.get("disease_risk_composite", 0.0))
        if disease_risk >= 60.0:
            base += 0.05
        return round(min(base, 0.96), 3)

    def _purge(self) -> None:
        cutoff = datetime.now(timezone.utc) - self._ttl
        expired = [session_id for session_id, state in self._state.items() if state.updated_at < cutoff]
        for session_id in expired:
            self._state.pop(session_id, None)


class AreaDiagnosisService:
    def __init__(self, chat_engine: ChatEngine | None = None) -> None:
        self.chat_engine = chat_engine
        self.crop_engine = CropQuestionEngine()

    def validate_geo_area(self, geo_data: dict[str, Any]) -> dict[str, Any]:
        geometry, area_hectares = self._geometry_from_geo_data(geo_data)
        if not geometry.is_valid:
            raise ValueError("The submitted geometry is invalid or self-intersecting.")
        if area_hectares > 50_000.0:
            raise ValueError("Area exceeds the 50,000 hectare limit.")

        bounds = geometry.bounds
        if bounds[0] < -180.0 or bounds[2] > 180.0 or bounds[1] < -90.0 or bounds[3] > 90.0:
            raise ValueError("Coordinates fall outside valid geographic bounds.")

        centroid = geometry.centroid
        return {
            "validated_geo_data": geo_data,
            "area_hectares": round(area_hectares, 3),
            "centroid": {"lat": round(float(centroid.y), 6), "lon": round(float(centroid.x), 6)},
            "bounds": [round(float(value), 6) for value in bounds],
        }

    def diagnose(
        self,
        field_state: FieldState,
        crop_answers: list[str] | None,
        allow_llm: bool,
    ) -> dict[str, Any]:
        crop_resolution = self.crop_engine.resolve_from_answers(crop_answers, field_state.sar_features)
        probable_crop = crop_resolution.get("probable_crop") or field_state.crop_class or "Unknown"
        sar_features = field_state.sar_features
        power_summary = field_state.power_data.get("summary", {})

        water_stress_score = float(power_summary.get("water_stress_peak", 0.0) * 100.0)
        disease_risk = float(sar_features.get("disease_risk_composite", 0.0))
        yield_forecast = float(sar_features.get("yield_forecast_index", 0.0))
        soil_moisture = float(sar_features.get("soil_moisture_percent", 0.0))
        et0_mean = float(power_summary.get("et0_mean", 0.0))
        recent_precip = float(sar_features.get("support_metrics", {}).get("recent_precip_mm", 0.0))

        irrigation_mm_day = max((et0_mean * (1.15 if water_stress_score >= 70.0 else 0.85)) - (recent_precip / 7.0), 0.0)
        irrigation_recommendation = (
            f"Apply {irrigation_mm_day:.1f} mm/day (about {irrigation_mm_day * 10000:.0f} L/ha/day) split between dawn and dusk for the next 3 days."
            if irrigation_mm_day >= 1.5
            else "No immediate irrigation pulse is required; keep a light maintenance schedule and reassess after the next orbit."
        )
        drainage_recommendation = (
            "Check drains and reduce standing water exposure within 24 hours."
            if soil_moisture >= 78.0 and disease_risk >= 60.0
            else "Drainage is currently acceptable; keep infiltration lanes free and monitor runoff after rainfall."
        )

        anomalies: list[str] = []
        raw_summary = field_state.raw_sar_summary
        if raw_summary.get("insar_available") and float(raw_summary.get("mean_coherence", 1.0)) < 0.35:
            anomalies.append("Low interferometric coherence indicates structural change or soil disturbance.")
        if raw_summary.get("insar_available") and float(raw_summary.get("mean_displacement_cm", 0.0)) > 1.5:
            anomalies.append("Measured displacement suggests localized deformation or water-driven settling.")
        if soil_moisture > 80.0:
            anomalies.append("Soil moisture remains high across the interpolated grid, increasing waterlogging risk.")
        if disease_risk > 70.0 and water_stress_score > 55.0:
            anomalies.append("Concurrent stress and pathogen pressure may accelerate canopy decline.")

        phytopathology_flags = [
            flag
            for flag in [
                "fungal_pressure" if disease_risk >= 65.0 else None,
                "vascular_stress" if water_stress_score >= 65.0 else None,
                "deformation_signal" if any("displacement" in item.lower() for item in anomalies) else None,
                "waterlogging_signal" if soil_moisture >= 80.0 else None,
            ]
            if flag is not None
        ]

        procedural = {
            "probable_crop": probable_crop,
            "candidate_crops": crop_resolution.get("candidate_crops", [])[:8],
            "water_stress_level": _level_from_score(water_stress_score, moderate=35.0, high=65.0),
            "disease_risk_level": _level_from_score(disease_risk),
            "yield_forecast_level": "good" if yield_forecast >= 70.0 else ("stable" if yield_forecast >= 45.0 else "fragile"),
            "irrigation_recommendation": irrigation_recommendation,
            "drainage_recommendation": drainage_recommendation,
            "phytopathology_flags": phytopathology_flags,
            "anomalies": anomalies,
            "confidence_score": round(min((field_state.confidence_score * 0.7) + (crop_resolution.get("confidence", 0.0) * 0.3), 0.98), 3),
        }

        report_farmer, report_scientist, llm_used = self._narratives(field_state, procedural, allow_llm)
        procedural["report_farmer"] = report_farmer
        procedural["report_scientist"] = report_scientist
        procedural["llm_used"] = llm_used
        return procedural

    @staticmethod
    def _geometry_from_geo_data(geo_data: dict[str, Any]) -> tuple[BaseGeometry, float]:
        geo_type = str(geo_data.get("type", "")).lower()
        if geo_type == "circle":
            center = geo_data.get("center") or {}
            lat = float(center.get("lat"))
            lon = float(center.get("lng", center.get("lon")))
            radius_m = float(geo_data.get("radius", 0.0))
            if radius_m <= 0.0:
                raise ValueError("Circle radius must be greater than zero.")
            degrees = radius_m / 111_320.0
            geometry = Point(lon, lat).buffer(degrees, resolution=64)
            area_hectares = (math.pi * radius_m * radius_m) / 10_000.0
            return geometry, area_hectares

        if "geojson" in geo_data:
            geometry = shape(geo_data["geojson"].get("geometry", geo_data["geojson"]))
            area_hectares = AreaDiagnosisService._approx_area_hectares(geometry)
            return geometry, area_hectares

        raise ValueError("Unsupported geo_data payload.")

    @staticmethod
    def _approx_area_hectares(geometry: BaseGeometry) -> float:
        centroid = geometry.centroid
        lat0 = math.radians(float(centroid.y))

        def _project(lon: float, lat: float, z: float | None = None) -> tuple[float, float]:
            x = (lon - centroid.x) * 111_320.0 * math.cos(lat0)
            y = (lat - centroid.y) * 110_540.0
            return x, y

        projected = transform(_project, geometry)
        return float(projected.area) / 10_000.0

    def _narratives(self, field_state: FieldState, procedural: dict[str, Any], allow_llm: bool) -> tuple[str, str, bool]:
        fallback_farmer = (
            f"Per l'area analizzata la coltura piu probabile e {procedural['probable_crop']}. "
            f"Lo stress idrico e {procedural['water_stress_level']}, il rischio fitopatologico e {procedural['disease_risk_level']} "
            f"e l'indice di resa atteso resta {procedural['yield_forecast_level']}. "
            f"Azione prioritaria: {procedural['irrigation_recommendation']}"
        )
        fallback_scientist = (
            f"FieldState confidence={field_state.confidence_score:.2f}; crop={procedural['probable_crop']}; "
            f"soil_moisture={field_state.sar_features.get('soil_moisture_percent', 0):.2f}%; "
            f"biomass={field_state.sar_features.get('biomass_index', 0):.2f}; "
            f"disease_risk={field_state.sar_features.get('disease_risk_composite', 0):.2f}; "
            f"yield_index={field_state.sar_features.get('yield_forecast_index', 0):.2f}. "
            f"Anomalies: {', '.join(procedural['anomalies']) or 'none'}"
        )
        if not allow_llm or self.chat_engine is None:
            return fallback_farmer, fallback_scientist, False

        payload = json.dumps({"field_state": field_state.as_dict(), "procedural": procedural}, ensure_ascii=True)
        farmer_prompt = (
            "Scrivi in italiano un report per agricoltore di massimo 170 parole. "
            "Tono chiaro, operativo, non tecnico. Nessun disclaimer. "
            f"Contesto JSON: {payload}"
        )
        scientist_prompt = (
            "Scrivi in italiano un report tecnico-scientifico di massimo 260 parole. "
            "Usa terminologia SAR, POWER e indicatori quantitativi. "
            f"Contesto JSON: {payload}"
        )
        farmer_text = (self.chat_engine.chat_internal(farmer_prompt) or "").strip()
        scientist_text = (self.chat_engine.chat_internal(scientist_prompt) or "").strip()
        return farmer_text or fallback_farmer, scientist_text or fallback_scientist, bool(farmer_text or scientist_text)