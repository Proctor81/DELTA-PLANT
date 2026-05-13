"""
Fine-tuning + export pipeline per EfficientFormerV2-S1:
PyTorch -> ONNX -> SavedModel -> TFLite float16 / int8.

Dipendenze opzionali:
    pip install -r requirements-efficientformer.txt
"""

from __future__ import annotations

import argparse
import copy
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
REPO_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = REPO_ROOT / ".env"


class GracefulStopRequested(RuntimeError):
    """Arresto cooperativo richiesto per consentire resume successivo."""


def _load_env_file(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    if not path.exists() or not path.is_file():
        return env
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        env[key.strip()] = value.strip().strip('"').strip("'")
    return env


def _configure_hf_hub_auth() -> None:
    file_env = _load_env_file(ENV_FILE)
    token = (
        os.environ.get("HF_TOKEN")
        or os.environ.get("HUGGINGFACE_HUB_TOKEN")
        or os.environ.get("HF_API_TOKEN")
        or file_env.get("HF_TOKEN")
        or file_env.get("HUGGINGFACE_HUB_TOKEN")
        or file_env.get("HF_API_TOKEN")
    )
    if not token:
        return

    # Allinea le variabili usate dal progetto e dalla Hugging Face Hub.
    os.environ.setdefault("HF_API_TOKEN", token)
    os.environ.setdefault("HF_TOKEN", token)
    os.environ.setdefault("HUGGINGFACE_HUB_TOKEN", token)


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
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Riprende il fine-tuning dal checkpoint last/state file se presente",
    )
    parser.add_argument(
        "--train-state-file",
        default="",
        help="Path JSON stato fine-tuning/resume (default: <output-dir>/efficientformer_v2_s1_33classes.state.json)",
    )
    parser.add_argument(
        "--stop-file",
        default="",
        help="Path file sentinella per arresto cooperativo e resume successivo",
    )
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


def _resolve_train_state_path(args, output_dir: Path) -> Path:
    if args.train_state_file:
        return Path(args.train_state_file).resolve()
    return output_dir / "efficientformer_v2_s1_33classes.state.json"


def _resolve_stop_file(args) -> Optional[Path]:
    if not args.stop_file:
        return None
    return Path(args.stop_file).resolve()


def _stop_requested(stop_file: Optional[Path]) -> bool:
    return bool(stop_file and stop_file.exists())


def _raise_if_stop_requested(stop_file: Optional[Path], stage: str) -> None:
    if _stop_requested(stop_file):
        raise GracefulStopRequested(f"Stop richiesto in fase: {stage}")


def _extract_state_dict(state: Any) -> dict[str, Any]:
    if isinstance(state, dict) and "state_dict" in state:
        state = state["state_dict"]
    if not isinstance(state, dict):
        raise RuntimeError("Checkpoint non valido: state_dict assente o non supportato")
    return {str(key).replace("module.", ""): value for key, value in state.items()}


def _load_state_dict_into_model(model: Any, state: Any) -> None:
    missing, unexpected = model.load_state_dict(_extract_state_dict(state), strict=False)
    if missing:
        LOGGER.warning("Missing keys durante load_state_dict: %s", list(missing)[:8])
    if unexpected:
        LOGGER.warning("Unexpected keys durante load_state_dict: %s", list(unexpected)[:8])


def _load_resume_state(state_path: Path, args, dataset_root: Path) -> Optional[dict[str, Any]]:
    if not state_path.exists() or not state_path.is_file():
        return None

    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        LOGGER.warning("State file resume corrotto: %s", state_path)
        return None

    checks = {
        "dataset_root": str(dataset_root),
        "torch_model": args.torch_model,
        "epochs": args.epochs,
    }
    for key, expected in checks.items():
        if state.get(key) != expected:
            LOGGER.warning("Resume ignorato: %s differente rispetto allo state file", key)
            return None

    return state


