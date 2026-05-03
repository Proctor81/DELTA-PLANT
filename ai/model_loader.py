"""
DELTA - ai/model_loader.py
Caricamento e gestione del modello TFLite (float16/INT8).
Supporta Raspberry Pi AI HAT 2+ (Edge TPU / NPU) con fallback su CPU.
"""

import logging
import os
import sys
from pathlib import Path
from typing import Optional, Tuple, List

from core.config import MODEL_CONFIG, DEFAULT_LABELS, BASE_DIR

logger = logging.getLogger("delta.ai.model_loader")


class ModelLoadError(RuntimeError):
    """Errore critico durante caricamento del modello TFLite."""


class ModelLoader:
    """
    Carica e gestisce il modello TFLite.
    Supporta Edge TPU (AI HAT 2+) con fallback automatico su CPU.
    """

    def __init__(self):
        self.interpreter = None
        self.labels: List[str] = []
        self.input_details = None
        self.output_details = None
        self._backend = "not_loaded"
        self._last_error: Optional[str] = None
        self._model_path_raw = str(MODEL_CONFIG["model_path"])
        self._labels_path_raw = str(MODEL_CONFIG["labels_path"])
        self._model_path = self._resolve_path(self._model_path_raw)
        self._labels_path = self._resolve_path(self._labels_path_raw)
        self._use_edge_tpu = MODEL_CONFIG["use_edge_tpu"]

        self._load_labels()
        self._load_model()

    # ─────────────────────────────────────────────
    # CARICAMENTO ETICHETTE
    # ─────────────────────────────────────────────

    def _load_labels(self):
        """Carica le etichette delle classi dal file o usa i default."""
        if self._labels_path.exists():
            with self._labels_path.open("r", encoding="utf-8") as f:
                self.labels = [line.strip() for line in f if line.strip()]
            logger.info(
                "Etichette caricate da file: %d classi (%s).",
                len(self.labels),
                self._labels_path,
            )
        else:
            self.labels = list(DEFAULT_LABELS)
            logger.warning(
                "File etichette non trovato (%s). Uso etichette predefinite.",
                self._labels_path,
            )

    # ─────────────────────────────────────────────
    # CARICAMENTO MODELLO TFLITE
    # ─────────────────────────────────────────────

    def _load_model(self):
        """
        Tenta il caricamento con Edge TPU (AI HAT 2+).
        In caso di errore, esegue fallback su CPU TFLite.
        Se il modello non esiste o non e` caricabile, genera un errore esplicito.
        """
        if not self._validate_model_path():
            self._backend = "unavailable"
            return
        logger.info("Caricamento modello TFLite da: %s", self._model_path)

        # Prova Edge TPU prima
        if self._use_edge_tpu:
            if self._try_load_edge_tpu():
                return

        # Fallback CPU TFLite
        self._load_cpu_tflite()

    def _resolve_path(self, configured_path: str) -> Path:
        """Risoluzione robusta di path assoluti/relativi (supporta ~ e variabili ambiente)."""
        expanded = Path(os.path.expandvars(os.path.expanduser(str(configured_path))))

        if expanded.is_absolute():
            return expanded.resolve(strict=False)

        cwd_candidate = (Path.cwd() / expanded).resolve(strict=False)
        if cwd_candidate.exists():
            return cwd_candidate

        base_candidate = (BASE_DIR / expanded).resolve(strict=False)
        return base_candidate

    def _validate_model_path(self) -> bool:
        """
        Verifica che il file modello esista e sia un file regolare.
        Restituisce True se valido, False se il file manca (solo warning).
        """
        logger.info(
            "Model path configurato: raw=%s | resolved=%s",
            self._model_path_raw,
            self._model_path,
        )

        if not self._model_path.exists():
            logger.warning(
                "Modello TFLite non trovato: %s. "
                "Il sistema avvia in modalità degradata (nessuna inferenza AI). "
                "Eseguire training o fornire un modello reale.",
                self._model_path,
            )
            return False

        if not self._model_path.is_file():
            logger.warning(
                "Model path non è un file regolare: %s. "
                "Il sistema avvia in modalità degradata.",
                self._model_path,
            )
            return False

        logger.info(
            "Model file verificato: %s (%.2f MB)",
            self._model_path,
            self._model_path.stat().st_size / (1024 * 1024),
        )
        return True

    def _try_load_edge_tpu(self) -> bool:
        """Tenta il caricamento con pycoral per Edge TPU. Restituisce True se riuscito."""
        try:
            from pycoral.utils.edgetpu import make_interpreter  # type: ignore
            self.interpreter = make_interpreter(str(self._model_path))
            self.interpreter.allocate_tensors()
            self.input_details = self.interpreter.get_input_details()
            self.output_details = self.interpreter.get_output_details()
            self._align_labels_with_output()
            self._backend = "edge_tpu"
            self._log_model_io_details()
            logger.info("Modello caricato su Edge TPU (AI HAT 2+).")
            return True
        except ImportError:
            logger.warning("pycoral non installato. Fallback su CPU TFLite.")
        except Exception as exc:
            logger.warning("Edge TPU non disponibile (%s). Fallback su CPU.", exc)
        return False

    def _load_cpu_tflite(self):
        """Carica il modello con tflite_runtime su CPU."""
        try:
            try:
                import tflite_runtime.interpreter as tflite  # type: ignore
                runtime = "tflite_runtime"
            except ImportError:
                try:
                    import ai_edge_litert.interpreter as tflite  # type: ignore
                    runtime = "ai_edge_litert"
                except ImportError:
                    import tensorflow.lite as tflite  # type: ignore
                    runtime = "tensorflow.lite"

            self.interpreter = tflite.Interpreter(
                model_path=str(self._model_path),
                num_threads=MODEL_CONFIG["num_threads"],
            )
            self.interpreter.allocate_tensors()
            self.input_details = self.interpreter.get_input_details()
            self.output_details = self.interpreter.get_output_details()
            self._align_labels_with_output()
            self._backend = f"cpu:{runtime}"
            self._log_model_io_details()
            logger.info("Modello TFLite caricato su CPU (%d thread).",
                        MODEL_CONFIG["num_threads"])
        except Exception as exc:
            self.interpreter = None
            self.input_details = None
            self.output_details = None
            self._backend = "unavailable"
            version_hint = ""
            if sys.version_info >= (3, 13):
                version_hint = " (Python >=3.13 rilevato: usare Python 3.10-3.12)"
            self._last_error = f"{exc}{version_hint}"
            logger.warning(
                "Runtime TFLite non disponibile (%s%s). "
                "Avvio in modalità degradata: inferenza AI simulata.",
                exc,
                version_hint,
            )

    def _align_labels_with_output(self):
        """Allinea il numero di etichette con il numero di classi in output del modello."""
        if not self.output_details:
            return

        shape = self.output_details[0].get("shape")
        if shape is None:
            return

        if len(shape) == 0:
            return

        try:
            output_classes = int(shape[-1])
        except (TypeError, ValueError):
            return

        if output_classes <= 0:
            return

        labels_count = len(self.labels)
        if labels_count == output_classes:
            return

        if labels_count > output_classes:
            logger.warning(
                "Mismatch labels/output: labels=%d, output=%d. "
                "Le etichette extra verranno ignorate.",
                labels_count,
                output_classes,
            )
            self.labels = self.labels[:output_classes]
            return

        logger.warning(
            "Mismatch labels/output: labels=%d, output=%d. "
            "Aggiungo etichette segnaposto mancanti.",
            labels_count,
            output_classes,
        )
        self.labels.extend(f"Classe_{i}" for i in range(labels_count, output_classes))

    def _log_model_io_details(self):
        """Log diagnostico completo su tensori di input/output del modello."""
        if not self.input_details or not self.output_details:
            logger.warning("Dettagli I/O non disponibili dopo allocate_tensors().")
            return

        in0 = self.input_details[0]
        out0 = self.output_details[0]
        logger.info(
            "Model backend=%s | input(shape=%s, dtype=%s, quant=%s) | "
            "output(shape=%s, dtype=%s, quant=%s)",
            self._backend,
            tuple(in0.get("shape", [])),
            in0.get("dtype"),
            in0.get("quantization", (None, None)),
            tuple(out0.get("shape", [])),
            out0.get("dtype"),
            out0.get("quantization", (None, None)),
        )

    # ─────────────────────────────────────────────
    # ACCESSO PARAMETRI TENSORI
    # ─────────────────────────────────────────────

    def get_input_shape(self) -> Tuple[int, int, int]:
        """Restituisce (H, W, C) del tensore di input."""
        if self.input_details:
            shape = self.input_details[0]["shape"]
            return int(shape[1]), int(shape[2]), int(shape[3])
        return (*MODEL_CONFIG["input_size"][::-1], 3)  # H, W, 3

    def get_input_dtype(self):
        """Restituisce il dtype del tensore di input."""
        if self.input_details:
            return self.input_details[0]["dtype"]
        return None

    def get_input_quantization(self) -> Tuple[float, int]:
        """Restituisce (scale, zero_point) per quantizzazione INT8."""
        if self.input_details:
            quant = self.input_details[0].get("quantization", (1.0, 0))
            return quant[0], quant[1]
        return 1.0, 0

    def is_ready(self) -> bool:
        """True se l'interprete è caricato e pronto."""
        return self.interpreter is not None

    def get_last_error(self) -> Optional[str]:
        """Dettaglio ultimo errore di caricamento runtime/modello, se presente."""
        return self._last_error

    def reload(self, model_path: Optional[str] = None):
        """Ricarica il modello (dopo fine-tuning)."""
        if model_path:
            self._model_path_raw = str(model_path)
            self._model_path = self._resolve_path(self._model_path_raw)
        logger.info("Ricaricamento modello da %s...", self._model_path)
        self._load_model()
