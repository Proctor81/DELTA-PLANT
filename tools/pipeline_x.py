#!/usr/bin/env python3
"""Orchestratore resumable per la Pipeline X EfficientFormer."""

from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence


LOGGER = logging.getLogger("delta.pipeline_x")


class PipelineStopRequested(RuntimeError):
    """Stop cooperativo richiesto dall'operatore."""


@dataclass(frozen=True)
class PipelineStep:
    key: str
    label: str
    command: list[str]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Pipeline X EfficientFormer resumable")
    parser.add_argument("--dataset-root", default="datasets/training_33classes", help="Root dataset training")
    parser.add_argument(
        "--evaluation-dataset-root",
        default="",
        help="Validation set ImageFolder per evaluation finale (default: <dataset-root>/validation)",
    )
    parser.add_argument("--output-dir", default="models", help="Directory output artefatti")
    parser.add_argument("--benchmark-image", default="", help="Immagine benchmark (default: prima immagine nel validation set)")
    parser.add_argument("--runs", type=int, default=50, help="Iterazioni benchmark")
    parser.add_argument("--warmup", type=int, default=5, help="Warmup benchmark")
    parser.add_argument("--epochs", type=int, default=8, help="Epoche fine-tuning EfficientFormer")
    parser.add_argument("--batch-size", type=int, default=16, help="Batch size fine-tuning")
    parser.add_argument("--learning-rate", type=float, default=3e-4, help="Learning rate fine-tuning")
    parser.add_argument("--weight-decay", type=float, default=1e-4, help="Weight decay fine-tuning")
    parser.add_argument("--num-workers", type=int, default=2, help="DataLoader workers")
    parser.add_argument("--num-classes", type=int, default=33, help="Numero classi target")
    parser.add_argument(
        "--dissemination-output-dir",
        default="logs/attivita_divulgative",
        help="Directory output per le ATTIVITA' DIVULGATIVE",
    )
    parser.add_argument("--resume", action="store_true", help="Riprende dalla state file della pipeline")
    parser.add_argument("--state-file", default="", help="Path JSON stato pipeline")
    parser.add_argument("--stop-file", default="", help="Path file sentinella stop cooperativo")
    parser.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    return parser


def resolve_repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def resolve_state_file(args, output_dir: Path) -> Path:
    if args.state_file:
        return Path(args.state_file).resolve()
    return output_dir / "pipeline_x_state.json"


def resolve_stop_file(args, output_dir: Path) -> Path:
    if args.stop_file:
        return Path(args.stop_file).resolve()
    return output_dir / "pipeline_x.stop"


def resolve_evaluation_root(args) -> Path:
    if args.evaluation_dataset_root:
        return Path(args.evaluation_dataset_root).resolve()
    return (Path(args.dataset_root).resolve() / "validation")


def discover_benchmark_image(explicit_image: str, evaluation_root: Path) -> Path:
    if explicit_image:
        return Path(explicit_image).resolve()

    exts = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}
    for image_path in sorted(evaluation_root.rglob("*")):
        if image_path.is_file() and image_path.suffix.lower() in exts:
            return image_path
    raise RuntimeError(f"Nessuna immagine disponibile per benchmark in {evaluation_root}")


