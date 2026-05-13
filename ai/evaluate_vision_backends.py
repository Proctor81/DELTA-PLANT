"""
Valutazione dettagliata su validation set PlantVillage per backend DELTA.

Output prodotti:
- comparison_summary.json
- <model_key>_predictions.csv
- <model_key>_confusion_matrix.csv
- <model_key>_classification_report.json
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import sys
from pathlib import Path
from typing import Any

from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, f1_score

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from vision.vision_service import VisionService

LOGGER = logging.getLogger("delta.ai.evaluate")

FOLDER_TO_CLASS = {
    "Apple___Apple_scab": "Apple_Apple_scab",
    "Apple___Black_rot": "Apple_Black_rot",
    "Apple___Cedar_apple_rust": "Apple_Cedar_apple_rust",
    "Apple___healthy": "Apple_healthy",
    "Pepper,_bell___Bacterial_spot": "Bell_pepper_Bacterial_spot",
    "Pepper,_bell___healthy": "Bell_pepper_healthy",
    "Blueberry___healthy": "Blueberry_healthy",
    "Cherry_(including_sour)___Powdery_mildew": "Cherry_Powdery_mildew",
    "Cherry_(including_sour)___healthy": "Cherry_healthy",
    "Corn_(maize)___Cercospora_leaf_spot Gray_leaf_spot": "Corn_Cercospora",
    "Corn_(maize)___Common_rust_": "Corn_Common_rust",
    "Corn_(maize)___Northern_Leaf_Blight": "Corn_Northern_Leaf_Blight",
    "Corn_(maize)___healthy": "Corn_healthy",
    "Grape___Black_rot": "Grape_Black_rot",
    "Grape___Esca_(Black_Measles)": "Grape_Esca",
    "Grape___Leaf_blight_(Isariopsis_Leaf_Spot)": "Grape_Leaf_blight",
    "Grape___healthy": "Grape_healthy",
    "Peach___healthy": "Peach_healthy",
    "Potato___Early_blight": "Potato_Early_blight",
    "Potato___Late_blight": "Potato_Late_blight",
    "Potato___healthy": "Potato_healthy",
    "Squash___Powdery_mildew": "Squash_Powdery_mildew",
    "Strawberry___Leaf_scorch": "Strawberry_Leaf_scorch",
    "Strawberry___healthy": "Strawberry_healthy",
    "Tomato___Bacterial_spot": "Tomato_Bacterial_spot",
    "Tomato___Early_blight": "Tomato_Early_blight",
    "Tomato___Late_blight": "Tomato_Late_blight",
    "Tomato___Leaf_Mold": "Tomato_Leaf_Mold",
    "Tomato___Septoria_leaf_spot": "Tomato_Septoria_leaf_spot",
    "Tomato___Target_Spot": "Tomato_Target_Spot",
    "Tomato___Tomato_Yellow_Leaf_Curl_Virus": "Tomato_Yellow_Leaf_Curl",
    "Tomato___healthy": "Tomato_healthy",
    "Tomato___Tomato_mosaic_virus": "Tomato_mosaic_virus",
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Valutazione accuracy/F1/confusion matrix backend vision DELTA")
    parser.add_argument("--dataset-root", default="datasets/training/validation", help="Validation set ImageFolder")
    parser.add_argument("--model-keys", nargs="+", default=["generale", "efficientformer"], help="Model keys da confrontare")
    parser.add_argument("--limit-per-class", type=int, default=0, help="Limita il numero di immagini per classe (0 = tutte)")
    parser.add_argument("--output-dir", default="logs/vision_eval", help="Directory report")
    parser.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    return parser


def _normalize_folder_name(folder_name: str) -> str:
    return FOLDER_TO_CLASS.get(folder_name, folder_name.replace("___", "_").replace(" ", "_"))


def _iter_validation_images(dataset_root: Path, limit_per_class: int):
    exts = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff"}
    for class_dir in sorted(path for path in dataset_root.iterdir() if path.is_dir()):
        gt_label = _normalize_folder_name(class_dir.name)
        files = [path for path in sorted(class_dir.iterdir()) if path.suffix.lower() in exts]
        if limit_per_class > 0:
            files = files[:limit_per_class]
        for image_path in files:
            yield gt_label, image_path


def _write_csv(path: Path, headers: list[str], rows: list[list[Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(headers)
        writer.writerows(rows)


def evaluate_model(model_key: str, dataset_root: Path, limit_per_class: int, output_dir: Path) -> dict[str, Any]:
    service = VisionService(model_key=model_key)
    if not service.is_ready:
        raise RuntimeError(f"Backend non pronto per {model_key}")

    y_true: list[str] = []
    y_pred: list[str] = []
    confidences: list[float] = []
    top3_hits = 0
    prediction_rows: list[list[Any]] = []

    for gt_label, image_path in _iter_validation_images(dataset_root, limit_per_class):
        result = service.classify(str(image_path))
        predicted = str(result.get("class", "errore"))
        confidence = float(result.get("confidence", 0.0))
        top3 = [str(item.get("class", "")) for item in result.get("top3", [])]
        top3_hit = gt_label in top3

        y_true.append(gt_label)
        y_pred.append(predicted)
        confidences.append(confidence)
        top3_hits += int(top3_hit)
        prediction_rows.append([
            image_path.name,
            gt_label,
            predicted,
            round(confidence, 6),
            int(top3_hit),
            json.dumps(result.get("top3", []), ensure_ascii=False),
        ])

    labels = sorted(set(y_true) | set(y_pred))
    accuracy = accuracy_score(y_true, y_pred) if y_true else 0.0
    macro_f1 = f1_score(y_true, y_pred, average="macro", zero_division=0) if y_true else 0.0
    matrix = confusion_matrix(y_true, y_pred, labels=labels)
    report = classification_report(y_true, y_pred, labels=labels, output_dict=True, zero_division=0)
    summary = {
        "model_key": model_key,
        "active_model": service.active_model,
        "backend": service.backend_type,
        "samples": len(y_true),
        "accuracy_top1": accuracy,
        "accuracy_top3": (top3_hits / len(y_true)) if y_true else 0.0,
        "macro_f1": macro_f1,
        "mean_confidence": (sum(confidences) / len(confidences)) if confidences else 0.0,
    }

    _write_csv(
        output_dir / f"{model_key}_predictions.csv",
        ["file", "ground_truth", "prediction", "confidence", "top3_hit", "top3"],
        prediction_rows,
    )
    _write_csv(
        output_dir / f"{model_key}_confusion_matrix.csv",
        ["ground_truth\\prediction", *labels],
        [[label, *row.tolist()] for label, row in zip(labels, matrix)],
    )
    (output_dir / f"{model_key}_classification_report.json").write_text(
        json.dumps(report, indent=2),
        encoding="utf-8",
    )
    (output_dir / f"{model_key}_summary.json").write_text(
        json.dumps(summary, indent=2),
        encoding="utf-8",
    )
    return summary


def main() -> int:
    args = build_parser().parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )

    dataset_root = Path(args.dataset_root).resolve()
    if not dataset_root.exists():
        raise RuntimeError(f"Validation set non trovato: {dataset_root}")

    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    comparison: list[dict[str, Any]] = []

    for model_key in args.model_keys:
        LOGGER.info("Valutazione backend %s...", model_key)
        comparison.append(evaluate_model(model_key, dataset_root, args.limit_per_class, output_dir))

    comparison_path = output_dir / "comparison_summary.json"
    comparison_path.write_text(json.dumps(comparison, indent=2), encoding="utf-8")
    print(json.dumps(comparison, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
