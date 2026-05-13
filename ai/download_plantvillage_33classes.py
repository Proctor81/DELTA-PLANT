"""
DELTA - ai/download_plantvillage_33classes.py
Downloader del dataset PlantVillage leaf-only a 33 classi in layout ImageFolder.

Output atteso:
    datasets/training_33classes/
      train/<classe>/*.jpg
      validation/<classe>/*.jpg

Strategia multi-sorgente:
  1. tensorflow-datasets (plant_village)
  2. Hugging Face Datasets (salathe/plantvillage)
  3. GitHub raw (fallback, potenzialmente incompleto oltre 1000 file/cartella)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import shutil
import subprocess
import tempfile
import time
import urllib.request
from collections import defaultdict
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterable

import numpy as np

LOGGER = logging.getLogger("delta.ai.download_plantvillage33")


# Mapping DELTA 33 classi -> cartelle PlantVillage originali.
# Italian/English note:
# We keep DELTA label names stable and only map source dataset folders here.
DELTA33_TO_PLANTVILLAGE: dict[str, str] = {
    "Apple_Apple_scab": "Apple___Apple_scab",
    "Apple_Black_rot": "Apple___Black_rot",
    "Apple_Cedar_apple_rust": "Apple___Cedar_apple_rust",
    "Apple_healthy": "Apple___healthy",
    "Bell_pepper_Bacterial_spot": "Pepper,_bell___Bacterial_spot",
    "Bell_pepper_healthy": "Pepper,_bell___healthy",
    "Blueberry_healthy": "Blueberry___healthy",
    "Cherry_Powdery_mildew": "Cherry_(including_sour)___Powdery_mildew",
    "Cherry_healthy": "Cherry_(including_sour)___healthy",
    "Corn_Cercospora": "Corn_(maize)___Cercospora_leaf_spot Gray_leaf_spot",
    "Corn_Common_rust": "Corn_(maize)___Common_rust_",
    "Corn_Northern_Leaf_Blight": "Corn_(maize)___Northern_Leaf_Blight",
    "Corn_healthy": "Corn_(maize)___healthy",
    "Grape_Black_rot": "Grape___Black_rot",
    "Grape_Esca": "Grape___Esca_(Black_Measles)",
    "Grape_Leaf_blight": "Grape___Leaf_blight_(Isariopsis_Leaf_Spot)",
    "Grape_healthy": "Grape___healthy",
    "Peach_healthy": "Peach___healthy",
    "Potato_Early_blight": "Potato___Early_blight",
    "Potato_Late_blight": "Potato___Late_blight",
    "Potato_healthy": "Potato___healthy",
    "Squash_Powdery_mildew": "Squash___Powdery_mildew",
    "Strawberry_Leaf_scorch": "Strawberry___Leaf_scorch",
    "Strawberry_healthy": "Strawberry___healthy",
    "Tomato_Bacterial_spot": "Tomato___Bacterial_spot",
    "Tomato_Early_blight": "Tomato___Early_blight",
    "Tomato_Late_blight": "Tomato___Late_blight",
    "Tomato_Leaf_Mold": "Tomato___Leaf_Mold",
    "Tomato_Septoria_leaf_spot": "Tomato___Septoria_leaf_spot",
    "Tomato_Target_Spot": "Tomato___Target_Spot",
    "Tomato_Yellow_Leaf_Curl": "Tomato___Tomato_Yellow_Leaf_Curl_Virus",
    "Tomato_healthy": "Tomato___healthy",
    "Tomato_mosaic_virus": "Tomato___Tomato_mosaic_virus",
}

PLANTVILLAGE_TO_DELTA33: dict[str, str] = {
    folder: label for label, folder in DELTA33_TO_PLANTVILLAGE.items()
}

GITHUB_API = "https://api.github.com/repos/spMohanty/PlantVillage-Dataset/contents/raw/color/{folder}"
GITHUB_TREE_API = "https://api.github.com/repos/spMohanty/PlantVillage-Dataset/git/trees/master?recursive=1"
GITHUB_RAW = "https://raw.githubusercontent.com/spMohanty/PlantVillage-Dataset/master/raw/color/{folder}/{file}"
GITHUB_HEADERS = {
    "User-Agent": "DELTA-PLANT/PlantVillage33Downloader",
    "Accept": "application/vnd.github.v3+json",
}
_GITHUB_TREE_CACHE: list[str] | None = None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Scarica PlantVillage leaf-only a 33 classi")
    parser.add_argument("--output", default="datasets/training_33classes", help="Root output dataset")
    parser.add_argument("--source", choices=["auto", "tfds", "hf", "github"], default="auto")
    parser.add_argument("--img-size", type=int, default=224, help="Resize target quadrato")
    parser.add_argument("--validation-ratio", type=float, default=0.2, help="Quota validation per classe")
    parser.add_argument("--max-per-class", type=int, default=0, help="Limite immagini per classe (0 = tutte)")
    parser.add_argument("--missing-only", action="store_true", help="Scarica solo le classi ancora assenti nell'output")
    parser.add_argument("--clean", action="store_true", help="Pulisce l'output prima del download")
    parser.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    return parser


def _ensure_cv2():
    try:
        import cv2  # type: ignore
        return cv2
    except ImportError as exc:
        raise RuntimeError("OpenCV richiesto per scrivere le immagini del dataset") from exc


def _save_rgb_image(image_rgb: np.ndarray, destination: Path, img_size: int) -> None:
    cv2 = _ensure_cv2()
    destination.parent.mkdir(parents=True, exist_ok=True)
    resized = cv2.resize(image_rgb, (img_size, img_size), interpolation=cv2.INTER_AREA)
    bgr = cv2.cvtColor(resized, cv2.COLOR_RGB2BGR)
    ok = cv2.imwrite(str(destination), bgr)
    if not ok:
        raise RuntimeError(f"Impossibile salvare immagine dataset: {destination}")


def _stable_split(label: str, image_rgb: np.ndarray, validation_ratio: float) -> str:
    """Split deterministico per mantenere coerenza tra riesecuzioni."""
    digest = hashlib.sha1(label.encode("utf-8") + image_rgb.tobytes()).digest()
    bucket = int.from_bytes(digest[:4], "big") / 0xFFFFFFFF
    return "validation" if bucket < validation_ratio else "train"


def _scan_existing(output_root: Path) -> dict[str, dict[str, int]]:
    counts: dict[str, dict[str, int]] = defaultdict(lambda: {"train": 0, "validation": 0, "total": 0})
    for split_name in ("train", "validation"):
        split_dir = output_root / split_name
        if not split_dir.exists():
            continue
        for class_dir in split_dir.iterdir():
            if not class_dir.is_dir():
                continue
            n = sum(1 for path in class_dir.iterdir() if path.suffix.lower() in {".jpg", ".jpeg", ".png"})
            counts[class_dir.name][split_name] = n
            counts[class_dir.name]["total"] += n
    return counts


def _next_filename(class_label: str, current_total: int) -> str:
    return f"{class_label}_{current_total:06d}.jpg"


def _write_manifest(output_root: Path, source: str, counts: dict[str, dict[str, int]], img_size: int, validation_ratio: float) -> None:
    manifest = {
        "source": source,
        "img_size": img_size,
        "validation_ratio": validation_ratio,
        "counts": counts,
        "n_classes": len([label for label in counts if counts[label].get("total", 0) > 0]),
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    (output_root / "download_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def _merge_source_labels(existing_source: str, requested_source: str, used_sources: list[str]) -> str:
    ordered_sources: list[str] = []
    for label in [existing_source, *used_sources, requested_source]:
        if not label:
            continue
        for item in str(label).split(","):
            value = item.strip()
            if not value or value == "auto":
                continue
            if value not in ordered_sources:
                ordered_sources.append(value)
    return ",".join(ordered_sources) or "existing"


def _read_existing_manifest_source(output_root: Path) -> str:
    manifest_path = output_root / "download_manifest.json"
    if not manifest_path.exists():
        return ""
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception:
        return ""
    return str(manifest.get("source", "") or "")


def _log_counts(counts: dict[str, dict[str, int]]) -> None:
    total_images = 0
    LOGGER.info("Riepilogo dataset 33 classi:")
    for label in sorted(DELTA33_TO_PLANTVILLAGE):
        stats = counts.get(label, {"train": 0, "validation": 0, "total": 0})
        total_images += stats.get("total", 0)
        LOGGER.info(
            "  %-28s train=%4d  val=%4d  total=%4d",
            label,
            stats.get("train", 0),
            stats.get("validation", 0),
            stats.get("total", 0),
        )
    LOGGER.info("Totale immagini salvate: %d", total_images)


def _missing_labels(counts: dict[str, dict[str, int]]) -> set[str]:
    return {
        label
        for label in DELTA33_TO_PLANTVILLAGE
        if counts.get(label, {}).get("total", 0) == 0
    }


def _ingest_sample(
    output_root: Path,
    counts: dict[str, dict[str, int]],
    class_label: str,
    image_rgb: np.ndarray,
    img_size: int,
    validation_ratio: float,
    max_per_class: int,
) -> bool:
    if image_rgb is None or image_rgb.size == 0:
        return False

    if max_per_class > 0 and counts[class_label]["total"] >= max_per_class:
        return False

    split_name = _stable_split(class_label, image_rgb, validation_ratio)
    filename = _next_filename(class_label, counts[class_label]["total"])
    destination = output_root / split_name / class_label / filename
    _save_rgb_image(image_rgb, destination, img_size)

    counts[class_label][split_name] += 1
    counts[class_label]["total"] += 1
    return True


def download_via_tfds(
    output_root: Path,
    counts: dict[str, dict[str, int]],
    img_size: int,
    validation_ratio: float,
    max_per_class: int,
    target_labels: set[str],
) -> bool:
    LOGGER.info("Tentativo download 33 classi tramite tensorflow-datasets...")
    try:
        import tensorflow_datasets as tfds  # type: ignore
    except ImportError as exc:
        LOGGER.warning("tensorflow_datasets non disponibile: %s", exc)
        return False

    try:
        dataset, info = tfds.load("plant_village", split="train", with_info=True, as_supervised=True)
    except Exception as exc:
        LOGGER.warning("TFDS non utilizzabile in questa esecuzione: %s", exc)
        return False
    label_names: list[str] = list(info.features["label"].names)

    saved = 0
    for image_tensor, label_tensor in dataset:
        raw_label = label_names[int(label_tensor.numpy())]
        class_label = PLANTVILLAGE_TO_DELTA33.get(raw_label)
        if class_label is None or class_label not in target_labels:
            continue
        image_rgb = image_tensor.numpy()
        if _ingest_sample(output_root, counts, class_label, image_rgb, img_size, validation_ratio, max_per_class):
            saved += 1

    LOGGER.info("TFDS completato: %d immagini nuove salvate", saved)
    return saved > 0


def _resolve_hf_label(item: dict[str, Any], label_names: list[str]) -> str:
    raw_label = item.get("label")
    if isinstance(raw_label, int) and label_names:
        return label_names[raw_label]
    if isinstance(raw_label, str):
        return raw_label
    if isinstance(item.get("class_name"), str):
        return str(item["class_name"])
    return ""


def _hf_image_to_numpy(image_obj: Any) -> np.ndarray | None:
    if image_obj is None:
        return None
    if isinstance(image_obj, np.ndarray):
        image = image_obj
    else:
        try:
            image = np.asarray(image_obj)
        except Exception:
            return None
    if image.ndim != 3:
        return None
    if image.shape[2] == 4:
        return image[:, :, :3]
    return image


def _local_image_to_numpy(image_path: Path) -> np.ndarray | None:
    cv2 = _ensure_cv2()
    image_bgr = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
    if image_bgr is None:
        return None
    return cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)


@contextmanager
def _github_sparse_checkout(folders: Iterable[str]):
    with tempfile.TemporaryDirectory(prefix="delta_plantvillage_") as temp_dir:
        repo_dir = Path(temp_dir) / "PlantVillage-Dataset"
        clone_cmd = [
            "git",
            "clone",
            "--depth",
            "1",
            "--filter=blob:none",
            "--sparse",
            "https://github.com/spMohanty/PlantVillage-Dataset.git",
            str(repo_dir),
        ]
        sparse_cmd = [
            "git",
            "-C",
            str(repo_dir),
            "sparse-checkout",
            "set",
            "--no-cone",
            *[f"raw/color/{folder}" for folder in folders],
        ]
        subprocess.run(clone_cmd, check=True, capture_output=True, text=True)
        subprocess.run(sparse_cmd, check=True, capture_output=True, text=True)
        yield repo_dir


def _download_via_github_sparse_checkout(
    output_root: Path,
    counts: dict[str, dict[str, int]],
    img_size: int,
    validation_ratio: float,
    max_per_class: int,
    target_labels: set[str],
) -> int:
    folders = [DELTA33_TO_PLANTVILLAGE[label] for label in sorted(target_labels)]
    saved = 0
    with _github_sparse_checkout(folders) as repo_dir:
        for class_label in sorted(target_labels):
            folder = DELTA33_TO_PLANTVILLAGE[class_label]
            source_dir = repo_dir / "raw" / "color" / folder
            if not source_dir.exists():
                LOGGER.warning("Cartella non trovata nello sparse checkout GitHub: %s", source_dir)
                continue
            image_paths = sorted(
                path for path in source_dir.iterdir() if path.is_file() and path.suffix.lower() in {".jpg", ".jpeg", ".png"}
            )
            for image_path in image_paths:
                if max_per_class > 0 and counts[class_label]["total"] >= max_per_class:
                    break
                image_rgb = _local_image_to_numpy(image_path)
                if image_rgb is None:
                    continue
                if _ingest_sample(output_root, counts, class_label, image_rgb, img_size, validation_ratio, max_per_class):
                    saved += 1
    return saved


def download_via_hf(
    output_root: Path,
    counts: dict[str, dict[str, int]],
    img_size: int,
    validation_ratio: float,
    max_per_class: int,
    target_labels: set[str],
) -> bool:
    LOGGER.info("Tentativo download 33 classi tramite Hugging Face Datasets...")
    try:
        from datasets import load_dataset  # type: ignore
    except ImportError as exc:
        LOGGER.warning("datasets non disponibile: %s", exc)
        return False

    try:
        ds = load_dataset("salathe/plantvillage", split="train", trust_remote_code=False)
    except Exception as exc:
        LOGGER.warning("Hugging Face non utilizzabile in questa esecuzione: %s", exc)
        return False
    label_feature = ds.features.get("label") if hasattr(ds, "features") else None
    label_names = list(getattr(label_feature, "names", []) or [])

    saved = 0
    for item in ds:
        raw_label = _resolve_hf_label(item, label_names)
        class_label = PLANTVILLAGE_TO_DELTA33.get(raw_label)
        if class_label is None or class_label not in target_labels:
            continue
        image_rgb = _hf_image_to_numpy(item.get("image") or item.get("img"))
        if image_rgb is None:
            continue
        if _ingest_sample(output_root, counts, class_label, image_rgb, img_size, validation_ratio, max_per_class):
            saved += 1

    LOGGER.info("Hugging Face completato: %d immagini nuove salvate", saved)
    return saved > 0


def _github_list_files(folder: str) -> list[str]:
    global _GITHUB_TREE_CACHE

    if _GITHUB_TREE_CACHE is None:
        try:
            req = urllib.request.Request(GITHUB_TREE_API, headers=GITHUB_HEADERS)
            with urllib.request.urlopen(req, timeout=60) as response:
                payload = json.loads(response.read())
            tree_items = payload.get("tree", [])
            _GITHUB_TREE_CACHE = [
                item["path"]
                for item in tree_items
                if item.get("type") == "blob" and item.get("path", "").lower().endswith(".jpg")
            ]
            if payload.get("truncated"):
                LOGGER.warning("GitHub tree API ha risposto in forma troncata; uso fallback contents API")
                _GITHUB_TREE_CACHE = None
        except Exception as exc:
            LOGGER.warning("GitHub tree API non disponibile: %s", exc)
            _GITHUB_TREE_CACHE = None

    if _GITHUB_TREE_CACHE is not None:
        prefix = f"raw/color/{folder}/"
        files = [path.rsplit("/", 1)[-1] for path in _GITHUB_TREE_CACHE if path.startswith(prefix)]
        if files:
            return files

    url = GITHUB_API.format(folder=urllib.request.quote(folder))
    req = urllib.request.Request(url, headers=GITHUB_HEADERS)
    with urllib.request.urlopen(req, timeout=30) as response:
        items = json.loads(response.read())
    files = [item["name"] for item in items if item.get("type") == "file" and item["name"].lower().endswith(".jpg")]
    if len(files) >= 1000:
        LOGGER.warning("GitHub contents API ha restituito 1000 file per %s: fallback potenzialmente incompleto", folder)
    return files


def _github_download_image(folder: str, filename: str) -> np.ndarray | None:
    cv2 = _ensure_cv2()
    url = GITHUB_RAW.format(folder=urllib.request.quote(folder), file=urllib.request.quote(filename))
    req = urllib.request.Request(url, headers={"User-Agent": GITHUB_HEADERS["User-Agent"]})
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            data = response.read()
    except Exception:
        return None
    if len(data) < 1000:
        return None
    buffer = np.frombuffer(data, dtype=np.uint8)
    image_bgr = cv2.imdecode(buffer, cv2.IMREAD_COLOR)
    if image_bgr is None:
        return None
    return cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)


def download_via_github(
    output_root: Path,
    counts: dict[str, dict[str, int]],
    img_size: int,
    validation_ratio: float,
    max_per_class: int,
    target_labels: set[str],
) -> bool:
    LOGGER.info("Tentativo download 33 classi tramite GitHub raw...")
    saved = 0
    try:
        saved += _download_via_github_sparse_checkout(
            output_root,
            counts,
            img_size,
            validation_ratio,
            max_per_class,
            target_labels,
        )
        if saved > 0:
            LOGGER.info("GitHub sparse checkout completato: %d immagini nuove salvate", saved)
    except Exception as exc:
        LOGGER.warning("GitHub sparse checkout non disponibile: %s", exc)

    remaining_labels = target_labels & _missing_labels(counts)
    if not remaining_labels:
        LOGGER.info("GitHub raw completato: %d immagini nuove salvate", saved)
        return saved > 0

    if saved > 0:
        LOGGER.info("Sparse checkout incompleto, provo API GitHub solo per le classi residue: %s", sorted(remaining_labels))

    for class_label, folder in DELTA33_TO_PLANTVILLAGE.items():
        if class_label not in remaining_labels:
            continue
        try:
            filenames = _github_list_files(folder)
        except Exception as exc:
            LOGGER.warning("Lista file GitHub fallita per %s: %s", class_label, exc)
            continue

        for filename in filenames:
            if max_per_class > 0 and counts[class_label]["total"] >= max_per_class:
                break
            image_rgb = _github_download_image(folder, filename)
            if image_rgb is None:
                continue
            if _ingest_sample(output_root, counts, class_label, image_rgb, img_size, validation_ratio, max_per_class):
                saved += 1

    LOGGER.info("GitHub raw completato: %d immagini nuove salvate", saved)
    return saved > 0


def _attempt_sources(
    source: str,
    output_root: Path,
    counts: dict[str, dict[str, int]],
    img_size: int,
    validation_ratio: float,
    max_per_class: int,
    missing_only: bool,
) -> list[str]:
    ordered_sources: list[tuple[str, Any]] = [
        ("tfds", download_via_tfds),
        ("hf", download_via_hf),
        ("github", download_via_github),
    ]
    if source != "auto":
        ordered_sources = [item for item in ordered_sources if item[0] == source]

    used_sources: list[str] = []
    for source_name, handler in ordered_sources:
        target_labels = _missing_labels(counts) if (source == "auto" or missing_only) else set(DELTA33_TO_PLANTVILLAGE)
        if not target_labels:
            break
        if handler(output_root, counts, img_size, validation_ratio, max_per_class, target_labels):
            used_sources.append(source_name)
            if source != "auto":
                break
    return used_sources


def main() -> int:
    args = build_parser().parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )

    output_root = Path(args.output).resolve()
    if args.clean and output_root.exists():
        LOGGER.warning("Pulizia output esistente: %s", output_root)
        shutil.rmtree(output_root)

    (output_root / "train").mkdir(parents=True, exist_ok=True)
    (output_root / "validation").mkdir(parents=True, exist_ok=True)

    counts = _scan_existing(output_root)
    used_sources = _attempt_sources(
        source=args.source,
        output_root=output_root,
        counts=counts,
        img_size=args.img_size,
        validation_ratio=args.validation_ratio,
        max_per_class=args.max_per_class,
        missing_only=args.missing_only,
    )

    existing_source = _read_existing_manifest_source(output_root)
    if not used_sources:
        if not _missing_labels(counts):
            source_label = _merge_source_labels(existing_source, args.source, used_sources)
            LOGGER.info("Dataset gia completo: aggiorno solo il manifest")
            _log_counts(counts)
            _write_manifest(output_root, source_label, counts, args.img_size, args.validation_ratio)
            print("\n=== DATASET 33 CLASSI COMPLETATO ===")
            print(f"Output:   {output_root}")
            print(f"Sorgente: {source_label}")
            print(f"Classi:   {len([label for label in counts if counts[label].get('total', 0) > 0])}")
            print(f"Manifest: {output_root / 'download_manifest.json'}")
            return 0
        LOGGER.error("Nessuna sorgente ha prodotto immagini per il dataset 33 classi")
        return 1

    _log_counts(counts)
    source_label = _merge_source_labels(existing_source, args.source, used_sources)
    _write_manifest(output_root, source_label, counts, args.img_size, args.validation_ratio)

    missing = [label for label in DELTA33_TO_PLANTVILLAGE if counts.get(label, {}).get("total", 0) == 0]
    if missing:
        LOGGER.warning("Classi mancanti nel dataset risultante: %s", missing)
    else:
        LOGGER.info("Tutte le 33 classi risultano presenti nel dataset locale")

    print("\n=== DATASET 33 CLASSI COMPLETATO ===")
    print(f"Output:   {output_root}")
    print(f"Sorgente: {source_label}")
    print(f"Classi:   {len([label for label in counts if counts[label].get('total', 0) > 0])}")
    print(f"Manifest: {output_root / 'download_manifest.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())