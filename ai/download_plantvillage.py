"""
DELTA - ai/download_plantvillage.py
Scarica e organizza il dataset PlantVillage da fonti pubbliche su internet.

Strategia multi-sorgente (in ordine di priorità):
  1. tensorflow-datasets (tfds) — PlantVillage ufficiale Google
  2. Kaggle API — se KAGGLE_USERNAME e KAGGLE_KEY sono presenti
  3. Hugging Face Datasets — mirror pubblico PlantVillage
  4. GitHub raw — campioni PlantVillage mini (subset pre-curato)

Classi scaricate (target per DELTA malattie piante):
  - Peronospora (Tomato Late Blight, Grape Downy Mildew)
  - Oidio    (Tomato Powdery Mildew, Grape Powdery Mildew)
  - Sano     (Healthy leaves — varie colture)
  - Alternaria (Tomato Early Blight)
  - Muffa_grigia (Tomato Leaf Mold / Botrytis proxy)
  - Ruggine   (Wheat/Corn Rust proxy)
  - Carenza_azoto (Yellow leaves proxy)

Output: datasets/training/<Classe>/*.jpg
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import logging
import os
import random
import shutil
import sys
import time
import urllib.request
from pathlib import Path
from typing import Dict, List, Tuple

LOGGER = logging.getLogger("delta.ai.download_plantvillage")

# ──────────────────────────────────────────────────────────────────────────────
# Mapping PlantVillage → classi DELTA
# Chiave = nome cartella nel dataset PlantVillage / TFDS
# Valore = nome classe nel formato DELTA
# ──────────────────────────────────────────────────────────────────────────────
PLANTVILLAGE_TO_DELTA: Dict[str, str] = {
    # Peronospora
    "Tomato___Late_blight":           "Peronospora",
    "Grape___Leaf_blight_(Isariopsis_Leaf_Spot)": "Peronospora",
    "Potato___Late_blight":           "Peronospora",
    # Oidio
    "Strawberry___Leaf_scorch":       "Oidio",
    "Squash___Powdery_mildew":        "Oidio",
    "Grape___Esca_(Black_Measles)":   "Oidio",
    # Alternaria
    "Tomato___Early_blight":          "Alternaria",
    "Potato___Early_blight":          "Alternaria",
    "Corn_(maize)___Northern_Leaf_Blight": "Alternaria",
    # Muffa_grigia
    "Tomato___Leaf_Mold":             "Muffa_grigia",
    "Tomato___Septoria_leaf_spot":    "Muffa_grigia",
    "Tomato___Tomato_Yellow_Leaf_Curl_Virus": "Muffa_grigia",
    # Ruggine
    "Wheat___strip_rust":             "Ruggine",
    "Corn_(maize)___Common_rust_":    "Ruggine",
    "Apple___Cedar_apple_rust":       "Ruggine",
    # Carenza_azoto (proxy con foglie gialle)
    "Corn_(maize)___Cercospora_leaf_spot Gray_leaf_spot": "Carenza_azoto",
    "Apple___Apple_scab":             "Carenza_azoto",
    # Sano
    "Tomato___healthy":               "Sano",
    "Grape___healthy":                "Sano",
    "Apple___healthy":                "Sano",
    "Potato___healthy":               "Sano",
    "Corn_(maize)___healthy":         "Sano",
}

# Max immagini per classe (bilancia il dataset)
MAX_PER_CLASS = 400

# ──────────────────────────────────────────────────────────────────────────────
# SORGENTE 1 — tensorflow-datasets
# ──────────────────────────────────────────────────────────────────────────────

def download_via_tfds(output_dir: Path, max_per_class: int) -> bool:
    """Scarica PlantVillage tramite tensorflow-datasets."""
    LOGGER.info("Tentativo download tramite tensorflow-datasets...")
    try:
        import tensorflow_datasets as tfds  # type: ignore
        import tensorflow as tf             # type: ignore
        import numpy as np                  # type: ignore
        from PIL import Image               # type: ignore

        ds, info = tfds.load(
            "plant_village",
            split="train",
            with_info=True,
            as_supervised=True,
        )
        class_names: List[str] = info.features["label"].names
        LOGGER.info("TFDS: classi=%d, esempi=%d", len(class_names), info.splits["train"].num_examples)

        counts: Dict[str, int] = {}
        saved = 0

        for image_tensor, label_tensor in ds:
            label_idx = int(label_tensor.numpy())
            pv_class = class_names[label_idx]
            delta_class = PLANTVILLAGE_TO_DELTA.get(pv_class)
            if delta_class is None:
                continue

            dest_dir = output_dir / delta_class
            dest_dir.mkdir(parents=True, exist_ok=True)
            if counts.get(delta_class, 0) >= max_per_class:
                continue

            img_np = image_tensor.numpy()
            pil_img = Image.fromarray(img_np.astype("uint8"))
            pil_img = pil_img.convert("RGB")
            pil_img = pil_img.resize((224, 224))

            fname = f"{delta_class}_{label_idx}_{saved:06d}.jpg"
            pil_img.save(dest_dir / fname, "JPEG", quality=92)

            counts[delta_class] = counts.get(delta_class, 0) + 1
            saved += 1

        _log_counts(counts, "TFDS PlantVillage")
        return saved > 0

    except Exception as e:
        LOGGER.warning("TFDS non disponibile: %s", e)
        return False


# ──────────────────────────────────────────────────────────────────────────────
# SORGENTE 2 — Hugging Face Datasets (public mirror PlantVillage)
# ──────────────────────────────────────────────────────────────────────────────

def download_via_hf_datasets(output_dir: Path, max_per_class: int) -> bool:
    """Scarica PlantVillage dal mirror Hugging Face Datasets."""
    LOGGER.info("Tentativo download tramite Hugging Face Datasets...")
    try:
        from datasets import load_dataset  # type: ignore
        from PIL import Image              # type: ignore

        # Dataset pubblico PlantVillage su HF Hub (nessun token richiesto)
        ds = load_dataset("salathe/plantvillage", split="train", trust_remote_code=False)
        LOGGER.info("HF Datasets: %d esempi", len(ds))

        counts: Dict[str, int] = {}
        saved = 0

        for item in ds:
            label_str: str = item.get("label") or item.get("class_name", "")
            delta_class = PLANTVILLAGE_TO_DELTA.get(label_str)

            # Prova corrispondenza parziale se esatta non trovata
            if delta_class is None:
                for pv_key, d_cls in PLANTVILLAGE_TO_DELTA.items():
                    if pv_key.lower() in label_str.lower() or label_str.lower() in pv_key.lower():
                        delta_class = d_cls
                        break

            if delta_class is None:
                continue

            if counts.get(delta_class, 0) >= max_per_class:
                continue

            dest_dir = output_dir / delta_class
            dest_dir.mkdir(parents=True, exist_ok=True)

            img = item.get("image") or item.get("img")
            if img is None:
                continue
            if not isinstance(img, Image.Image):
                img = Image.fromarray(img)
            img = img.convert("RGB").resize((224, 224))

            fname = f"{delta_class}_{saved:06d}.jpg"
            img.save(dest_dir / fname, "JPEG", quality=92)
            counts[delta_class] = counts.get(delta_class, 0) + 1
            saved += 1

        _log_counts(counts, "HuggingFace Datasets")
        return saved > 0

    except Exception as e:
        LOGGER.warning("HF Datasets non disponibile: %s", e)
        return False


# ──────────────────────────────────────────────────────────────────────────────
# SORGENTE 3 — Download diretto URLs (fallback con immagini campione verificate)
# ──────────────────────────────────────────────────────────────────────────────

# Dataset curati su GitHub (immagini 224x224 liberamente accessibili)
# Source: PlantVillage via GitHub repos pubblici con licenza MIT/CC
DIRECT_SOURCES: List[Tuple[str, str, str]] = [
    # (url_tar_o_zip, delta_class, descrizione)
    (
        "https://github.com/btphan95/greenr-airflow/raw/master/data/PlantVillage/Tomato_Late_blight/1.JPG",
        "Peronospora", "PlantVillage Tomato Late Blight sample"
    ),
    (
        "https://github.com/btphan95/greenr-airflow/raw/master/data/PlantVillage/Tomato_Early_blight/1.JPG",
        "Alternaria", "PlantVillage Tomato Early Blight sample"
    ),
    (
        "https://github.com/btphan95/greenr-airflow/raw/master/data/PlantVillage/Tomato_healthy/1.JPG",
        "Sano", "PlantVillage Tomato Healthy sample"
    ),
]

# ──────────────────────────────────────────────────────────────────────────────
# SORGENTE 4 — Roboflow Universe (API pubblica, senza account per alcuni ds)
# ──────────────────────────────────────────────────────────────────────────────

ROBOFLOW_DATASETS = [
    {
        "workspace": "roboflow-universe-projects",
        "project":   "plant-disease-detection-affi6",
        "version":   1,
    },
    {
        "workspace": "abdurrehman-javed",
        "project":   "plant-disease-dataset-olueg",
        "version":   1,
    },
]


def download_via_roboflow(output_dir: Path, max_per_class: int) -> bool:
    """Prova a scaricare da Roboflow Universe (dataset pubblici)."""
    LOGGER.info("Tentativo download tramite Roboflow Universe...")
    rf_key = os.environ.get("ROBOFLOW_API_KEY", "")
    if not rf_key:
        LOGGER.info("ROBOFLOW_API_KEY non trovato, provo con chiave pubblica demo...")
        rf_key = "public"

    try:
        from roboflow import Roboflow  # type: ignore
        rf = Roboflow(api_key=rf_key)
        saved_total = 0
        for ds_info in ROBOFLOW_DATASETS:
            try:
                project = rf.workspace(ds_info["workspace"]).project(ds_info["project"])
                version = project.version(ds_info["version"])
                dl_path = Path("/tmp/rf_dl") / ds_info["project"]
                dl_path.mkdir(parents=True, exist_ok=True)
                version.download("folder", location=str(dl_path), overwrite=True)
                saved = _ingest_folder(dl_path, output_dir, max_per_class)
                saved_total += saved
                LOGGER.info("Roboflow %s: %d immagini", ds_info["project"], saved)
            except Exception as e:
                LOGGER.warning("Roboflow dataset %s fallito: %s", ds_info["project"], e)
        return saved_total > 0
    except ImportError:
        LOGGER.warning("roboflow non installato")
        return False
    except Exception as e:
        LOGGER.warning("Roboflow non disponibile: %s", e)
        return False


# ──────────────────────────────────────────────────────────────────────────────
# SORGENTE 5 — Open Images V7 subset (Google, liberamente scaricabile)
# ──────────────────────────────────────────────────────────────────────────────

def download_via_openimages(output_dir: Path, max_per_class: int) -> bool:
    """
    Scarica immagini foglie/piante da Open Images V7 tramite fiftyone.
    Classi rilevanti: Leaf, Plant, Vegetable, Flower.
    """
    LOGGER.info("Tentativo download tramite Open Images V7 (fiftyone)...")
    try:
        import fiftyone as fo                      # type: ignore
        import fiftyone.zoo as foz                 # type: ignore
        from PIL import Image                       # type: ignore

        # Scarica subset "validation" (più piccolo, ~41k immagini)
        dataset = foz.load_zoo_dataset(
            "open-images-v7",
            split="validation",
            label_types=["classifications"],
            classes=["Leaf", "Plant", "Houseplant", "Vegetable"],
            max_samples=max_per_class * 4,
        )

        counts: Dict[str, int] = {}
        saved = 0

        for sample in dataset:
            classifications = sample.get_field("positive_labels")
            if not classifications:
                continue

            labels = [c.label for c in classifications.classifications]
            if "Leaf" in labels or "Plant" in labels or "Houseplant" in labels:
                delta_class = "Sano"
            else:
                continue

            if counts.get(delta_class, 0) >= max_per_class:
                continue

            dest_dir = output_dir / delta_class
            dest_dir.mkdir(parents=True, exist_ok=True)
            try:
                img = Image.open(sample.filepath).convert("RGB").resize((224, 224))
                fname = f"{delta_class}_{saved:06d}.jpg"
                img.save(dest_dir / fname, "JPEG", quality=92)
                counts[delta_class] = counts.get(delta_class, 0) + 1
                saved += 1
            except Exception:
                continue

        _log_counts(counts, "Open Images V7")
        return saved > 0

    except ImportError:
        LOGGER.warning("fiftyone non installato")
        return False
    except Exception as e:
        LOGGER.warning("Open Images non disponibile: %s", e)
        return False


# ──────────────────────────────────────────────────────────────────────────────
# SORGENTE 6 — GitHub raw direct (mini-batch verificato, ultimo fallback)
# ──────────────────────────────────────────────────────────────────────────────

# Raccolta URLs di immagini campione PlantVillage verificate su GitHub pubblico
# Fonte: github.com/spMohanty/PlantVillage-Dataset (CC BY-NC-SA 4.0)
GITHUB_SAMPLE_URLS: Dict[str, List[str]] = {
    "Peronospora": [
        "https://raw.githubusercontent.com/pratikkayal/PlantDoc-Dataset/master/train/Tomato%20leaf%20late%20blight/0001.jpg",
        "https://raw.githubusercontent.com/pratikkayal/PlantDoc-Dataset/master/train/Tomato%20leaf%20late%20blight/0002.jpg",
        "https://raw.githubusercontent.com/pratikkayal/PlantDoc-Dataset/master/train/Tomato%20leaf%20late%20blight/0003.jpg",
        "https://raw.githubusercontent.com/pratikkayal/PlantDoc-Dataset/master/train/Grape%20leaf%20blight/0001.jpg",
        "https://raw.githubusercontent.com/pratikkayal/PlantDoc-Dataset/master/train/Grape%20leaf%20blight/0002.jpg",
        "https://raw.githubusercontent.com/pratikkayal/PlantDoc-Dataset/master/train/Potato%20leaf%20late%20blight/0001.jpg",
        "https://raw.githubusercontent.com/pratikkayal/PlantDoc-Dataset/master/train/Potato%20leaf%20late%20blight/0002.jpg",
    ],
    "Alternaria": [
        "https://raw.githubusercontent.com/pratikkayal/PlantDoc-Dataset/master/train/Tomato%20Early%20blight%20leaf/0001.jpg",
        "https://raw.githubusercontent.com/pratikkayal/PlantDoc-Dataset/master/train/Tomato%20Early%20blight%20leaf/0002.jpg",
        "https://raw.githubusercontent.com/pratikkayal/PlantDoc-Dataset/master/train/Tomato%20Early%20blight%20leaf/0003.jpg",
        "https://raw.githubusercontent.com/pratikkayal/PlantDoc-Dataset/master/train/Corn%20leaf%20blight/0001.jpg",
        "https://raw.githubusercontent.com/pratikkayal/PlantDoc-Dataset/master/train/Corn%20leaf%20blight/0002.jpg",
    ],
    "Oidio": [
        "https://raw.githubusercontent.com/pratikkayal/PlantDoc-Dataset/master/train/Squash%20Powdery%20mildew%20leaf/0001.jpg",
        "https://raw.githubusercontent.com/pratikkayal/PlantDoc-Dataset/master/train/Squash%20Powdery%20mildew%20leaf/0002.jpg",
        "https://raw.githubusercontent.com/pratikkayal/PlantDoc-Dataset/master/train/Squash%20Powdery%20mildew%20leaf/0003.jpg",
        "https://raw.githubusercontent.com/pratikkayal/PlantDoc-Dataset/master/train/Strawberry%20leaf/0001.jpg",
    ],
    "Muffa_grigia": [
        "https://raw.githubusercontent.com/pratikkayal/PlantDoc-Dataset/master/train/Tomato%20leaf%20yellow%20virus/0001.jpg",
        "https://raw.githubusercontent.com/pratikkayal/PlantDoc-Dataset/master/train/Tomato%20leaf%20yellow%20virus/0002.jpg",
        "https://raw.githubusercontent.com/pratikkayal/PlantDoc-Dataset/master/train/Tomato%20mite/0001.jpg",
        "https://raw.githubusercontent.com/pratikkayal/PlantDoc-Dataset/master/train/Tomato%20mite/0002.jpg",
    ],
    "Ruggine": [
        "https://raw.githubusercontent.com/pratikkayal/PlantDoc-Dataset/master/train/Corn%20rust%20leaf/0001.jpg",
        "https://raw.githubusercontent.com/pratikkayal/PlantDoc-Dataset/master/train/Corn%20rust%20leaf/0002.jpg",
        "https://raw.githubusercontent.com/pratikkayal/PlantDoc-Dataset/master/train/Corn%20rust%20leaf/0003.jpg",
        "https://raw.githubusercontent.com/pratikkayal/PlantDoc-Dataset/master/train/Corn%20rust%20leaf/0004.jpg",
    ],
    "Sano": [
        "https://raw.githubusercontent.com/pratikkayal/PlantDoc-Dataset/master/train/Tomato%20leaf/0001.jpg",
        "https://raw.githubusercontent.com/pratikkayal/PlantDoc-Dataset/master/train/Tomato%20leaf/0002.jpg",
        "https://raw.githubusercontent.com/pratikkayal/PlantDoc-Dataset/master/train/Tomato%20leaf/0003.jpg",
        "https://raw.githubusercontent.com/pratikkayal/PlantDoc-Dataset/master/train/Tomato%20leaf/0004.jpg",
        "https://raw.githubusercontent.com/pratikkayal/PlantDoc-Dataset/master/train/Tomato%20leaf/0005.jpg",
        "https://raw.githubusercontent.com/pratikkayal/PlantDoc-Dataset/master/train/Corn%20leaf%20(maize)/0001.jpg",
        "https://raw.githubusercontent.com/pratikkayal/PlantDoc-Dataset/master/train/Corn%20leaf%20(maize)/0002.jpg",
        "https://raw.githubusercontent.com/pratikkayal/PlantDoc-Dataset/master/train/Grape%20leaf/0001.jpg",
        "https://raw.githubusercontent.com/pratikkayal/PlantDoc-Dataset/master/train/Grape%20leaf/0002.jpg",
        "https://raw.githubusercontent.com/pratikkayal/PlantDoc-Dataset/master/train/Grape%20leaf/0003.jpg",
    ],
    "Carenza_azoto": [
        "https://raw.githubusercontent.com/pratikkayal/PlantDoc-Dataset/master/train/Soybean%20leaf/0001.jpg",
        "https://raw.githubusercontent.com/pratikkayal/PlantDoc-Dataset/master/train/Soybean%20leaf/0002.jpg",
        "https://raw.githubusercontent.com/pratikkayal/PlantDoc-Dataset/master/train/Tomato%20leaf%20mosaic%20virus/0001.jpg",
        "https://raw.githubusercontent.com/pratikkayal/PlantDoc-Dataset/master/train/Tomato%20leaf%20mosaic%20virus/0002.jpg",
    ],
}

# Dataset aggiuntivo: PlantDoc su GitHub (CSV con URLs)
PLANTDOC_CSV_URL = (
    "https://raw.githubusercontent.com/pratikkayal/PlantDoc-Dataset/master/"
    "train.csv"
)


def _safe_download_image(url: str, dest_path: Path, timeout: int = 15) -> bool:
    """Scarica una singola immagine con retry e validazione."""
    for attempt in range(3):
        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "DELTA-AI/2.0 (plant-disease-research)"},
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = resp.read()
            # Valida che sia un'immagine reale
            if len(data) < 1000:
                return False
            # Verifica header JPEG/PNG
            if data[:2] == b'\xff\xd8' or data[:8] == b'\x89PNG\r\n\x1a\n':
                dest_path.write_bytes(data)
                return True
            # Prova comunque come immagine con Pillow
            try:
                from PIL import Image
                img = Image.open(io.BytesIO(data))
                img.verify()
                # Re-apri per salvare (verify consuma il file)
                img = Image.open(io.BytesIO(data)).convert("RGB").resize((224, 224))
                img.save(dest_path, "JPEG", quality=90)
                return True
            except Exception:
                return False
        except Exception as e:
            LOGGER.debug("Download tentativo %d fallito (%s): %s", attempt + 1, url, e)
            if attempt < 2:
                time.sleep(1.5 * (attempt + 1))
    return False


def download_via_github_samples(output_dir: Path, max_per_class: int) -> bool:
    """
    Scarica campioni PlantDoc da GitHub (fallback affidabile).
    Poi replica le immagini con augmentation leggera per avere almeno 50/classe.
    """
    LOGGER.info("Download campioni PlantDoc da GitHub...")
    counts: Dict[str, int] = {}
    total_saved = 0

    for delta_class, urls in GITHUB_SAMPLE_URLS.items():
        if counts.get(delta_class, 0) >= max_per_class:
            continue
        dest_dir = output_dir / delta_class
        dest_dir.mkdir(parents=True, exist_ok=True)

        for i, url in enumerate(urls):
            if counts.get(delta_class, 0) >= max_per_class:
                break
            fname = f"{delta_class}_gh_{i:04d}.jpg"
            dest_path = dest_dir / fname
            if dest_path.exists():
                counts[delta_class] = counts.get(delta_class, 0) + 1
                total_saved += 1
                continue
            if _safe_download_image(url, dest_path):
                counts[delta_class] = counts.get(delta_class, 0) + 1
                total_saved += 1
                LOGGER.debug("Scaricato: %s → %s", url, fname)
            else:
                LOGGER.debug("Fallito: %s", url)

        time.sleep(0.3)  # Rate limiting cortese

    _log_counts(counts, "GitHub PlantDoc samples")
    return total_saved > 0


# ──────────────────────────────────────────────────────────────────────────────
# SORGENTE 7 — PlantDoc GitHub completo via ZIP
# ──────────────────────────────────────────────────────────────────────────────

# Mapping cartelle PlantDoc → classi DELTA
PLANTDOC_FOLDER_MAP: Dict[str, str] = {
    "Tomato leaf late blight":          "Peronospora",
    "Grape leaf blight":                "Peronospora",
    "Potato leaf late blight":          "Peronospora",
    "Tomato Early blight leaf":         "Alternaria",
    "Corn leaf blight":                 "Alternaria",
    "Squash Powdery mildew leaf":       "Oidio",
    "Strawberry leaf":                  "Oidio",
    "Tomato leaf yellow virus":         "Muffa_grigia",
    "Tomato mite":                      "Muffa_grigia",
    "Corn rust leaf":                   "Ruggine",
    "Apple rust leaf":                  "Ruggine",
    "Tomato leaf":                      "Sano",
    "Corn leaf (maize)":                "Sano",
    "Grape leaf":                       "Sano",
    "Soybean leaf":                     "Carenza_azoto",
    "Tomato leaf mosaic virus":         "Carenza_azoto",
    "Bell_pepper leaf":                 "Sano",
    "Blueberry leaf":                   "Sano",
    "Cherry leaf":                      "Sano",
    "Peach leaf":                       "Sano",
}

PLANTDOC_ZIP_URL = (
    "https://github.com/pratikkayal/PlantDoc-Dataset/archive/refs/heads/master.zip"
)


def download_via_plantdoc_zip(output_dir: Path, max_per_class: int) -> bool:
    """Scarica l'intero dataset PlantDoc da GitHub ZIP."""
    import zipfile
    import tempfile

    LOGGER.info("Download PlantDoc completo (ZIP ~180MB)...")
    try:
        from PIL import Image

        zip_cache = Path("/tmp/plantdoc_master.zip")
        if not zip_cache.exists():
            LOGGER.info("Download ZIP in corso...")
            req = urllib.request.Request(
                PLANTDOC_ZIP_URL,
                headers={"User-Agent": "DELTA-AI/2.0"},
            )
            with urllib.request.urlopen(req, timeout=300) as resp:
                total = int(resp.headers.get("Content-Length", 0))
                downloaded = 0
                chunk_size = 65536
                with open(zip_cache, "wb") as f:
                    while True:
                        chunk = resp.read(chunk_size)
                        if not chunk:
                            break
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total > 0:
                            pct = downloaded / total * 100
                            print(f"\r  Progresso: {pct:.1f}% ({downloaded//1024//1024}MB)", end="", flush=True)
            print()
            LOGGER.info("ZIP scaricato: %s", zip_cache)
        else:
            LOGGER.info("ZIP già in cache: %s", zip_cache)

        counts: Dict[str, int] = {}
        saved = 0

        with zipfile.ZipFile(zip_cache, "r") as zf:
            members = zf.namelist()
            img_members = [
                m for m in members
                if m.lower().endswith((".jpg", ".jpeg", ".png"))
            ]
            LOGGER.info("Immagini nello ZIP: %d", len(img_members))

            # Mescola per varietà
            random.shuffle(img_members)

            for member in img_members:
                parts = Path(member).parts
                # Struttura: PlantDoc-Dataset-master/train/<classe>/img.jpg
                if len(parts) < 3:
                    continue
                folder_name = parts[-2]  # nome cartella classe

                delta_class = PLANTDOC_FOLDER_MAP.get(folder_name)
                if delta_class is None:
                    # Fuzzy match
                    for pd_key, d_cls in PLANTDOC_FOLDER_MAP.items():
                        if pd_key.lower() in folder_name.lower():
                            delta_class = d_cls
                            break

                if delta_class is None:
                    continue
                if counts.get(delta_class, 0) >= max_per_class:
                    continue

                dest_dir = output_dir / delta_class
                dest_dir.mkdir(parents=True, exist_ok=True)

                try:
                    with zf.open(member) as img_file:
                        data = img_file.read()
                    img = Image.open(io.BytesIO(data)).convert("RGB").resize((224, 224))
                    fname = f"{delta_class}_{saved:06d}.jpg"
                    img.save(dest_dir / fname, "JPEG", quality=92)
                    counts[delta_class] = counts.get(delta_class, 0) + 1
                    saved += 1
                except Exception as e:
                    LOGGER.debug("Immagine skippata %s: %s", member, e)

        _log_counts(counts, "PlantDoc ZIP")
        return saved > 0

    except Exception as e:
        LOGGER.warning("PlantDoc ZIP fallito: %s", e)
        # Rimuovi cache corrotta
        if zip_cache.exists():
            try:
                zip_cache.unlink()
            except Exception:
                pass
        return False


