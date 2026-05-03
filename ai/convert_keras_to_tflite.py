"""
Conversione modello TensorFlow/Keras in TensorFlow Lite.
Supporta quantizzazione: none, dynamic, float16, int8.

Esempio (float16 consigliato):
    python ai/convert_keras_to_tflite.py \
      --keras-model models/plant_disease_model.keras \
    --output models/plant_disease_model_39classes.tflite \
    --quantization float16
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import Iterator

import numpy as np

LOGGER = logging.getLogger("delta.ai.convert")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Conversione Keras -> TFLite")
    parser.add_argument("--keras-model", required=True, help="Path modello Keras (.keras o SavedModel)")
    parser.add_argument("--output", required=True, help="Path output .tflite")
    parser.add_argument("--quantization", default="float16", choices=["none", "dynamic", "float16", "int8"])
    parser.add_argument("--representative-data", default="datasets/training", help="Dataset per quantizzazione INT8")
    parser.add_argument("--img-size", type=int, default=224, help="Dimensione immagine input")
    parser.add_argument("--num-samples", type=int, default=200, help="Campioni representative dataset")
    parser.add_argument("--allow-float-fallback", action="store_true", help="Permette fallback float se alcune ops non sono INT8")
    parser.add_argument("--labels", default="models/labels_33classes_correct.txt", help="Path labels da validare/copiare")
    parser.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    return parser


def image_file_iter(dataset_root: Path) -> Iterator[Path]:
    exts = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff"}
    for p in dataset_root.rglob("*"):
        if p.is_file() and p.suffix.lower() in exts:
            yield p


def make_representative_dataset(dataset_root: Path, img_size: int, max_samples: int):
    try:
        import cv2  # type: ignore
    except ImportError as exc:
        raise RuntimeError("OpenCV richiesto per representative dataset") from exc

    files = list(image_file_iter(dataset_root))
    if not files:
        raise RuntimeError(f"Nessuna immagine trovata in representative dataset: {dataset_root}")

    selected = files[:max_samples]

    def representative_data_gen():
        for img_path in selected:
            image = cv2.imread(str(img_path), cv2.IMREAD_COLOR)
            if image is None:
                continue
            image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            image = cv2.resize(image, (img_size, img_size), interpolation=cv2.INTER_AREA)
            image = image.astype(np.float32)
            image = np.expand_dims(image, axis=0)
            yield [image]

    return representative_data_gen


def main() -> int:
    args = build_parser().parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )

    keras_model_path = Path(args.keras_model).resolve()
    output_path = Path(args.output).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    rep_data_path = Path(args.representative_data).resolve()
    labels_path = Path(args.labels).resolve()

    if not keras_model_path.exists():
        raise RuntimeError(f"Modello Keras non trovato: {keras_model_path}")

    try:
        import tensorflow as tf  # type: ignore
    except ImportError as exc:
        raise RuntimeError("TensorFlow non installato. Installare con: pip install tensorflow") from exc

    LOGGER.info("Caricamento modello Keras: %s", keras_model_path)
    model = tf.keras.models.load_model(keras_model_path)
    converter = tf.lite.TFLiteConverter.from_keras_model(model)

    if args.quantization == "dynamic":
        converter.optimizations = [tf.lite.Optimize.DEFAULT]
    elif args.quantization == "float16":
        converter.optimizations = [tf.lite.Optimize.DEFAULT]
        converter.target_spec.supported_types = [tf.float16]
    elif args.quantization == "int8":
        converter.optimizations = [tf.lite.Optimize.DEFAULT]
        converter.representative_dataset = make_representative_dataset(
            rep_data_path,
            img_size=args.img_size,
            max_samples=args.num_samples,
        )
        converter.inference_input_type = tf.uint8
        converter.inference_output_type = tf.uint8
        if args.allow_float_fallback:
            converter.target_spec.supported_ops = [
                tf.lite.OpsSet.TFLITE_BUILTINS_INT8,
                tf.lite.OpsSet.TFLITE_BUILTINS,
            ]
        else:
            converter.target_spec.supported_ops = [tf.lite.OpsSet.TFLITE_BUILTINS_INT8]

    tflite_model = converter.convert()
    output_path.write_bytes(tflite_model)

    size_mb = output_path.stat().st_size / (1024 * 1024)
    LOGGER.info("Modello TFLite salvato: %s (%.2f MB)", output_path, size_mb)

    if labels_path.exists() and labels_path.is_file():
        target_labels = output_path.parent / "labels_33classes_correct.txt"
        target_labels.write_text(labels_path.read_text(encoding="utf-8"), encoding="utf-8")
        LOGGER.info("labels copiato in: %s", target_labels)
    else:
        LOGGER.warning("file labels non trovato in %s (salto copia)", labels_path)

    print("\n=== CONVERSIONE COMPLETATA ===")
    print(f"Output TFLite: {output_path}")
    print(f"Quantization:  {args.quantization}")
    print(f"File size:     {size_mb:.2f} MB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
