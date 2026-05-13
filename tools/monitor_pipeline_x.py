#!/usr/bin/env python3
"""Monitor live testuale per Pipeline X ed EfficientFormer training."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any


STEP_ORDER = ["train", "export", "evaluate", "benchmark", "dissemination"]
STEP_LABELS = {
    "train": "Fine-tuning EfficientFormer",
    "export": "Export ONNX/SavedModel/TFLite",
    "evaluate": "Evaluate backend vision",
    "benchmark": "Benchmark backend vision",
    "dissemination": "ATTIVITA' DIVULGATIVE",
    "done": "Completata",
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Monitor live per Pipeline X")
    parser.add_argument("--pipeline-state", default="models/pipeline_x_state.json", help="Path state file pipeline")
    parser.add_argument(
        "--training-state",
        default="models/efficientformer_v2_s1_33classes.state.json",
        help="Path state file fine-tuning EfficientFormer",
    )
    parser.add_argument("--interval", type=float, default=5.0, help="Intervallo refresh in secondi")
    parser.add_argument("--watch", action="store_true", help="Aggiorna continuamente finche la pipeline termina")
    parser.add_argument(
        "--until-train-closes",
        action="store_true",
        help="Attende finche la pipeline esce dallo step train, poi stampa lo snapshot finale",
    )
    parser.add_argument(
        "--until-next-checkpoint",
        action="store_true",
        help="Attende finche completed_epochs aumenta rispetto allo stato iniziale, poi stampa lo snapshot finale",
    )
    parser.add_argument("--width", type=int, default=72, help="Larghezza barra di avanzamento")
    return parser


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists() or not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def clamp(value: float, min_value: float = 0.0, max_value: float = 1.0) -> float:
    return max(min_value, min(max_value, value))


def render_bar(label: str, fraction: float, width: int) -> str:
    fraction = clamp(fraction)
    filled = int(round(width * fraction))
    bar = "#" * filled + "-" * (width - filled)
    return f"{label:<12} [{bar}] {fraction * 100:6.2f}%"


def compute_training_fraction(training_state: dict[str, Any]) -> float:
    total_epochs = int(training_state.get("epochs", 0) or 0)
    completed_epochs = int(training_state.get("completed_epochs", 0) or 0)
    if total_epochs <= 0:
        return 0.0
    return clamp(completed_epochs / total_epochs)


def compute_pipeline_fraction(pipeline_state: dict[str, Any], training_state: dict[str, Any]) -> float:
    completed_steps = set(pipeline_state.get("completed_steps") or [])
    current_step = str(pipeline_state.get("current_step") or "")
    completed = sum(1 for step in STEP_ORDER if step in completed_steps)
    partial = 0.0
    if current_step == "train":
        partial = compute_training_fraction(training_state)
    elif current_step in STEP_ORDER and current_step not in completed_steps:
        partial = 0.0
    return clamp((completed + partial) / max(len(STEP_ORDER), 1))


def resolve_training_status(pipeline_state: dict[str, Any], training_state: dict[str, Any]) -> str:
    pipeline_status = str(pipeline_state.get("status") or "").lower()
    current_step = str(pipeline_state.get("current_step") or "")
    training_status = str(training_state.get("status") or "waiting").lower()

    # Durante il resume il training state resta fermo all'ultimo snapshot
    # finche non termina la prossima epoca, quindi qui mostriamo lo stato reale.
    if pipeline_status == "running" and current_step == "train":
        return "running"

    return training_status or "waiting"


def terminal_clear() -> str:
    return "\033[2J\033[H"


def train_step_is_active(pipeline_state: dict[str, Any]) -> bool:
    return (
        str(pipeline_state.get("status") or "").lower() == "running"
        and str(pipeline_state.get("current_step") or "") == "train"
    )


def completed_epochs(training_state: dict[str, Any]) -> int:
    return int(training_state.get("completed_epochs", 0) or 0)


def format_snapshot(pipeline_state: dict[str, Any], training_state: dict[str, Any], width: int) -> str:
    lines: list[str] = []
    status = str(pipeline_state.get("status") or "starting").upper()
    current_step = str(pipeline_state.get("current_step") or "train")
    current_label = STEP_LABELS.get(current_step, current_step or "n/d")
    training_fraction = compute_training_fraction(training_state)
    pipeline_fraction = compute_pipeline_fraction(pipeline_state, training_state)
    completed_epochs = int(training_state.get("completed_epochs", 0) or 0)
    total_epochs = int(training_state.get("epochs", 0) or 0)
    best_acc = training_state.get("best_acc")
    training_status = resolve_training_status(pipeline_state, training_state)
    completed_steps = ", ".join(pipeline_state.get("completed_steps") or []) or "nessuno"

    lines.append("=" * (width + 28))
    lines.append("PIPELINE X - MONITOR LIVE")
    lines.append("=" * (width + 28))
    lines.append(f"Stato pipeline : {status}")
    lines.append(f"Step corrente  : {current_label}")
    lines.append(f"Step completati: {completed_steps}")
    lines.append("")
    lines.append(render_bar("PIPELINE", pipeline_fraction, width))
    lines.append(render_bar("TRAINING", training_fraction, width))
    lines.append("")

    if total_epochs > 0:
        if completed_epochs < total_epochs:
            lines.append(f"Epoche        : {completed_epochs}/{total_epochs} completate, epoca {completed_epochs + 1} in corso")
        else:
            lines.append(f"Epoche        : {completed_epochs}/{total_epochs} completate")
    else:
        lines.append("Epoche        : training avviato, prima epoca non ancora consolidata")

    lines.append(f"Stato train   : {training_status}")
    if isinstance(best_acc, (float, int)):
        lines.append(f"Best val acc  : {float(best_acc) * 100:.2f}%")
    else:
        lines.append("Best val acc  : n/d")

    message = str(pipeline_state.get("message") or "")
    if message:
        lines.append(f"Messaggio     : {message}")

    stop_file = str(pipeline_state.get("stop_file") or "")
    if stop_file:
        lines.append(f"Stop file     : {stop_file}")

    lines.append("=" * (width + 28))
    return "\n".join(lines)


def main() -> int:
    args = build_parser().parse_args()
    pipeline_state_path = Path(args.pipeline_state).resolve()
    training_state_path = Path(args.training_state).resolve()
    baseline_completed_epochs = completed_epochs(load_json(training_state_path)) if args.until_next_checkpoint else 0

    while True:
        pipeline_state = load_json(pipeline_state_path)
        training_state = load_json(training_state_path)
        snapshot = format_snapshot(pipeline_state, training_state, args.width)

        if args.until_train_closes and not train_step_is_active(pipeline_state):
            print(snapshot)
            return 0
        if args.until_next_checkpoint and completed_epochs(training_state) > baseline_completed_epochs:
            print(snapshot)
            return 0

        if args.watch:
            sys.stdout.write(terminal_clear())
            sys.stdout.write(snapshot + "\n")
            sys.stdout.flush()
        elif not args.until_train_closes and not args.until_next_checkpoint:
            print(snapshot)
            return 0

        status = str(pipeline_state.get("status") or "").lower()
        if status in {"completed", "failed", "stopped"}:
            return 0
        time.sleep(max(args.interval, 0.5))


if __name__ == "__main__":
    raise SystemExit(main())