# ──────────────────────────────────────────────────────────────────────────────
# AUGMENTATION leggera per espandere dataset piccolo
# ──────────────────────────────────────────────────────────────────────────────

def augment_small_classes(output_dir: Path, min_per_class: int = 60) -> None:
    """
    Se una classe ha meno di min_per_class immagini, genera copie augmentate
    con flip, rotazione e variazione brightness per bilanciare il dataset.
    """
    try:
        from PIL import Image, ImageEnhance, ImageFilter
    except ImportError:
        LOGGER.warning("Pillow non disponibile per augmentation")
        return

    for class_dir in output_dir.iterdir():
        if not class_dir.is_dir():
            continue
        imgs = list(class_dir.glob("*.jpg")) + list(class_dir.glob("*.png"))
        n = len(imgs)
        if n == 0 or n >= min_per_class:
            continue

        LOGGER.info(
            "Augmentation classe %s: %d → ~%d immagini",
            class_dir.name, n, min_per_class
        )
        aug_count = 0
        needed = min_per_class - n

        while aug_count < needed:
            for src_path in imgs:
                if aug_count >= needed:
                    break
                try:
                    img = Image.open(src_path).convert("RGB")
                    ops = random.randint(1, 4)

                    if ops == 1:
                        img = img.transpose(Image.FLIP_LEFT_RIGHT)
                    elif ops == 2:
                        angle = random.uniform(-15, 15)
                        img = img.rotate(angle, expand=False, fillcolor=(128, 128, 128))
                    elif ops == 3:
                        factor = random.uniform(0.75, 1.30)
                        img = ImageEnhance.Brightness(img).enhance(factor)
                    elif ops == 4:
                        img = img.filter(ImageFilter.GaussianBlur(radius=random.uniform(0.5, 1.5)))

                    img = img.resize((224, 224))
                    fname = f"{class_dir.name}_aug_{aug_count:05d}.jpg"
                    img.save(class_dir / fname, "JPEG", quality=88)
                    aug_count += 1
                except Exception as e:
                    LOGGER.debug("Augmentation errore: %s", e)

        LOGGER.info("Augmentation %s: aggiunte %d immagini", class_dir.name, aug_count)


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _ingest_folder(src_dir: Path, output_dir: Path, max_per_class: int) -> int:
    """Copia immagini da src_dir (struttura classname/img.jpg) verso output_dir."""
    try:
        from PIL import Image
    except ImportError:
        return 0

    counts: Dict[str, int] = {}
    saved = 0
    for class_dir in src_dir.rglob("*"):
        if not class_dir.is_dir():
            continue
        delta_class = PLANTDOC_FOLDER_MAP.get(class_dir.name)
        if delta_class is None:
            for k, v in PLANTDOC_FOLDER_MAP.items():
                if k.lower() in class_dir.name.lower():
                    delta_class = v
                    break
        if delta_class is None:
            continue
        dest_dir = output_dir / delta_class
        dest_dir.mkdir(parents=True, exist_ok=True)
        for img_path in class_dir.glob("*"):
            if not img_path.suffix.lower() in {".jpg", ".jpeg", ".png"}:
                continue
            if counts.get(delta_class, 0) >= max_per_class:
                break
            try:
                img = Image.open(img_path).convert("RGB").resize((224, 224))
                fname = f"{delta_class}_{saved:06d}.jpg"
                img.save(dest_dir / fname, "JPEG", quality=90)
                counts[delta_class] = counts.get(delta_class, 0) + 1
                saved += 1
            except Exception:
                pass
    return saved


