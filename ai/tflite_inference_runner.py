"""
Esecuzione inferenza TFLite su immagini di piante in modalità produzione.

Uso:
    python ai/tflite_inference_runner.py \
    --model models/plant_disease_model_39classes.tflite \
        --image input_images/sample.jpg \
    --labels models/labels_33classes_correct.txt
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path
from typing import List, Tuple, Dict, Any

import numpy as np

try:
    import cv2  # type: ignore
except ImportError as exc:
    raise RuntimeError("OpenCV non installato. Eseguire: pip install opencv-python-headless") from exc

LOGGER = logging.getLogger("delta.tflite.runner")


class TFLiteModelError(RuntimeError):
    """Errore durante caricamento o inferenza TFLite."""


def resolve_path(path_str: str) -> Path:
    """Risoluzione robusta di path assoluti/relativi, con supporto ~ e env vars."""
    candidate = Path(os.path.expanduser(os.path.expandvars(path_str)))
    if candidate.is_absolute():
        return candidate.resolve(strict=False)
    cwd_candidate = (Path.cwd() / candidate).resolve(strict=False)
    if cwd_candidate.exists():
        return cwd_candidate
    return cwd_candidate


def load_labels(labels_path: Path) -> List[str]:
    """Carica etichette da file testo (una classe per riga)."""
    if not labels_path.exists() or not labels_path.is_file():
        raise TFLiteModelError(f"File labels non trovato: {labels_path}")
    labels = [line.strip() for line in labels_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not labels:
        raise TFLiteModelError(f"File labels vuoto: {labels_path}")
    return labels


def make_interpreter(model_path: Path, num_threads: int):
    """Crea interprete TFLite usando tflite_runtime o tensorflow.lite."""
    if not model_path.exists() or not model_path.is_file():
        raise TFLiteModelError(f"Model not found at path: {model_path}")

    try:
        import tflite_runtime.interpreter as tflite  # type: ignore
        runtime_name = "tflite_runtime"
    except ImportError:
        try:
            import ai_edge_litert.interpreter as tflite  # type: ignore
            runtime_name = "ai_edge_litert"
        except ImportError:
            try:
                import tensorflow.lite as tflite  # type: ignore
                runtime_name = "tensorflow.lite"
            except ImportError as exc:
                version_hint = ""
                if sys.version_info >= (3, 13):
                    version_hint = (
                        " Rilevato Python >=3.13: usare un ambiente Python 3.10-3.12 "
                        "per installare tensorflow/tflite-runtime."
                    )
                raise TFLiteModelError(
                    "Nessun runtime TFLite disponibile. "
                    "Installare tflite-runtime o tensorflow." + version_hint
                ) from exc

    try:
        interpreter = tflite.Interpreter(model_path=str(model_path), num_threads=num_threads)
        interpreter.allocate_tensors()
    except Exception as exc:
        raise TFLiteModelError(f"Impossibile allocare tensori per {model_path}: {exc}") from exc

    input_details = interpreter.get_input_details()
    output_details = interpreter.get_output_details()

    LOGGER.info("Modello caricato con backend=%s", runtime_name)
    LOGGER.info(
        "Input: shape=%s dtype=%s quant=%s",
        tuple(input_details[0].get("shape", [])),
        input_details[0].get("dtype"),
        input_details[0].get("quantization", (None, None)),
    )
    LOGGER.info(
        "Output: shape=%s dtype=%s quant=%s",
        tuple(output_details[0].get("shape", [])),
        output_details[0].get("dtype"),
        output_details[0].get("quantization", (None, None)),
    )
    return interpreter, input_details, output_details


def preprocess_image(image_path: Path, input_shape: Tuple[int, int, int], input_dtype) -> np.ndarray:
    """Carica e prepara un'immagine nel formato richiesto dal modello."""
    if not image_path.exists() or not image_path.is_file():
        raise TFLiteModelError(f"Immagine non trovata: {image_path}")

    image = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
    if image is None:
        raise TFLiteModelError(f"Impossibile leggere immagine: {image_path}")

    h, w, _ = input_shape
    rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    resized = cv2.resize(rgb, (w, h), interpolation=cv2.INTER_AREA)

    if np.issubdtype(input_dtype, np.integer):
        batch = np.expand_dims(resized, axis=0).astype(input_dtype)
    else:
        batch = np.expand_dims(resized.astype(np.float32) / 255.0, axis=0)
    return batch