def _write_resume_state(
    state_path: Path,
    *,
    status: str,
    args,
    dataset_root: Path,
    completed_epochs: int,
    best_acc: float,
    class_names: list[str],
    best_checkpoint_path: Path,
    last_checkpoint_path: Path,
    metrics_path: Path,
) -> None:
    payload = {
        "status": status,
        "dataset_root": str(dataset_root),
        "torch_model": args.torch_model,
        "num_classes": args.num_classes,
        "epochs": args.epochs,
        "completed_epochs": completed_epochs,
        "best_acc": best_acc,
        "class_names": list(class_names),
        "best_checkpoint": str(best_checkpoint_path),
        "last_checkpoint": str(last_checkpoint_path),
        "metrics_path": str(metrics_path),
    }
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _train_model(args, class_names: list[str]) -> Path:
    torch = _require_module("torch", "Installare torch per il fine-tuning.")

    dataset_root = Path(args.dataset_root).resolve()
    output_dir = Path(args.output_dir).resolve()
    state_path = _resolve_train_state_path(args, output_dir)
    stop_file = _resolve_stop_file(args)
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

    checkpoint_path = output_dir / "efficientformer_v2_s1_33classes.pth"
    last_checkpoint_path = output_dir / "efficientformer_v2_s1_33classes.last.pth"
    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
    best_acc = -1.0
    history: list[dict[str, float]] = []
    metrics_path = checkpoint_path.with_suffix(".training.json")
    completed_epochs = 0

    if args.resume:
        resume_state = _load_resume_state(state_path, args, dataset_root)
        if resume_state is not None:
            resume_checkpoint = Path(str(resume_state.get("last_checkpoint") or last_checkpoint_path)).resolve()
            if resume_checkpoint.exists() and resume_checkpoint.is_file():
                checkpoint_state = torch.load(str(resume_checkpoint), map_location="cpu")
                _load_state_dict_into_model(model, checkpoint_state)
                if isinstance(checkpoint_state, dict):
                    if checkpoint_state.get("optimizer_state"):
                        optimizer.load_state_dict(checkpoint_state["optimizer_state"])
                    if checkpoint_state.get("scheduler_state"):
                        scheduler.load_state_dict(checkpoint_state["scheduler_state"])
                    history = list(checkpoint_state.get("history") or [])
                    best_acc = float(checkpoint_state.get("best_acc", resume_state.get("best_acc", -1.0)))
                    completed_epochs = int(checkpoint_state.get("epoch", resume_state.get("completed_epochs", 0)))
                    if not class_names:
                        class_names.extend(list(checkpoint_state.get("class_names") or resume_state.get("class_names") or []))
                LOGGER.info("Resume fine-tuning da epoca %d/%d", completed_epochs, args.epochs)
            else:
                LOGGER.warning("Resume richiesto ma checkpoint last non trovato: %s", resume_checkpoint)

    if completed_epochs >= args.epochs:
        _write_resume_state(
            state_path,
            status="completed",
            args=args,
            dataset_root=dataset_root,
            completed_epochs=completed_epochs,
            best_acc=best_acc,
            class_names=class_names,
            best_checkpoint_path=checkpoint_path,
            last_checkpoint_path=last_checkpoint_path,
            metrics_path=metrics_path,
        )
        return checkpoint_path

    for epoch in range(completed_epochs + 1, args.epochs + 1):
        _raise_if_stop_requested(stop_file, f"train:before-epoch-{epoch}")
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

        is_best = epoch_stats["val_acc"] >= best_acc
        if is_best:
            best_acc = epoch_stats["val_acc"]

        snapshot = {
            "epoch": epoch,
            "state_dict": model.state_dict(),
            "optimizer_state": optimizer.state_dict(),
            "scheduler_state": scheduler.state_dict(),
            "class_names": list(class_names),
            "best_acc": best_acc,
            "history": history,
            "torch_model": args.torch_model,
        }
        torch.save(snapshot, last_checkpoint_path)

        if is_best:
            torch.save(
                snapshot,
                checkpoint_path,
            )

        metrics_path.write_text(json.dumps(history, indent=2), encoding="utf-8")
        _write_resume_state(
            state_path,
            status="running",
            args=args,
            dataset_root=dataset_root,
            completed_epochs=epoch,
            best_acc=best_acc,
            class_names=class_names,
            best_checkpoint_path=checkpoint_path,
            last_checkpoint_path=last_checkpoint_path,
            metrics_path=metrics_path,
        )
        _raise_if_stop_requested(stop_file, f"train:after-epoch-{epoch}")

    metrics_path.write_text(json.dumps(history, indent=2), encoding="utf-8")
    _write_resume_state(
        state_path,
        status="completed",
        args=args,
        dataset_root=dataset_root,
        completed_epochs=args.epochs,
        best_acc=best_acc,
        class_names=class_names,
        best_checkpoint_path=checkpoint_path,
        last_checkpoint_path=last_checkpoint_path,
        metrics_path=metrics_path,
    )
    LOGGER.info("Checkpoint best model salvato in %s", checkpoint_path)
    return checkpoint_path


