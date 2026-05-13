#!/usr/bin/env python3
"""Accoda ATTIVITA' DIVULGATIVE alla Pipeline X gia in esecuzione."""

from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


LOGGER = logging.getLogger("delta.pipeline_x.queue")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Accoda le ATTIVITA' DIVULGATIVE al run corrente di Pipeline X")
    parser.add_argument("--pipeline-state", default="models/pipeline_x_state.json", help="Path state file Pipeline X")
    parser.add_argument("--poll-interval", type=float, default=15.0, help="Intervallo di polling in secondi")
    parser.add_argument("--eval-summary", default="logs/vision_eval/comparison_summary.json", help="Path evaluation summary")
    parser.add_argument("--benchmark-summary", default="logs/vision_benchmark.json", help="Path benchmark summary")
    parser.add_argument("--output-dir", default="logs/attivita_divulgative", help="Directory output pacchetto divulgativo")
    parser.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    return parser


def load_state(path: Path) -> dict[str, Any]:
    if not path.exists() or not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        LOGGER.warning("State file pipeline corrotta: %s", path)
        return {}


def write_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")


def dissemination_output_exists(output_dir: Path) -> bool:
    return (output_dir / "dissemination_summary.json").exists()


def run_dissemination(repo_root: Path, args) -> int:
    env = os.environ.copy()
    existing_pythonpath = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = f"{repo_root}:{existing_pythonpath}" if existing_pythonpath else str(repo_root)
    command = [
        sys.executable,
        "tools/prepare_dissemination_artifacts.py",
        "--eval-summary", str(Path(args.eval_summary).resolve()),
        "--benchmark-summary", str(Path(args.benchmark_summary).resolve()),
        "--output-dir", str(Path(args.output_dir).resolve()),
    ]
    result = subprocess.run(command, cwd=str(repo_root), env=env)
    return int(result.returncode)


def main() -> int:
    args = build_parser().parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )

    repo_root = Path(__file__).resolve().parent.parent
    pipeline_state_path = Path(args.pipeline_state).resolve()
    output_dir = Path(args.output_dir).resolve()

    while True:
        state = load_state(pipeline_state_path)
        status = str(state.get("status") or "waiting").lower()
        completed_steps = list(state.get("completed_steps") or [])

        if "dissemination" in completed_steps or dissemination_output_exists(output_dir):
            LOGGER.info("ATTIVITA' DIVULGATIVE gia' completate o disponibili")
            return 0

        if status == "failed":
            LOGGER.error("Pipeline X fallita: attivita' divulgative non eseguite")
            return 1

        if status == "completed":
            state["status"] = "running"
            state["current_step"] = "dissemination"
            state["message"] = "ATTIVITA' DIVULGATIVE"
            write_state(pipeline_state_path, state)

            exit_code = run_dissemination(repo_root, args)
            refreshed_state = load_state(pipeline_state_path)
            refreshed_completed = list(refreshed_state.get("completed_steps") or completed_steps)
            if exit_code == 0:
                if "dissemination" not in refreshed_completed:
                    refreshed_completed.append("dissemination")
                refreshed_state["completed_steps"] = refreshed_completed
                refreshed_state["status"] = "completed"
                refreshed_state["current_step"] = "done"
                refreshed_state["last_exit_code"] = 0
                refreshed_state["message"] = "Pipeline completata + ATTIVITA' DIVULGATIVE"
                write_state(pipeline_state_path, refreshed_state)
                LOGGER.info("ATTIVITA' DIVULGATIVE completate")
                return 0

            refreshed_state["status"] = "failed"
            refreshed_state["current_step"] = "dissemination"
            refreshed_state["last_exit_code"] = exit_code
            refreshed_state["message"] = "Step fallito: ATTIVITA' DIVULGATIVE"
            write_state(pipeline_state_path, refreshed_state)
            LOGGER.error("ATTIVITA' DIVULGATIVE fallite con exit code %d", exit_code)
            return exit_code

        time.sleep(max(args.poll_interval, 2.0))


if __name__ == "__main__":
    raise SystemExit(main())