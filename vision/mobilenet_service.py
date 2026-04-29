"""
DELTA - vision/mobilenet_service.py
Servizio vision che espone classificazione multi-modello tramite VisionBackend.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from .vision_backend import CpuMobileNetBackend, VisionBackend


class MobileNetService:
    """
    Punto di accesso unificato alla visione DELTA.
    Supporta selezione dinamica del modello tramite model_key.

    Uso:
        svc = MobileNetService()                  # usa ACTIVE_MODEL
        svc = MobileNetService("dipladenia")       # modello specializzato
        result = svc.classify("path/to/img.jpg")
    """

    def __init__(self, model_key: Optional[str] = None):
        from core.config import ACTIVE_MODEL
        key = model_key or ACTIVE_MODEL
        self.backend: VisionBackend = CpuMobileNetBackend(model_key=key)

    @property
    def is_ready(self) -> bool:
        return self.backend.is_ready

    @property
    def active_model(self) -> str:
        return self.backend.model_name

    def classify(self, image_path: str | Path) -> Dict[str, Any]:
        """
        Classifica un'immagine usando il backend attivo.

        Returns:
            dict con chiavi: class, confidence, top_k, model
        """
        return self.backend.infer(image_path)

    def classify_dipladenia(self, image_path: str | Path) -> Dict[str, Any]:
        """Shortcut per classificazione specializzata Dipladenia/Mandevilla."""
        svc = MobileNetService("dipladenia")
        return svc.classify(image_path)