def load_state(state_path: Path) -> dict:
    if not state_path.exists() or not state_path.is_file():
        return {}
    try:
        return json.loads(state_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        LOGGER.warning("State file pipeline corrotta: %s", state_path)
        return {}


def write_state(
    state_path: Path,
    *,
    status: str,
    current_step: str,
    completed_steps: list[str],
    stop_file: Path,
    last_command: Sequence[str] | None = None,
    last_exit_code: int | None = None,
    message: str = "",
) -> None:
    payload = {
        "pipeline": "pipeline_x",
        "status": status,
        "current_step": current_step,
        "completed_steps": completed_steps,
        "stop_file": str(stop_file),
        "last_command": list(last_command or []),
        "last_exit_code": last_exit_code,
        "message": message,
    }
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def stop_requested(stop_file: Path) -> bool:
    return stop_file.exists()


def raise_if_stop_requested(stop_file: Path, current_step: str) -> None:
    if stop_requested(stop_file):
        raise PipelineStopRequested(f"Stop richiesto prima/dopo lo step {current_step}")


def build_steps(args, repo_root: Path, output_dir: Path, stop_file: Path) -> list[PipelineStep]:
    train_state_file = output_dir / "efficientformer_v2_s1_33classes.state.json"
    checkpoint_path = output_dir / "efficientformer_v2_s1_33classes.pth"
    evaluation_root = resolve_evaluation_root(args)
    benchmark_image = discover_benchmark_image(args.benchmark_image, evaluation_root)
    eval_output_dir = repo_root / "logs" / "vision_eval"
    benchmark_output = repo_root / "logs" / "vision_benchmark.json"
    dissemination_output_dir = Path(args.dissemination_output_dir).resolve()
    manual_script = repo_root / "Manuale" / "genera_manuale.py"
    return [
        PipelineStep(
            key="train",
            label="Fine-tuning EfficientFormer",
            command=[
                sys.executable,
                "ai/export_efficientformer_tflite.py",
                "--dataset-root", args.dataset_root,
                "--output-dir", str(output_dir),
                "--mode", "train",
                "--epochs", str(args.epochs),
                "--batch-size", str(args.batch_size),
                "--learning-rate", str(args.learning_rate),
                "--weight-decay", str(args.weight_decay),
                "--num-workers", str(args.num_workers),
                "--num-classes", str(args.num_classes),
                "--resume",
                "--train-state-file", str(train_state_file),
                "--stop-file", str(stop_file),
                "--log-level", args.log_level,
            ],
        ),
        PipelineStep(
            key="export",
            label="Export ONNX/SavedModel/TFLite",
            command=[
                sys.executable,
                "ai/export_efficientformer_tflite.py",
                "--dataset-root", args.dataset_root,
                "--output-dir", str(output_dir),
                "--mode", "export",
                "--quantization", "both",
                "--checkpoint", str(checkpoint_path),
                "--train-state-file", str(train_state_file),
                "--stop-file", str(stop_file),
                "--log-level", args.log_level,
            ],
        ),
        PipelineStep(
            key="evaluate",
            label="Evaluate backend vision",
            command=[
                sys.executable,
                "ai/evaluate_vision_backends.py",
                "--dataset-root", str(evaluation_root),
                "--model-keys", "generale", "efficientformer",
                "--output-dir", str(eval_output_dir),
            ],
        ),
        PipelineStep(
            key="benchmark",
            label="Benchmark backend vision",
            command=[
                sys.executable,
                "tools/benchmark_vision_models.py",
                "--model-keys", "generale", "efficientformer",
                "--image", str(benchmark_image),
                "--runs", str(args.runs),
                "--warmup", str(args.warmup),
                "--output", str(benchmark_output),
            ],
        ),
        PipelineStep(
            key="dissemination",
            label="ATTIVITA' DIVULGATIVE",
            command=[
                sys.executable,
                "tools/prepare_dissemination_artifacts.py",
                "--eval-summary", str(eval_output_dir / "comparison_summary.json"),
                "--benchmark-summary", str(benchmark_output),
                "--output-dir", str(dissemination_output_dir),
            ],
        ),
        PipelineStep(
            key="manual",
            label="Rigenerazione manuale utente",
            command=[
                sys.executable,
                str(manual_script),
            ],
        ),
    ]


def run_step(step: PipelineStep, repo_root: Path) -> int:
    env = os.environ.copy()
    existing_pythonpath = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = f"{repo_root}:{existing_pythonpath}" if existing_pythonpath else str(repo_root)
    LOGGER.info("Avvio step %s", step.label)
    process = subprocess.run(step.command, cwd=str(repo_root), env=env)
    return int(process.returncode)


def main() -> int:
    args = build_parser().parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )

    repo_root = resolve_repo_root()
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    state_path = resolve_state_file(args, output_dir)
    stop_file = resolve_stop_file(args, output_dir)
    steps = build_steps(args, repo_root, output_dir, stop_file)

    state = load_state(state_path) if args.resume else {}
    completed_steps = list(state.get("completed_steps") or [])

    try:
        for step in steps:
            if step.key in completed_steps:
                LOGGER.info("Step gia completato, skip: %s", step.label)
                continue

            raise_if_stop_requested(stop_file, step.key)
            write_state(
                state_path,
                status="running",
                current_step=step.key,
                completed_steps=completed_steps,
                stop_file=stop_file,
                last_command=step.command,
                message=step.label,
            )
            exit_code = run_step(step, repo_root)
            if exit_code == 130:
                write_state(
                    state_path,
                    status="stopped",
                    current_step=step.key,
                    completed_steps=completed_steps,
                    stop_file=stop_file,
                    last_command=step.command,
                    last_exit_code=exit_code,
                    message=f"Arresto cooperativo durante {step.label}",
                )
                return 130
            if exit_code != 0:
                write_state(
                    state_path,
                    status="failed",
                    current_step=step.key,
                    completed_steps=completed_steps,
                    stop_file=stop_file,
                    last_command=step.command,
                    last_exit_code=exit_code,
                    message=f"Step fallito: {step.label}",
                )
                return exit_code

            completed_steps.append(step.key)
            write_state(
                state_path,
                status="running",
                current_step=step.key,
                completed_steps=completed_steps,
                stop_file=stop_file,
                last_command=step.command,
                last_exit_code=exit_code,
                message=f"Step completato: {step.label}",
            )
            raise_if_stop_requested(stop_file, step.key)
    except PipelineStopRequested as exc:
        write_state(
            state_path,
            status="stopped",
            current_step=state.get("current_step", steps[0].key if steps else "done"),
            completed_steps=completed_steps,
            stop_file=stop_file,
            message=str(exc),
        )
        LOGGER.warning("%s", exc)
        return 130

    if stop_file.exists():
        stop_file.unlink()

    write_state(
        state_path,
        status="completed",
        current_step="done",
        completed_steps=completed_steps,
        stop_file=stop_file,
        message="Pipeline completata",
    )
    print(json.dumps({
        "status": "completed",
        "state_file": str(state_path),
        "completed_steps": completed_steps,
    }, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())