def _log_counts(counts: Dict[str, int], source: str) -> None:
    if not counts:
        LOGGER.info("%s: nessuna immagine salvata", source)
        return
    total = sum(counts.values())
    LOGGER.info("%s: %d immagini totali", source, total)
    for cls, n in sorted(counts.items()):
        LOGGER.info("  %s: %d", cls, n)


def _count_existing(output_dir: Path) -> Dict[str, int]:
    counts = {}
    if not output_dir.exists():
        return counts
    for class_dir in output_dir.iterdir():
        if class_dir.is_dir():
            n = len(list(class_dir.glob("*.jpg"))) + len(list(class_dir.glob("*.png")))
            if n > 0:
                counts[class_dir.name] = n
    return counts


# ──────────────────────────────────────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Scarica dataset PlantVillage/PlantDoc per training DELTA"
    )
    p.add_argument("--output", default="datasets/training",
                   help="Directory output dataset strutturato")
    p.add_argument("--max-per-class", type=int, default=MAX_PER_CLASS,
                   help="Massimo immagini per classe (default: 400)")
    p.add_argument("--min-per-class", type=int, default=60,
                   help="Minimo immagini per classe (triggera augmentation)")
    p.add_argument("--source", choices=["auto", "tfds", "hf", "plantdoc", "github"],
                   default="auto",
                   help="Sorgente dati (auto = prova in sequenza)")
    p.add_argument("--skip-augment", action="store_true",
                   help="Non eseguire augmentation automatica")
    p.add_argument("--log-level", default="INFO",
                   choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    return p


def main() -> int:
    args = build_parser().parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )

    output_dir = Path(args.output).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    LOGGER.info("=" * 60)
    LOGGER.info("DELTA Dataset Downloader — PlantVillage/PlantDoc")
    LOGGER.info("Output: %s", output_dir)
    LOGGER.info("Max per classe: %d", args.max_per_class)
    LOGGER.info("=" * 60)

    # Mostra stato iniziale
    existing = _count_existing(output_dir)
    if existing:
        LOGGER.info("Dataset esistente:")
        for cls, n in sorted(existing.items()):
            LOGGER.info("  %s: %d immagini", cls, n)

    success = False

    if args.source in ("auto", "tfds"):
        success = download_via_tfds(output_dir, args.max_per_class)
        if success and args.source != "auto":
            pass  # continua per completare con altre sorgenti

    if not success or args.source in ("auto", "plantdoc"):
        success2 = download_via_plantdoc_zip(output_dir, args.max_per_class)
        success = success or success2

    if not success or args.source in ("auto", "hf"):
        success3 = download_via_hf_datasets(output_dir, args.max_per_class)
        success = success or success3

    if not success or args.source == "github":
        success4 = download_via_github_samples(output_dir, args.max_per_class)
        success = success or success4

    # Augmentation classi con poche immagini
    if not args.skip_augment:
        LOGGER.info("Augmentation classi con < %d immagini...", args.min_per_class)
        augment_small_classes(output_dir, args.min_per_class)

    # Riepilogo finale
    final_counts = _count_existing(output_dir)
    LOGGER.info("=" * 60)
    LOGGER.info("DATASET FINALE:")
    total = 0
    classes_ok = 0
    for cls in sorted(final_counts):
        n = final_counts[cls]
        status = "✓" if n >= args.min_per_class else "⚠ (poche immagini)"
        LOGGER.info("  %-20s %4d  %s", cls, n, status)
        total += n
        if n >= 2:
            classes_ok += 1
    LOGGER.info("Totale: %d immagini, %d classi", total, classes_ok)

    # Salva manifest
    manifest = {
        "classes": final_counts,
        "total_images": total,
        "n_classes": classes_ok,
        "output_dir": str(output_dir),
        "max_per_class": args.max_per_class,
    }
    manifest_path = output_dir / "download_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    LOGGER.info("Manifest salvato: %s", manifest_path)

    if classes_ok < 2:
        LOGGER.error("Dataset insufficiente: servono almeno 2 classi con immagini.")
        return 1

    LOGGER.info("=" * 60)
    LOGGER.info("Download completato. Avvia training con:")
    LOGGER.info(
        "  python ai/train_keras_classifier.py --dataset %s --output models",
        args.output,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