def _load_checkpoint_model(torch_model_name: str, checkpoint_path: Path, num_classes: int):
    torch = _require_module("torch", "Installare torch per l'export.")
    model = _build_model(torch_model_name, num_classes)
    state = torch.load(str(checkpoint_path), map_location="cpu")
    _load_state_dict_into_model(model, state)
    model.eval()
    return model


def _enable_export_friendly_gelu(model: Any) -> int:
    torch = _require_module("torch", "Installare torch per l'export.")
    gelu_type = getattr(torch.nn, "GELU", None)
    if gelu_type is None:
        return 0

    replaced = 0
    for module_name, module in list(model.named_modules()):
        is_supported_gelu = isinstance(module, gelu_type) or module.__class__.__name__ == "GELU"
        if not module_name or not is_supported_gelu:
            continue

        parent = model
        parts = module_name.split(".")
        for chunk in parts[:-1]:
            parent = parent[int(chunk)] if chunk.isdigit() else getattr(parent, chunk)

        replacement = torch.nn.GELU(approximate="tanh")
        leaf = parts[-1]
        if leaf.isdigit():
            parent[int(leaf)] = replacement
        else:
            setattr(parent, leaf, replacement)
        replaced += 1

    if replaced:
        LOGGER.info("Sostituite %d GELU con approximate='tanh' per export int8", replaced)
    return replaced


def _export_to_onnx(model: Any, onnx_path: Path, img_size: int) -> None:
    torch = _require_module("torch", "Installare torch per l'export ONNX.")
    _require_module(
        "onnxscript",
        "Installare onnxscript per torch.onnx.export (es. pip install onnxscript oppure pip install -r requirements-efficientformer.txt).",
    )
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
        convert(
            input_onnx_file_path=str(onnx_path),
            output_folder_path=str(saved_model_dir),
            flatbuffer_direct_output_saved_model=True,
            non_verbose=True,
        )
        _log_onnx2tf_artifacts(saved_model_dir)
        return
    except Exception as exc:
        if _has_onnx2tf_artifacts(saved_model_dir):
            LOGGER.warning(
                "API onnx2tf terminata con errore (%s), riuso gli artefatti gia presenti in %s",
                exc,
                saved_model_dir,
            )
            _log_onnx2tf_artifacts(saved_model_dir)
            return
        LOGGER.warning("API onnx2tf non disponibile (%s), provo il CLI", exc)

    onnx2tf_bin = shutil.which("onnx2tf")
    if not onnx2tf_bin:
        if _has_onnx2tf_artifacts(saved_model_dir):
            LOGGER.warning(
                "CLI onnx2tf non trovata, riuso gli artefatti gia presenti in %s",
                saved_model_dir,
            )
            _log_onnx2tf_artifacts(saved_model_dir)
            return
        raise RuntimeError("onnx2tf non installato: impossibile convertire ONNX in artefatti TFLite/SavedModel")
    subprocess.run(
        [onnx2tf_bin, "-i", str(onnx_path), "-o", str(saved_model_dir), "--flatbuffer_direct_output_saved_model"],
        check=True,
    )
    _log_onnx2tf_artifacts(saved_model_dir)


def _has_saved_model_bundle(saved_model_dir: Path) -> bool:
    return any((saved_model_dir / name).exists() for name in ("saved_model.pb", "saved_model.pbtxt"))


def _iter_direct_tflite_artifacts(saved_model_dir: Path, quantization: str) -> Iterable[Path]:
    if not saved_model_dir.exists() or not saved_model_dir.is_dir():
        return []

    pattern_map = {
        "float16": ["*_float16.tflite", "*float16*.tflite"],
        "float32": ["*_float32.tflite", "*float32*.tflite"],
        "int8": [
            "*_full_integer_quant.tflite",
            "*_full_integer_quant_with_int16_act.tflite",
            "*_integer_quant.tflite",
            "*_integer_quant_with_int16_act.tflite",
        ],
    }
    patterns = pattern_map.get(quantization.lower(), [f"*_{quantization}.tflite", f"*{quantization}*.tflite"])
    seen: set[Path] = set()
    for pattern in patterns:
        matches = sorted(path for path in saved_model_dir.glob(pattern) if path.is_file())
        for match in matches:
            if match in seen:
                continue
            seen.add(match)
            yield match


def _find_direct_tflite_artifact(saved_model_dir: Path, quantization: str) -> Optional[Path]:
    for artifact_path in _iter_direct_tflite_artifacts(saved_model_dir, quantization):
        return artifact_path
    return None


