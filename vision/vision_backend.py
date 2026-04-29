"""
DELTA - vision/vision_backend.py
Backend di inferenza visiva basato su TFLite.
Supporta modelli multipli tramite MODELS_REGISTRY in core/config.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, Optional
import logging

LOGGER = logging.getLogger("delta.vision.backend")


class VisionBackend(ABC):
    """Interfaccia astratta per backend visivi."""

    @abstractmethod
    def infer(self, image_path: str | Path) -> Dict[str, Any]:
        """Esegue classificazione e ritorna dict con class/confidence/top_k."""
        ...

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Nome del modello attivo."""
        ...

    @property
    @abstractmethod
    def is_ready(self) -> bool:
        """True se il backend è pronto per l'inferenza."""
        ...


class CpuMobileNetBackend(VisionBackend):
    """
    Backend CPU basato su TFLite.
    Carica il modello indicato (o 'dipladenia' di default se disponibile).
    """

    def __init__(self, model_key: str = "dipladenia"):
        from core.config import MODELS_REGISTRY, ACTIVE_MODEL

        # Usa model_key, poi ACTIVE_MODEL, poi primo disponibile
        key = model_key if model_key in MODELS_REGISTRY else ACTIVE_MODEL
        if key not in MODELS_REGISTRY:
            key = next(iter(MODELS_REGISTRY), None)

        self._model_key = key
        self._cfg = MODELS_REGISTRY.get(key, {}) if key else {}
        self._interpreter = None
        self._input_details = None
        self._output_details = None
        self._labels: list = []
        self._ready = False
        self._error: Optional[str] = None

        self._init_model()

    def _init_model(self):
        if not self._cfg:
            self._error = "Nessuna configurazione modello disponibile"
            LOGGER.warning(self._error)
            return

        model_path = Path(self._cfg["model_path"])
        labels_path = Path(self._cfg["labels_path"])

        if not model_path.exists():
            self._error = f"Modello non trovato: {model_path}"
            LOGGER.warning(self._error)
            return

        # Carica labels
        if labels_path.exists():
            self._labels = [
                l.strip() for l in labels_path.read_text(encoding="utf-8").splitlines() if l.strip()
            ]
        else:
            self._labels = self._cfg.get("classes", [])

        # Carica interprete TFLite
        try:
            from ai.tflite_inference_runner import make_interpreter
            self._interpreter, self._input_details, self._output_details = make_interpreter(
                model_path, num_threads=4
            )
            self._ready = True
            LOGGER.info(
                "CpuMobileNetBackend pronto: modello=%s, classi=%s",
                self._model_key, self._labels,
            )
        except Exception as exc:
            self._error = str(exc)
            LOGGER.warning("CpuMobileNetBackend non disponibile: %s", exc)

    @property
    def model_name(self) -> str:
        return self._model_key or "unknown"

    @property
    def is_ready(self) -> bool:
        return self._ready

    def infer(self, image_path: str | Path) -> Dict[str, Any]:
        if not self._ready:
            return {
                "class": "non_disponibile",
                "confidence": 0.0,
                "top_k": [],
                "error": self._error,
            }

        import numpy as np
        from ai.tflite_inference_runner import (
            preprocess_image,
            run_inference,
            decode_prediction,
        )

        try:
            h, w = self._cfg.get("input_size", (224, 224))
            input_dtype = self._input_details[0].get("dtype")
            img = preprocess_image(Path(image_path), (h, w, 3), input_dtype)

            probs = run_inference(
                self._interpreter,
                self._input_details,
                self._output_details,
                img,
            )
            result = decode_prediction(probs, self._labels, top_k=3)
            result["model"] = self._model_key
            return result
        except Exception as exc:
            LOGGER.error("Errore inferenza: %s", exc)
            return {
                "class": "errore",
                "confidence": 0.0,
                "top_k": [],
                "error": str(exc),
                "model": self._model_key,
            }


# Placeholder per futuro HailoBackend (Raspberry Pi AI HAT 2+)
class HailoBackend(VisionBackend):
    @property
    def model_name(self) -> str:
        return "hailo"

    @property
    def is_ready(self) -> bool:
        return False

    def infer(self, image_path: str | Path) -> Dict[str, Any]:
        raise NotImplementedError("Hailo non ancora implementato")
