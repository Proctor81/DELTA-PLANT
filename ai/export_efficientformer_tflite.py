"""
Fine-tuning + export pipeline per EfficientFormerV2-S1:
PyTorch -> ONNX -> SavedModel -> TFLite float16 / int8.

Dipendenze opzionali:
    pip install -r requirements-efficientformer.txt
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import random
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Optional

import numpy as np

LOGGER = logging.getLogger("delta.ai.efficientformer.export")


@dataclass
class ExportArtifacts:
    checkpoint_path: Path
    onnx_path: Path
    saved_model_dir: Path
    float16_tflite_path: Path
    int8_tflite_path: Path
    labels_path: Path
    class_names: list[str]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Fine-tuning ed export EfficientFormerV2-S1 -> TFLite")
    parser.add_argument("--dataset-root", default="datasets/training", help="Root dataset ImageFolder o root con train/val")
    parser.add_argument("--output-dir", default="models", help="Directory output artefatti")
    parser.add_argument("--torch-model", default="efficientformerv2_s1", help="Nome timm del backbone")
    parser.add_argument("--num-classes", type=int, default=33, help="Numero classi target")
    parser.add_argument("--img-size", type=int, default=224, help="Input size quadrato")
    parser.add_argument("--epochs", type=int, default=8, help="Numero epoche fine-tuning")
    parser.add_argument("--batch-size", type=int, default=16, help="Batch size training")
    parser.add_argument("--learning-rate", type=float, default=3e-4, help="Learning rate iniziale")
    parser.add_argument("--weight-decay", type=float, default=1e-4, help="Weight decay AdamW")
    parser.add_argument("--val-split", type=float, default=0.2, help="Split validation se val/ non esiste")
    parser.add_argument("--num-workers", type=int, default=2, help="Numero worker DataLoader")
    parser.add_argument("--seed", type=int, default=42, help="Seed riproducibilita")
    parser.add_argument("--mode", default="all", choices=["train", "export", "all"], help="Solo training, solo export o pipeline completa")
    parser.add_argument("--checkpoint", default="", help="Checkpoint .pth gia fine-tuned per export")
    parser.add_argument("--quantization", default="both", choices=["float16", "int8", "both"], help="Varianti TFLite da produrre")
    parser.add_argument("--representative-data", default="", help="Dataset representative per int8 (default: dataset-root)")
    parser.add_argument("--representative-samples", type=int, default=256, help="Numero campioni representative dataset")
    parser.add_argument("--labels-out", default="labels_33classes_correct.txt", help="Nome file labels da esportare")
    parser.add_argument("--skip-onnx-simplify", action="store_true", help="Salta onnxsim")
    parser.add_argument("--allow-float-fallback", action="store_true", help="Permette fallback float nel TFLite int8")
    parser.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    return parser


def set_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)


def _require_module(name: str, hint: str = ""):
    try:
        __import__(name)
        return sys.modules[name]
    except ImportError as exc:
        message = f"Dipendenza mancante: {name}. {hint}".strip()
        raise RuntimeError(message) from exc


def _normalize_folder_label(name: str) -> str:
    mapping = {
        "Pepper,_bell___Bacterial_spot": "Bell_pepper_Bacterial_spot",
        "Pepper,_bell___healthy": "Bell_pepper_healthy",
        "Cherry_(including_sour)___Powdery_mildew": "Cherry_Powdery_mildew",
        "Cherry_(including_sour)___healthy": "Cherry_healthy",
        "Corn_(maize)___Cercospora_leaf_spot Gray_leaf_spot": "Corn_Cercospora",
        "Corn_(maize)___Common_rust_": "Corn_Common_rust",
        "Corn_(maize)___Northern_Leaf_Blight": "Corn_Northern_Leaf_Blight",
        "Corn_(maize)___healthy": "Corn_healthy",
        "Grape___Esca_(Black_Measles)": "Grape_Esca",
        "Grape___Leaf_blight_(Isariopsis_Leaf_Spot)": "Grape_Leaf_blight",
        "Tomato___Tomato_Yellow_Leaf_Curl_Virus": "Tomato_Yellow_Leaf_Curl",
        "Tomato___Tomato_mosaic_virus": "Tomato_mosaic_virus",
    }
    if name in mapping:
        return mapping[name]
    return name.replace("___", "_").replace(" ", "_").replace(",", "")


def _discover_image_folder_roots(dataset_root: Path) -> tuple[Path, Optional[Path]]:
    train_root = dataset_root / "train"
    for val_name in ("val", "validation", "valid"):
        val_root = dataset_root / val_name
        if train_root.exists() and val_root.exists():
            return train_root, val_root
    return dataset_root, None


def _build_transforms(img_size: int):
    torchvision = _require_module("torchvision", "Installare torchvision per il fine-tuning.")
    transforms = torchvision.transforms
    normalize = transforms.Normalize(mean=[0.5, 0.5, 0.5], std=[0.5, 0.5, 0.5])
    train_tf = transforms.Compose([
        transforms.RandomResizedCrop(img_size, scale=(0.80, 1.0)),
        transforms.RandomHorizontalFlip(),
        transforms.RandomRotation(12),
        transforms.ColorJitter(brightness=0.12, contrast=0.12, saturation=0.08),
        transforms.ToTensor(),
        normalize,
    ])
    eval_tf = transforms.Compose([
        transforms.Resize(int(img_size * 1.14)),
        transforms.CenterCrop(img_size),
        transforms.ToTensor(),
        normalize,
    ])
    return train_tf, eval_tf


def _build_dataloaders(dataset_root: Path, img_size: int, batch_size: int, num_workers: int, val_split: float, seed: int):
    torch = _require_module("torch", "Installare torch per il fine-tuning.")
    torchvision = _require_module("torchvision", "Installare torchvision per il fine-tuning.")
    datasets = torchvision.datasets

    train_tf, eval_tf = _build_transforms(img_size)
    train_root, val_root = _discover_image_folder_roots(dataset_root)

    if val_root is not None:
        train_dataset = datasets.ImageFolder(str(train_root), transform=train_tf)
        val_dataset = datasets.ImageFolder(str(val_root), transform=eval_tf)
        class_names = [_normalize_folder_label(name) for name in train_dataset.classes]
    else:
        base_dataset = datasets.ImageFolder(str(train_root))
        n_total = len(base_dataset)
        if n_total < 2:
            raise RuntimeError(f"Dataset troppo piccolo per fine-tuning: {train_root}")
        n_val = max(1, int(n_total * val_split))
        n_train = n_total - n_val
        generator = torch.Generator().manual_seed(seed)
        train_subset, val_subset = torch.utils.data.random_split(base_dataset, [n_train, n_val], generator=generator)

        class _TransformSubset(torch.utils.data.Dataset):
            def __init__(self, dataset, indices, transform):
                self.dataset = dataset
                self.indices = list(indices)
                self.transform = transform

            def __len__(self):
                return len(self.indices)

            def __getitem__(self, idx):
                image, label = self.dataset[self.indices[idx]]
                if self.transform is not None:
                    image = self.transform(image)
                return image, label

        train_dataset = _TransformSubset(base_dataset, train_subset.indices, train_tf)
        val_dataset = _TransformSubset(base_dataset, val_subset.indices, eval_tf)
        class_names = [_normalize_folder_label(name) for name in base_dataset.classes]

    if len(class_names) != len(set(class_names)):
        raise RuntimeError("Le classi normalizzate non sono univoche. Verificare il mapping PlantVillage.")

    pin_memory = bool(torch.cuda.is_available())
    train_loader = torch.utils.data.DataLoader(
        train_dataset,
        batch_size=batch_size,
        shuffle=True,
        num_workers=num_workers,
        pin_memory=pin_memory,
    )
    val_loader = torch.utils.data.DataLoader(
        val_dataset,
        batch_size=batch_size,
        shuffle=False,
        num_workers=num_workers,
        pin_memory=pin_memory,
    )
    return train_loader, val_loader, class_names


def _build_model(torch_model_name: str, num_classes: int):
    timm = _require_module("timm", "Installare timm per EfficientFormerV2-S1.")
    return timm.create_model(torch_model_name, pretrained=True, num_classes=num_classes)


def _train_model(args, class_names: list[str]) -> Path:
    torch = _require_module("torch", "Installare torch per il fine-tuning.")

    dataset_root = Path(args.dataset_root).resolve()
    train_loader, val_loader, discovered_classes = _build_dataloaders(
        dataset_root=dataset_root,
        img_size=args.img_size,
        batch_size=args.batch_size,
        num_workers=args.num_workers,
        val_split=args.val_split,
        seed=args.seed,
    )
    if not class_names:
        class_names.extend(discovered_classes)

    if len(discovered_classes) != args.num_classes:
        LOGGER.warning(
            "Numero classi dataset=%d diverso da --num-classes=%d. Uso il dataset come fonte di verita.",
            len(discovered_classes),
            args.num_classes,
        )
        args.num_classes = len(discovered_classes)

    model = _build_model(args.torch_model, args.num_classes)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model.to(device)

    criterion = torch.nn.CrossEntropyLoss()
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.learning_rate, weight_decay=args.weight_decay)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=max(args.epochs, 1))

    checkpoint_path = Path(args.output_dir).resolve() / "efficientformer_v2_s1_33classes.pth"
    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
    best_acc = -1.0
    history: list[dict[str, float]] = []

    for epoch in range(1, args.epochs + 1):
        model.train()
        train_loss = 0.0
        train_correct = 0
        train_total = 0
        for images, targets in train_loader:
            images = images.to(device)
            targets = targets.to(device)

            optimizer.zero_grad(set_to_none=True)
            logits = model(images)
            loss = criterion(logits, targets)
            loss.backward()
            optimizer.step()

            train_loss += float(loss.item()) * images.size(0)
            predictions = torch.argmax(logits, dim=1)
            train_correct += int((predictions == targets).sum().item())
            train_total += int(images.size(0))

        model.eval()
        val_loss = 0.0
        val_correct = 0
        val_total = 0
        with torch.no_grad():
            for images, targets in val_loader:
                images = images.to(device)
                targets = targets.to(device)
                logits = model(images)
                loss = criterion(logits, targets)
                val_loss += float(loss.item()) * images.size(0)
                predictions = torch.argmax(logits, dim=1)
                val_correct += int((predictions == targets).sum().item())
                val_total += int(images.size(0))

        scheduler.step()

        epoch_stats = {
            "epoch": float(epoch),
            "train_loss": train_loss / max(train_total, 1),
            "train_acc": train_correct / max(train_total, 1),
            "val_loss": val_loss / max(val_total, 1),
            "val_acc": val_correct / max(val_total, 1),
        }
        history.append(epoch_stats)
        LOGGER.info(
            "Epoch %d/%d | train_loss=%.4f train_acc=%.4f | val_loss=%.4f val_acc=%.4f",
            epoch,
            args.epochs,
            epoch_stats["train_loss"],
            epoch_stats["train_acc"],
            epoch_stats["val_loss"],
            epoch_stats["val_acc"],
        )

        if epoch_stats["val_acc"] >= best_acc:
            best_acc = epoch_stats["val_acc"]
            torch.save(
                {
                    "state_dict": model.state_dict(),
                    "class_names": list(class_names),
                    "val_acc": best_acc,
                    "history": history,
                    "torch_model": args.torch_model,
                },
                checkpoint_path,
            )

    metrics_path = checkpoint_path.with_suffix(".training.json")
    metrics_path.write_text(json.dumps(history, indent=2), encoding="utf-8")
    LOGGER.info("Checkpoint best model salvato in %s", checkpoint_path)
    return checkpoint_path


def _load_checkpoint_model(torch_model_name: str, checkpoint_path: Path, num_classes: int):
    torch = _require_module("torch", "Installare torch per l'export.")
    model = _build_model(torch_model_name, num_classes)
    state = torch.load(str(checkpoint_path), map_location="cpu")
    if isinstance(state, dict) and "state_dict" in state:
        state = state["state_dict"]
    if isinstance(state, dict):
        state = {str(key).replace("module.", ""): value for key, value in state.items()}
    missing, unexpected = model.load_state_dict(state, strict=False)
    if missing:
        LOGGER.warning("Missing keys durante load_state_dict: %s", list(missing)[:8])
    if unexpected:
        LOGGER.warning("Unexpected keys durante load_state_dict: %s", list(unexpected)[:8])
    model.eval()
    return model


def _export_to_onnx(model: Any, onnx_path: Path, img_size: int) -> None:
    torch = _require_module("torch", "Installare torch per l'export ONNX.")
    onnx_path.parent.mkdir(parents=True, exist_ok=True)
    dummy = torch.randn(1, 3, img_size, img_size)
    torch.onnx.export(
        model,
        dummy,
        str(onnx_path),
        input_names=["input"],
        output_names=["logits"],
        dynamic_axes=None,
        opset_version=17,
        do_constant_folding=True,
    )
    LOGGER.info("ONNX esportato in %s", onnx_path)


def _simplify_onnx(onnx_path: Path) -> Path:
    simplified_path = onnx_path.with_name(onnx_path.stem + ".sim.onnx")
    onnxsim_bin = shutil.which("onnxsim")
    if onnxsim_bin:
        subprocess.run([onnxsim_bin, str(onnx_path), str(simplified_path)], check=True)
        LOGGER.info("ONNX semplificato in %s", simplified_path)
        return simplified_path
    LOGGER.warning("onnxsim non trovato: uso ONNX originale")
    return onnx_path


def _convert_onnx_to_saved_model(onnx_path: Path, saved_model_dir: Path) -> None:
    saved_model_dir.parent.mkdir(parents=True, exist_ok=True)
    try:
        from onnx2tf import convert  # type: ignore
        convert(input_onnx_file_path=str(onnx_path), output_folder_path=str(saved_model_dir), non_verbose=True)
        LOGGER.info("SavedModel generato in %s", saved_model_dir)
        return
    except Exception as exc:
        LOGGER.warning("API onnx2tf non disponibile (%s), provo il CLI", exc)

    onnx2tf_bin = shutil.which("onnx2tf")
    if not onnx2tf_bin:
        raise RuntimeError("onnx2tf non installato: impossibile convertire ONNX in SavedModel")
    subprocess.run([onnx2tf_bin, "-i", str(onnx_path), "-o", str(saved_model_dir)], check=True)
    LOGGER.info("SavedModel generato in %s", saved_model_dir)


def _iter_representative_images(dataset_root: Path) -> Iterable[Path]:
    exts = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff"}
    for path in dataset_root.rglob("*"):
        if path.is_file() and path.suffix.lower() in exts:
            yield path


def _make_representative_dataset(dataset_root: Path, img_size: int, max_samples: int):
    try:
        import cv2  # type: ignore
    except ImportError as exc:
        raise RuntimeError("OpenCV richiesto per il representative dataset") from exc

    selected = list(_iter_representative_images(dataset_root))[:max_samples]
    if not selected:
        raise RuntimeError(f"Representative dataset vuoto: {dataset_root}")

    def _generator():
        for image_path in selected:
            image = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
            if image is None:
                continue
            image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            image = cv2.resize(image, (img_size, img_size), interpolation=cv2.INTER_AREA)
            image = (image.astype(np.float32) / 127.5) - 1.0
            yield [np.expand_dims(image, axis=0)]

    return _generator


def _convert_saved_model_to_tflite(
    saved_model_dir: Path,
    output_path: Path,
    quantization: str,
    representative_data: Path,
    img_size: int,
    representative_samples: int,
    allow_float_fallback: bool,
) -> None:
    try:
        import tensorflow as tf  # type: ignore
    except ImportError as exc:
        raise RuntimeError("TensorFlow richiesto per la conversione TFLite") from exc

    converter = tf.lite.TFLiteConverter.from_saved_model(str(saved_model_dir))
    if quantization == "float16":
        converter.optimizations = [tf.lite.Optimize.DEFAULT]
        converter.target_spec.supported_types = [tf.float16]
    elif quantization == "int8":
        converter.optimizations = [tf.lite.Optimize.DEFAULT]
        converter.representative_dataset = _make_representative_dataset(
            representative_data,
            img_size=img_size,
            max_samples=representative_samples,
        )
        converter.inference_input_type = tf.int8
        converter.inference_output_type = tf.int8
        if allow_float_fallback:
            converter.target_spec.supported_ops = [
                tf.lite.OpsSet.TFLITE_BUILTINS_INT8,
                tf.lite.OpsSet.TFLITE_BUILTINS,
            ]
        else:
            converter.target_spec.supported_ops = [tf.lite.OpsSet.TFLITE_BUILTINS_INT8]
    else:
        raise RuntimeError(f"Quantizzazione non supportata: {quantization}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(converter.convert())
    LOGGER.info("TFLite %s salvato in %s", quantization, output_path)


def _write_labels(labels_path: Path, class_names: list[str]) -> None:
    labels_path.parent.mkdir(parents=True, exist_ok=True)
    labels_path.write_text("\n".join(class_names) + "\n", encoding="utf-8")


def main() -> int:
    args = build_parser().parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    set_seed(args.seed)

    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    labels_path = output_dir / args.labels_out
    onnx_path = output_dir / "efficientformer_v2_s1_33classes.onnx"
    saved_model_dir = output_dir / "efficientformer_v2_s1_saved_model"
    float16_tflite_path = output_dir / "efficientformer_v2_s1_33classes_float16.tflite"
    int8_tflite_path = output_dir / "efficientformer_v2_s1_33classes_int8.tflite"

    class_names: list[str] = []
    checkpoint_path = Path(args.checkpoint).resolve() if args.checkpoint else output_dir / "efficientformer_v2_s1_33classes.pth"

    if args.mode in ("train", "all"):
        checkpoint_path = _train_model(args, class_names)
    elif not checkpoint_path.exists():
        raise RuntimeError(f"Checkpoint non trovato per export: {checkpoint_path}")

    if args.mode in ("export", "all"):
        if not class_names:
            state = _require_module("torch", "Installare torch per leggere il checkpoint").load(str(checkpoint_path), map_location="cpu")
            class_names = list((state or {}).get("class_names") or [])
        if not class_names:
            raise RuntimeError("Impossibile determinare le classi dal checkpoint. Rieseguire il fine-tuning.")

        _write_labels(labels_path, class_names)
        model = _load_checkpoint_model(args.torch_model, checkpoint_path, len(class_names))
        _export_to_onnx(model, onnx_path, args.img_size)
        onnx_source = onnx_path if args.skip_onnx_simplify else _simplify_onnx(onnx_path)
        _convert_onnx_to_saved_model(onnx_source, saved_model_dir)

        representative_root = Path(args.representative_data or args.dataset_root).resolve()
        if args.quantization in ("float16", "both"):
            _convert_saved_model_to_tflite(
                saved_model_dir=saved_model_dir,
                output_path=float16_tflite_path,
                quantization="float16",
                representative_data=representative_root,
                img_size=args.img_size,
                representative_samples=args.representative_samples,
                allow_float_fallback=args.allow_float_fallback,
            )
        if args.quantization in ("int8", "both"):
            _convert_saved_model_to_tflite(
                saved_model_dir=saved_model_dir,
                output_path=int8_tflite_path,
                quantization="int8",
                representative_data=representative_root,
                img_size=args.img_size,
                representative_samples=args.representative_samples,
                allow_float_fallback=args.allow_float_fallback,
            )

    artifacts = ExportArtifacts(
        checkpoint_path=checkpoint_path,
        onnx_path=onnx_path,
        saved_model_dir=saved_model_dir,
        float16_tflite_path=float16_tflite_path,
        int8_tflite_path=int8_tflite_path,
        labels_path=labels_path,
        class_names=class_names,
    )
    print(json.dumps({
        "checkpoint": str(artifacts.checkpoint_path),
        "onnx": str(artifacts.onnx_path),
        "saved_model": str(artifacts.saved_model_dir),
        "float16_tflite": str(artifacts.float16_tflite_path),
        "int8_tflite": str(artifacts.int8_tflite_path),
        "labels": str(artifacts.labels_path),
        "classes": artifacts.class_names,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