def _has_onnx2tf_artifacts(saved_model_dir: Path) -> bool:
    if _has_saved_model_bundle(saved_model_dir):
        return True
    return any(path.is_file() for path in saved_model_dir.glob("*.tflite"))


def _log_onnx2tf_artifacts(saved_model_dir: Path) -> None:
    if _has_saved_model_bundle(saved_model_dir):
        LOGGER.info("SavedModel generato in %s", saved_model_dir)
        return
    if any(path.is_file() for path in saved_model_dir.glob("*.tflite")):
        LOGGER.info("Artefatti TFLite diretti generati in %s", saved_model_dir)
        return
    LOGGER.warning("onnx2tf non ha prodotto artefatti utilizzabili in %s", saved_model_dir)


def _validate_tflite_artifact(artifact_path: Path, quantization: str) -> bool:
    interpreter_cls = None
    runtime_name = "unknown"
    try:
        from ai_edge_litert.interpreter import Interpreter as LiteInterpreter  # type: ignore

        interpreter_cls = LiteInterpreter
        runtime_name = "ai_edge_litert"
    except Exception:
        try:
            import tensorflow as tf  # type: ignore

            interpreter_cls = tf.lite.Interpreter
            runtime_name = "tensorflow.lite"
        except Exception as exc:
            LOGGER.warning("Validazione TFLite saltata per %s: interprete non disponibile (%s)", artifact_path, exc)
            return False

    try:
        interpreter = interpreter_cls(model_path=str(artifact_path))
        interpreter.allocate_tensors()
        input_details = interpreter.get_input_details()
        output_details = interpreter.get_output_details()
    except Exception as exc:
        LOGGER.warning("Scarto artefatto TFLite %s in %s: allocate_tensors fallita (%s)", quantization, artifact_path, exc)
        return False

    if quantization == "int8":
        if not input_details or not output_details:
            LOGGER.warning("Scarto artefatto TFLite int8 in %s: metadati input/output assenti", artifact_path)
            return False

        input_dtype = np.dtype(input_details[0].get("dtype", np.float32))
        output_dtype = np.dtype(output_details[0].get("dtype", np.float32))
        if not np.issubdtype(input_dtype, np.integer) or not np.issubdtype(output_dtype, np.integer):
            LOGGER.warning(
                "Scarto artefatto TFLite int8 in %s: dtype input/output non integer (%s -> %s)",
                artifact_path,
                input_dtype,
                output_dtype,
            )
            return False

    LOGGER.info("Artefatto TFLite %s validato con %s: %s", quantization, runtime_name, artifact_path)
    return True


def _materialize_direct_tflite_artifact(saved_model_dir: Path, output_path: Path, quantization: str) -> bool:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    for artifact_path in _iter_direct_tflite_artifacts(saved_model_dir, quantization):
        if quantization == "int8" and not _validate_tflite_artifact(artifact_path, quantization):
            continue
        if artifact_path != output_path:
            shutil.copy2(artifact_path, output_path)
        LOGGER.info("TFLite %s riusato da onnx2tf in %s", quantization, output_path)
        return True
    return False


def _load_onnx_input_names(onnx_path: Path) -> list[str]:
    onnx = _require_module("onnx", "Installare onnx per l'export int8.")
    model = onnx.load(str(onnx_path), load_external_data=False)
    input_names = [str(value.name) for value in model.graph.input if getattr(value, "name", "")]
    if not input_names:
        raise RuntimeError(f"Impossibile determinare gli input ONNX da {onnx_path}")
    return input_names


