"""
DELTA - vision/preprocessing.py
Preprocessing immagini per inferenza TFLite.
Resize, normalizzazione e preparazione del tensore di input.
"""

import logging
from typing import Tuple

import numpy as np

from core.config import MODEL_CONFIG

logger = logging.getLogger("delta.vision.preprocessing")


class Preprocessor:
    """
    Prepara le immagini per l'inferenza sul modello TFLite:
    1. Resize alla dimensione di input del modello
    2. Normalizzazione MobileNetV2 in float32 range [-1, 1]
    3. Aggiunta dimensione batch (1, H, W, C)
    """

    def __init__(self):
        w, h = MODEL_CONFIG["input_size"]
        self._target_size: Tuple[int, int] = (w, h)  # (W, H)
        logger.debug("Preprocessor inizializzato: target size %s.", self._target_size)

    def prepare_for_inference(self, image: np.ndarray) -> np.ndarray:
        """
        Pipeline completa di preprocessing per inferenza.

        Args:
            image: array numpy (H, W, 3) BGR uint8

        Returns:
            array numpy (1, H, W, 3) float32 pronto per inferenza TFLite
        """
        try:
            import cv2  # type: ignore
        except ImportError:
            raise ImportError("OpenCV (cv2) richiesto per il preprocessing.")

        if image is None or image.size == 0:
            raise ValueError("Immagine input vuota o None.")

        # ── 1. Assicura formato (H, W, 3) ────────────────────
        if image.ndim == 2:
            image = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
        elif image.shape[2] == 4:
            image = cv2.cvtColor(image, cv2.COLOR_BGRA2BGR)

        # ── 2. Resize con INTER_AREA (downscale) o INTER_LINEAR ──
        w_target, h_target = self._target_size
        interp = cv2.INTER_AREA if image.shape[0] > h_target else cv2.INTER_LINEAR
        resized = cv2.resize(image, (w_target, h_target), interpolation=interp)

        # ── 3. BGR → RGB (TFLite addestrato su RGB) ──────────
        rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)

        # ── 4. MobileNetV2 preprocessing: [0,255] → [-1, 1] float32 ──
        normalized = (rgb.astype(np.float32) / 127.5) - 1.0

        # ── 5. Aggiungi dimensione batch ─────────────────────
        batched = np.expand_dims(normalized, axis=0)  # (1, H, W, C)

        return batched

    def resize_for_display(self, image: np.ndarray) -> np.ndarray:
        """
        Ridimensiona un'immagine per la visualizzazione (preview).

        Args:
            image: array numpy (H, W, 3) BGR

        Returns:
            array numpy ridimensionato per preview
        """
        try:
            import cv2  # type: ignore
        except ImportError:
            return image

        from core.config import VISION_CONFIG
        w = VISION_CONFIG["preview_width"]
        h = VISION_CONFIG["preview_height"]
        return cv2.resize(image, (w, h), interpolation=cv2.INTER_LINEAR)

    @staticmethod
    def normalize_float(image: np.ndarray) -> np.ndarray:
        """
        Normalizza un'immagine uint8 [0,255] → float32 [0.0, 1.0].
        Utility generica (diversa dalla normalizzazione MobileNetV2 [-1,1]).
        """
        return image.astype(np.float32) / 255.0
