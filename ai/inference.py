"""
DELTA - ai/inference.py
Esecuzione inferenza sul modello TFLite.
Gestisce input/output quantizzati o float e output strutturato.
"""

import logging
from typing import Dict, Any, List, Optional

import numpy as np

from core.config import MODEL_CONFIG, FLOWER_LABELS, FRUIT_LABELS
from ai.model_loader import ModelLoader

logger = logging.getLogger("delta.ai.inference")


class PlantInference:
    """
    Esegue l'inferenza sul modello TFLite per classificazione malattie.
    Gestisce automaticamente input/output quantizzati o float.
    """

    def __init__(self, model_loader: ModelLoader):
        self.loader = model_loader
        self._conf_threshold = MODEL_CONFIG["confidence_threshold"]
        self._runtime_warning_emitted = False

    # ─────────────────────────────────────────────
    # PREDIZIONE PRINCIPALE
    # ─────────────────────────────────────────────

    def predict(
        self,
        image: np.ndarray,
        sensor_data: Dict[str, Any],
        label_set: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Esegue la predizione su un'immagine preprocessata.

        Args:
            image: array numpy (1, H, W, 3) già preparato
            sensor_data: dati ambientali per contesto
            label_set: set etichette da usare (None/"leaf", "flower", "fruit")

        Returns:
            dict con classe, confidenza e distribuzione probabilità
        """
        labels = self._resolve_labels(label_set)

        if not self.loader.is_ready():
            log_fn = logger.warning if not self._runtime_warning_emitted else logger.debug
            log_fn(
                "Inferenza reale non disponibile (backend=%s, errore=%s). "
                "Uso fallback simulato.",
                getattr(self.loader, "_backend", "unknown"),
                self.loader.get_last_error(),
            )
            self._runtime_warning_emitted = True
            return self._simulate_result(labels)

        try:
            return self._run_inference(image, labels)
        except Exception as exc:
            logger.error("Errore durante inferenza: %s", exc, exc_info=True)
            raise RuntimeError(f"Errore durante inferenza TFLite: {exc}") from exc

    # ─────────────────────────────────────────────
    # INFERENZA REALE
    # ─────────────────────────────────────────────

    def _run_inference(self, image: np.ndarray, labels: List[str]) -> Dict[str, Any]:
        """Esegue l'inferenza reale sul modello TFLite."""
        interpreter = self.loader.interpreter
        input_details = self.loader.input_details
        output_details = self.loader.output_details

        # ── Quantizzazione input INT8 ────────────────────────
        scale, zero_point = self.loader.get_input_quantization()
        input_dtype = self.loader.get_input_dtype()

        if input_dtype is not None and np.issubdtype(input_dtype, np.integer):
            # Converti float [0,1] → INT8 quantizzato
            quantized = (image / scale + zero_point).astype(input_dtype)
            interpreter.set_tensor(input_details[0]["index"], quantized)
        else:
            interpreter.set_tensor(input_details[0]["index"], image.astype(np.float32))

        # ── Esecuzione ───────────────────────────────────────
        interpreter.invoke()

        # ── Output e dequantizzazione ────────────────────────
        raw_output = interpreter.get_tensor(output_details[0]["index"])
        out_quant = output_details[0].get("quantization", (1.0, 0))
        out_scale, out_zero = out_quant[0], out_quant[1]

        if out_scale != 0:
            vector = (raw_output.astype(np.float32) - out_zero) * out_scale
        else:
            vector = raw_output.astype(np.float32)

        vector = vector[0]
        # Non applicare softmax una seconda volta se il modello ha già output normalizzato.
        if float(np.min(vector)) >= 0.0 and abs(float(np.sum(vector)) - 1.0) < 0.05:
            probabilities = vector.astype(np.float32)
        else:
            probabilities = self._softmax(vector)

        return self._build_result(probabilities, labels)

    # ─────────────────────────────────────────────
    # UTILITÀ
    # ─────────────────────────────────────────────

    def _build_result(self, probabilities: np.ndarray, labels: List[str]) -> Dict[str, Any]:
        """Costruisce il dizionario risultato dalla distribuzione di probabilità.

        v3.0: se la confidenza è bassa, attiva fallback software non classificato.
        """
        top_idx = int(np.argmax(probabilities))
        confidence = float(probabilities[top_idx])

        # Usa la soglia configurata per il fallback di bassa confidenza.
        low_conf_threshold = float(MODEL_CONFIG.get("low_confidence_threshold", 0.50))
        if confidence < low_conf_threshold:
            # Classe sintetica: non è un indice reale del modello.
            return {
                "class": "Classe_NonClassificato",
                "confidence": confidence,
                "class_index": -1,
                "top3": [],
                "above_threshold": False,
                "simulated": False,
                "fallback": True,  # NEW: v3.0 flag
                "requires_chat": True,  # Suggest chat with AI
                "requires_agronomy": True,  # Suggest expert
            }

        # Top-3 predizioni
        top3_indices = np.argsort(probabilities)[::-1][:3]
        top3 = [
            {
                "class": labels[i] if i < len(labels) else f"Classe_{i}",
                "confidence": float(probabilities[i]),
            }
            for i in top3_indices
        ]

        return {
            "class": labels[top_idx] if top_idx < len(labels) else f"Classe_{top_idx}",
            "confidence": confidence,
            "class_index": top_idx,
            "top3": top3,
            "above_threshold": confidence >= self._conf_threshold,
            "simulated": False,
            "fallback": False,  # Normal classification
        }

    def _resolve_labels(self, label_set: Optional[str]) -> List[str]:
        """Restituisce le etichette da usare in base all'organo richiesto."""
        normalized = (label_set or "leaf").strip().lower()
        if normalized in ("leaf", "foglia"):
            return self.loader.labels
        if normalized in ("flower", "fiore"):
            return list(FLOWER_LABELS)
        if normalized in ("fruit", "frutto"):
            return list(FRUIT_LABELS)

        logger.warning("label_set non riconosciuto: %s. Uso etichette foglia.", label_set)
        return self.loader.labels

    def _simulate_result(self, labels: List[str]) -> Dict[str, Any]:
        """Fallback deterministico quando runtime TFLite non è disponibile."""
        if not labels:
            labels = ["Sano"]

        healthy_idx = 0
        if "Sano" in labels:
            healthy_idx = labels.index("Sano")
        else:
            for idx, label in enumerate(labels):
                if "healthy" in label.lower() or "sano" in label.lower():
                    healthy_idx = idx
                    break
        n = len(labels)
        base = 0.40 / max(n - 1, 1)
        probabilities = np.full(n, base, dtype=np.float32)
        probabilities[healthy_idx] = 0.60

        return self._build_result(probabilities, labels) | {"simulated": True}

    @staticmethod
    def _softmax(x: np.ndarray) -> np.ndarray:
        """Applica softmax numericamente stabile."""
        e_x = np.exp(x - np.max(x))
        return e_x / e_x.sum()
