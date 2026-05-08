"""
DELTA - vision/mobilenet_service.py
Servizio vision che espone classificazione multi-modello tramite VisionBackend.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from .vision_service import VisionService


class MobileNetService(VisionService):
    """
    Compat wrapper storico.

    Usa la nuova VisionService ma mantiene il nome importabile precedente.

    Uso:
        svc = MobileNetService()                  # usa ACTIVE_MODEL
        svc = MobileNetService("dipladenia")       # modello specializzato
        result = svc.classify("path/to/img.jpg")
    """

    def classify_dipladenia(self, image_path: str | Path) -> Dict[str, Any]:
        """Shortcut per classificazione specializzata Dipladenia/Mandevilla."""
        svc = MobileNetService("dipladenia")
        return svc.classify(image_path)