def _build_quant_calibration_tensor(
    dataset_root: Path,
    output_path: Path,
    img_size: int,
    max_samples: int,
) -> Path:
    try:
        import cv2  # type: ignore
    except ImportError as exc:
        raise RuntimeError("OpenCV richiesto per la calibrazione int8") from exc

    selected = list(_iter_representative_images(dataset_root))[:max_samples]
    if not selected:
        raise RuntimeError(f"Representative dataset vuoto: {dataset_root}")

    tensors: list[np.ndarray] = []
    for image_path in selected:
        image = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
        if image is None:
            continue
        image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        image = cv2.resize(image, (img_size, img_size), interpolation=cv2.INTER_AREA)
        tensors.append(image.astype(np.float32) / 255.0)

    if not tensors:
        raise RuntimeError(f"Impossibile costruire il tensore di calibrazione da {dataset_root}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    np.save(output_path, np.stack(tensors, axis=0).astype(np.float32))
    LOGGER.info("Tensore di calibrazione int8 salvato in %s (%d campioni)", output_path, len(tensors))
    return output_path


def _convert_onnx_to_int8_tflite(
    onnx_path: Path,
    output_dir: Path,
    output_path: Path,
    representative_data: Path,
    img_size: int,
    representative_samples: int,
) -> None:
    input_names = _load_onnx_input_names(onnx_path)
    if len(input_names) != 1:
        raise RuntimeError(f"Export int8 supportato solo per modelli con un input, trovati: {input_names}")

    if output_path.exists():
        output_path.unlink()

    output_dir.mkdir(parents=True, exist_ok=True)
    calibration_path = output_dir / f"{output_path.stem}_calibration.npy"
    _build_quant_calibration_tensor(
        representative_data,
        calibration_path,
        img_size=img_size,
        max_samples=representative_samples,
    )

    quant_mean = [[[[0.5, 0.5, 0.5]]]]
    quant_std = [[[[0.5, 0.5, 0.5]]]]
    quant_inputs = [[input_names[0], str(calibration_path), quant_mean, quant_std]]

    try:
        from onnx2tf import convert  # type: ignore

        convert(
            input_onnx_file_path=str(onnx_path),
            output_folder_path=str(output_dir),
            output_integer_quantized_tflite=True,
            tflite_backend="tf_converter",
            custom_input_op_name_np_data_path=quant_inputs,
            input_quant_dtype="int8",
            output_quant_dtype="int8",
            non_verbose=True,
        )
        if _materialize_direct_tflite_artifact(output_dir, output_path, "int8"):
            return
        raise RuntimeError(f"onnx2tf non ha prodotto un TFLite int8 utilizzabile in {output_dir}")
    except Exception as exc:
        if _materialize_direct_tflite_artifact(output_dir, output_path, "int8"):
            LOGGER.warning(
                "API onnx2tf int8 terminata con errore (%s), riuso l'artefatto generato in %s",
                exc,
                output_dir,
            )
            return
        LOGGER.warning("API onnx2tf int8 non disponibile (%s), provo il CLI", exc)

    onnx2tf_bin = shutil.which("onnx2tf")
    onnx2tf_command = [onnx2tf_bin] if onnx2tf_bin else [sys.executable, "-m", "onnx2tf"]

    subprocess.run(
        onnx2tf_command + [
            "-i",
            str(onnx_path),
            "-o",
            str(output_dir),
            "-oiqt",
            "-tb",
            "tf_converter",
            "-cind",
            input_names[0],
            str(calibration_path),
            "[[[[0.5,0.5,0.5]]]]",
            "[[[[0.5,0.5,0.5]]]]",
            "--input_quant_dtype",
            "int8",
            "--output_quant_dtype",
            "int8",
        ],
        check=True,
    )
    if not _materialize_direct_tflite_artifact(output_dir, output_path, "int8"):
        if output_path.exists():
            output_path.unlink()
        raise RuntimeError(f"onnx2tf CLI non ha prodotto un TFLite int8 utilizzabile in {output_dir}")


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
    _configure_hf_hub_auth()
    set_seed(args.seed)

    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    labels_path = output_dir / args.labels_out
    onnx_path = output_dir / "efficientformer_v2_s1_33classes.onnx"
    int8_onnx_path = output_dir / "efficientformer_v2_s1_33classes_int8.onnx"
    saved_model_dir = output_dir / "efficientformer_v2_s1_saved_model"
    int8_export_dir = output_dir / "efficientformer_v2_s1_int8_export"
    float16_tflite_path = output_dir / "efficientformer_v2_s1_33classes_float16.tflite"
    int8_tflite_path = output_dir / "efficientformer_v2_s1_33classes_int8.tflite"
    stop_file = _resolve_stop_file(args)

    class_names: list[str] = []
    checkpoint_path = Path(args.checkpoint).resolve() if args.checkpoint else output_dir / "efficientformer_v2_s1_33classes.pth"

    try:
        _raise_if_stop_requested(stop_file, "startup")

        if args.mode in ("train", "all"):
            checkpoint_path = _train_model(args, class_names)
        elif not checkpoint_path.exists():
            raise RuntimeError(f"Checkpoint non trovato per export: {checkpoint_path}")

        _raise_if_stop_requested(stop_file, "post-train")

        if args.mode in ("export", "all"):
            if not class_names:
                state = _require_module("torch", "Installare torch per leggere il checkpoint").load(str(checkpoint_path), map_location="cpu")
                class_names = list((state or {}).get("class_names") or [])
            if not class_names:
                raise RuntimeError("Impossibile determinare le classi dal checkpoint. Rieseguire il fine-tuning.")

            _write_labels(labels_path, class_names)
            _raise_if_stop_requested(stop_file, "export:labels")

            model = _load_checkpoint_model(args.torch_model, checkpoint_path, len(class_names))
            _export_to_onnx(model, onnx_path, args.img_size)
            _raise_if_stop_requested(stop_file, "export:onnx")

            onnx_source = onnx_path if args.skip_onnx_simplify else _simplify_onnx(onnx_path)
            _raise_if_stop_requested(stop_file, "export:onnx-simplify")

            int8_onnx_source = onnx_source
            if args.quantization in ("int8", "both"):
                int8_model = copy.deepcopy(model)
                _enable_export_friendly_gelu(int8_model)
                _export_to_onnx(int8_model, int8_onnx_path, args.img_size)
                _raise_if_stop_requested(stop_file, "export:onnx-int8")
                int8_onnx_source = int8_onnx_path if args.skip_onnx_simplify else _simplify_onnx(int8_onnx_path)
                _raise_if_stop_requested(stop_file, "export:onnx-simplify-int8")

            _convert_onnx_to_saved_model(onnx_source, saved_model_dir)
            _raise_if_stop_requested(stop_file, "export:saved-model")

            representative_root = Path(args.representative_data or args.dataset_root).resolve()
            has_saved_model_bundle = _has_saved_model_bundle(saved_model_dir)
            if args.quantization in ("float16", "both"):
                if not _materialize_direct_tflite_artifact(saved_model_dir, float16_tflite_path, "float16"):
                    if not has_saved_model_bundle:
                        raise RuntimeError(
                            "onnx2tf non ha prodotto un TFLite float16 e non e disponibile un SavedModel standard"
                        )
                    _convert_saved_model_to_tflite(
                        saved_model_dir=saved_model_dir,
                        output_path=float16_tflite_path,
                        quantization="float16",
                        representative_data=representative_root,
                        img_size=args.img_size,
                        representative_samples=args.representative_samples,
                        allow_float_fallback=args.allow_float_fallback,
                    )
                _raise_if_stop_requested(stop_file, "export:tflite-float16")
            if args.quantization in ("int8", "both"):
                try:
                    _convert_onnx_to_int8_tflite(
                        onnx_path=int8_onnx_source,
                        output_dir=int8_export_dir,
                        output_path=int8_tflite_path,
                        representative_data=representative_root,
                        img_size=args.img_size,
                        representative_samples=args.representative_samples,
                    )
                    _raise_if_stop_requested(stop_file, "export:tflite-int8")
                except Exception:
                    if has_saved_model_bundle:
                        try:
                            _convert_saved_model_to_tflite(
                                saved_model_dir=saved_model_dir,
                                output_path=int8_tflite_path,
                                quantization="int8",
                                representative_data=representative_root,
                                img_size=args.img_size,
                                representative_samples=args.representative_samples,
                                allow_float_fallback=args.allow_float_fallback,
                            )
                        except Exception:
                            if args.quantization == "int8":
                                raise
                            LOGGER.warning("INT8 non generato: continuo con il float16 richiesto dal runtime", exc_info=True)
                        else:
                            _raise_if_stop_requested(stop_file, "export:tflite-int8")
                    elif args.quantization == "int8":
                        raise RuntimeError(
                            "Quantizzazione int8 richiesta ma non disponibile: manca SavedModel standard e onnx2tf non ha prodotto un artefatto int8"
                        )
                    else:
                        LOGGER.warning(
                            "INT8 non generato: impossibile ottenere una variante int8 eseguibile da ONNX/SavedModel in questo ambiente",
                            exc_info=True,
                        )
    except GracefulStopRequested as exc:
        LOGGER.warning("%s", exc)
        print(json.dumps({
            "status": "stopped",
            "reason": str(exc),
            "checkpoint": str(checkpoint_path),
            "onnx": str(onnx_path),
            "saved_model": str(saved_model_dir),
            "float16_tflite": str(float16_tflite_path),
            "int8_tflite": str(int8_tflite_path),
            "labels": str(labels_path),
        }, ensure_ascii=False, indent=2))
        return 130

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
        "status": "completed",
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
