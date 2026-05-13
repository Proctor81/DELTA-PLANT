#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from datetime import datetime
from pathlib import Path


STEP_HEADERS = {
    "Training + export EfficientFormerV2-S1 -> ONNX/TFLite": "training_export",
    "Valutazione backend generale vs efficientformer": "evaluation",
    "Benchmark edge backend generale vs efficientformer": "benchmark",
    "Pipeline completata con successo": "completed",
}

PIPELINE_PATTERNS = [
    "tools/run_efficientformer_pipeline.sh",
    "ai/export_efficientformer_tflite.py",
    "ai/evaluate_vision_backends.py",
    "tools/benchmark_vision_models.py",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Aggiorna una tabella di stato per la pipeline EfficientFormer")
    parser.add_argument("--run-dir", required=True, help="Directory del run pipeline")
    parser.add_argument("--report-file", default="", help="File markdown da aggiornare")
    parser.add_argument("--timer-unit", default="", help="Nome del timer systemd da fermare a pipeline completata")
    parser.add_argument("--notify", action="store_true", help="Invia notify-send se disponibile")
    return parser.parse_args()


def _read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def _detect_process_running() -> bool:
    result = subprocess.run(
        ["ps", "-eo", "command="],
        check=False,
        capture_output=True,
        text=True,
    )
    commands = result.stdout.splitlines()
    return any(any(pattern in command for pattern in PIPELINE_PATTERNS) for command in commands)


def _latest_step(log_text: str) -> str:
    matches = re.findall(r"^\[(.*?)\]\s+(.*)$", log_text, flags=re.MULTILINE)
    for _, label in reversed(matches):
        if label in STEP_HEADERS:
            return STEP_HEADERS[label]
    return "starting"


def _last_epoch_metrics(log_text: str) -> tuple[str, str, str]:
    matches = re.findall(
        r"Epoch\s+(\d+)/(\d+)\s+\|\s+train_loss=([0-9.]+)\s+train_acc=([0-9.]+)\s+\|\s+val_loss=([0-9.]+)\s+val_acc=([0-9.]+)",
        log_text,
    )
    if not matches:
        return "0/8", "-", "-"
    epoch, total, _, train_acc, _, val_acc = matches[-1]
    return f"{epoch}/{total}", train_acc, val_acc


def _last_log_line(log_text: str) -> str:
    lines = [line.strip() for line in log_text.splitlines() if line.strip()]
    return lines[-1] if lines else "nessun log disponibile"


def _artifact_status(run_dir: Path) -> str:
    root = run_dir.parent.parent.parent
    models_dir = root / "models"
    checks = {
        "ckpt": models_dir / "efficientformer_v2_s1_33classes.pth",
        "fp16": models_dir / "efficientformer_v2_s1_33classes_float16.tflite",
        "int8": models_dir / "efficientformer_v2_s1_33classes_int8.tflite",
        "eval": run_dir / "vision_eval" / "comparison_summary.json",
        "bench": run_dir / "vision_benchmark.json",
    }
    ready = [label for label, path in checks.items() if path.exists()]
    return ", ".join(ready) if ready else "nessuno"


def _pipeline_status(step: str, running: bool, log_text: str) -> str:
    if "Pipeline completata con successo" in log_text:
        return "completata"
    if running:
        return "in esecuzione"
    if log_text:
        return "interrotta"
    return "non avviata"


def _load_existing_rows(report_file: Path) -> list[str]:
    if not report_file.exists():
        return []
    content = report_file.read_text(encoding="utf-8", errors="replace").splitlines()
    rows: list[str] = []
    for line in content:
        if not line.startswith("| "):
            continue
        if line.startswith("| Timestamp |"):
            continue
        if line.startswith("| --- |"):
            continue
        rows.append(line)
    return rows


def _write_report(report_file: Path, run_dir: Path, row: str) -> None:
    existing_rows = _load_existing_rows(report_file)
    report_file.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Resoconto Pipeline EfficientFormer",
        "",
        f"Run: {run_dir}",
        "",
        "| Timestamp | Stato | Fase | Epoca | Train acc | Val acc | Artefatti | Ultimo evento |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
        *existing_rows,
        row,
        "",
    ]
    report_file.write_text("\n".join(lines), encoding="utf-8")


def _notify(summary: str) -> None:
    if not os.environ.get("DISPLAY"):
        return
    if not shutil_which("notify-send"):
        return
    subprocess.run(["notify-send", "DELTA Pipeline", summary], check=False)


def shutil_which(command: str) -> str | None:
    result = subprocess.run(["bash", "-lc", f"command -v {command}"], check=False, capture_output=True, text=True)
    value = result.stdout.strip()
    return value or None


def _stop_timer(timer_unit: str) -> None:
    if not timer_unit:
        return
    subprocess.run(["systemctl", "--user", "stop", f"{timer_unit}.timer"], check=False)
    subprocess.run(["systemctl", "--user", "stop", f"{timer_unit}.service"], check=False)


def main() -> int:
    args = parse_args()
    run_dir = Path(args.run_dir).resolve()
    report_file = Path(args.report_file).resolve() if args.report_file else run_dir / "progress_table.md"
    log_file = run_dir / "pipeline.log"

    log_text = _read_text(log_file)
    running = _detect_process_running()
    step = _latest_step(log_text)
    epoch, train_acc, val_acc = _last_epoch_metrics(log_text)
    status = _pipeline_status(step, running, log_text)
    artifacts = _artifact_status(run_dir)
    last_event = _last_log_line(log_text).replace("|", "/")[:140]
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    row = f"| {timestamp} | {status} | {step} | {epoch} | {train_acc} | {val_acc} | {artifacts} | {last_event} |"
    _write_report(report_file, run_dir, row)

    summary = f"{status} | {step} | epoca {epoch} | artefatti: {artifacts}"
    if args.notify:
        _notify(summary)

    print(summary)

    if status in {"completata", "interrotta"}:
        _stop_timer(args.timer_unit)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())