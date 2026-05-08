"""
DELTA - vision/vision_service.py
Servizio unificato per backend vision multipli (MobileNet / EfficientFormer).
"""

from __future__ import annotations

from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, Dict, Optional
import logging

import numpy as np

from core.config import MODEL_CONFIG, MODELS_REGISTRY, ACTIVE_MODEL
from .efficientformer_classifier import EfficientFormerClassifier
from .vision_backend import CpuMobileNetBackend, VisionBackend

LOGGER = logging.getLogger("delta.vision.service")


class VisionService:
    """Router minimale dei backend vision in base al MODELS_REGISTRY."""

    def __init__(self, model_key: Optional[str] = None):
        self._model_key = model_key or ACTIVE_MODEL
        self._cfg = dict(MODELS_REGISTRY.get(self._model_key, {}))
        self.backend: VisionBackend = self._build_backend(self._model_key, self._cfg)

    @property
    def is_ready(self) -> bool:
        return self.backend.is_ready

    @property
    def active_model(self) -> str:
        return self.backend.model_name

    @property
    def backend_type(self) -> str:
        return str(self._cfg.get("backend", "mobilenet")).lower()

    @property
    def can_explain(self) -> bool:
        return bool(getattr(self.backend, "can_explain", False))

    def classify(self, image_path: str | Path) -> Dict[str, Any]:
        return self._normalize_result(self.backend.infer(image_path))

    def classify_image(self, image: np.ndarray) -> Dict[str, Any]:
        if hasattr(self.backend, "infer_image"):
            backend_any: Any = self.backend
            result = backend_any.infer_image(image)
            return self._normalize_result(result)

        # Fallback legacy: scrive una PNG temporanea e usa infer(path).
        try:
            import cv2  # type: ignore
        except ImportError as exc:
            raise RuntimeError("OpenCV richiesto per classify_image legacy") from exc

        with NamedTemporaryFile(suffix=".png", delete=True) as temp_file:
            if not cv2.imwrite(temp_file.name, image):
                raise RuntimeError("Impossibile scrivere file temporaneo per inferenza vision")
            return self.classify(temp_file.name)

    def explain(self, image_path: str | Path) -> Dict[str, Any]:
        if not hasattr(self.backend, "get_explanation"):
            return {
                "model": self.active_model,
                "error": f"Il backend {self.backend_type} non supporta explainability",
            }
        backend_any: Any = self.backend
        return backend_any.get_explanation(image_path)

    def explain_image(self, image: np.ndarray) -> Dict[str, Any]:
        if not hasattr(self.backend, "get_explanation"):
            return {
                "model": self.active_model,
                "error": f"Il backend {self.backend_type} non supporta explainability",
            }
        backend_any: Any = self.backend
        return backend_any.get_explanation(image)

    def _build_backend(self, model_key: str, cfg: Dict[str, Any]) -> VisionBackend:
        backend_name = str(cfg.get("backend", "mobilenet")).lower()
        if backend_name == "efficientformer":
            return EfficientFormerClassifier(
                model_key=model_key,
                quantization=cfg.get("quantization"),
                ensemble_enabled=cfg.get("enable_ensemble"),
            )
        return CpuMobileNetBackend(model_key=model_key)

    def _normalize_result(self, result: Dict[str, Any]) -> Dict[str, Any]:
        normalized = dict(result)
        top_k = list(normalized.get("top_k") or normalized.get("top3") or [])
        confidence = float(normalized.get("confidence") or 0.0)
        low_conf_threshold = float(MODEL_CONFIG.get("low_confidence_threshold", 0.50))
        conf_threshold = float(MODEL_CONFIG.get("confidence_threshold", 0.65))

        if confidence < low_conf_threshold and normalized.get("class") not in ("errore", "non_disponibile"):
            raw_prediction = {
                "class": normalized.get("class"),
                "confidence": confidence,
                "top_k": top_k,
            }
            return {
                "class": "Classe_NonClassificato",
                "confidence": confidence,
                "class_index": -1,
                "top_k": top_k,
                "top3": top_k[:3],
                "above_threshold": False,
                "simulated": bool(normalized.get("simulated", False)),
                "fallback": True,
                "requires_chat": True,
                "requires_agronomy": True,
                "model": normalized.get("model", self.active_model),
                "backend": normalized.get("backend", self.backend_type),
                "quantization": normalized.get("quantization", self._cfg.get("quantization")),
                "ensemble": bool(normalized.get("ensemble", False)),
                "raw_prediction": raw_prediction,
            }

        normalized["top_k"] = top_k
        normalized["top3"] = top_k[:3]
        normalized.setdefault("simulated", False)
        normalized.setdefault("fallback", False)
        normalized.setdefault("above_threshold", confidence >= conf_threshold)
        normalized.setdefault("model", self.active_model)
        normalized.setdefault("backend", self.backend_type)
        return normalized