def run_inference(
    interpreter,
    input_details: List[Dict[str, Any]],
    output_details: List[Dict[str, Any]],
    image_tensor: np.ndarray,
) -> np.ndarray:
    """Esegue inferenza e restituisce vettore probabilità float32."""
    in0 = input_details[0]
    out0 = output_details[0]

    input_dtype = in0.get("dtype")
    in_scale, in_zero = in0.get("quantization", (1.0, 0))

    if input_dtype is not None and np.issubdtype(input_dtype, np.integer):
        if image_tensor.dtype != input_dtype:
            if in_scale == 0:
                raise TFLiteModelError("Quantizzazione input invalida: scale=0")
            quantized = (image_tensor / in_scale + in_zero).astype(input_dtype)
            interpreter.set_tensor(in0["index"], quantized)
        else:
            interpreter.set_tensor(in0["index"], image_tensor)
    else:
        interpreter.set_tensor(in0["index"], image_tensor.astype(np.float32))

    interpreter.invoke()

    raw_output = interpreter.get_tensor(out0["index"])
    out_scale, out_zero = out0.get("quantization", (1.0, 0))
    if out_scale and out_scale != 0:
        logits = (raw_output.astype(np.float32) - out_zero) * out_scale
    else:
        logits = raw_output.astype(np.float32)

    vector = logits[0]
    # Se il modello ha già il softmax integrato (output già normalizzato), non applicarlo di nuovo.
    # Criterio: valori non negativi e somma vicina a 1.0.
    if float(np.min(vector)) >= 0.0 and abs(float(np.sum(vector)) - 1.0) < 0.05:
        return vector.astype(np.float32)
    exp = np.exp(vector - np.max(vector))
    probs = exp / np.sum(exp)
    return probs


def decode_prediction(probabilities: np.ndarray, labels: List[str], top_k: int = 3) -> Dict[str, Any]:
    """Converte il vettore probabilità in classe predetta + top-k."""
    if probabilities.ndim != 1:
        raise TFLiteModelError(f"Output modello non valido, atteso 1D: shape={probabilities.shape}")

    top_idx = int(np.argmax(probabilities))
    top_indices = np.argsort(probabilities)[::-1][:top_k]

    top = [
        {
            "class": labels[i] if i < len(labels) else f"class_{i}",
            "confidence": float(probabilities[i]),
        }
        for i in top_indices
    ]

    return {
        "class": labels[top_idx] if top_idx < len(labels) else f"class_{top_idx}",
        "class_index": top_idx,
        "confidence": float(probabilities[top_idx]),
        "top_k": top,
    }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Runner inferenza modello TFLite per malattie piante")
    parser.add_argument("--model", required=True, help="Path del modello .tflite")
    parser.add_argument("--image", required=True, help="Path immagine pianta")
    parser.add_argument("--labels", required=True, help="Path labels.txt")
    parser.add_argument("--threads", type=int, default=4, help="Numero thread CPU per TFLite")
    parser.add_argument("--top-k", type=int, default=3, help="Numero classi top da restituire")
    parser.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )

    model_path = resolve_path(args.model)
    image_path = resolve_path(args.image)
    labels_path = resolve_path(args.labels)

    LOGGER.info("Model path: %s", model_path)
    LOGGER.info("Image path: %s", image_path)
    LOGGER.info("Labels path: %s", labels_path)

    labels = load_labels(labels_path)
    interpreter, input_details, output_details = make_interpreter(model_path, args.threads)

    input_shape = tuple(int(v) for v in input_details[0]["shape"][1:4])
    input_dtype = input_details[0]["dtype"]

    image_tensor = preprocess_image(image_path, input_shape, input_dtype)
    probabilities = run_inference(interpreter, input_details, output_details, image_tensor)
    result = decode_prediction(probabilities, labels, top_k=args.top_k)

    print("\n=== RISULTATO INFERENZA ===")
    print(f"Classe:      {result['class']}")
    print(f"Indice:      {result['class_index']}")
    print(f"Confidenza:  {result['confidence'] * 100:.2f}%")
    print("Top classi:")
    for item in result["top_k"]:
        print(f"  - {item['class']}: {item['confidence'] * 100:.2f}%")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
