#!/usr/bin/env python3
"""
Benchmark latency/throughput per backend vision DELTA su device edge.

Esempio:
    python tools/benchmark_vision_models.py \
      --model-keys generale efficientformer \
      --image models/validation_sample.jpg \
      --runs 100 --warmup 10
"""

from __future__ import annotations

import argparse
import json
import logging
import statistics
import sys
import time
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from vision.vision_service import VisionService

LOGGER = logging.getLogger("delta.tools.benchmark")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Benchmark backend vision DELTA")
    parser.add_argument("--model-keys", nargs="+", default=["generale", "efficientformer"], help="Model keys da benchmarkare")
    parser.add_argument("--image", default="models/validation_sample.jpg", help="Immagine di benchmark")
    parser.add_argument("--runs", type=int, default=50, help="Numero iterazioni misurate")
    parser.add_argument("--warmup", type=int, default=5, help="Numero iterazioni warmup")
    parser.add_argument("--output", default="logs/vision_benchmark.json", help="JSON di output")
    parser.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    return parser


def percentile(values: list[float], ratio: float) -> float:
    if not values:
        return 0.0
    index = min(len(values) - 1, max(0, int(round((len(values) - 1) * ratio))))
    ordered = sorted(values)
    return ordered[index]


def benchmark_model(model_key: str, image_path: Path, runs: int, warmup: int) -> dict[str, Any]:
    service = VisionService(model_key=model_key)
    if not service.is_ready:
        raise RuntimeError(f"Backend non pronto per {model_key}")

    for _ in range(warmup):
        service.classify(str(image_path))

    latencies_ms: list[float] = []
    for _ in range(runs):
        started = time.perf_counter()
        _ = service.classify(str(image_path))
        latencies_ms.append((time.perf_counter() - started) * 1000.0)

    avg_ms = statistics.fmean(latencies_ms) if latencies_ms else 0.0
    throughput = 1000.0 / avg_ms if avg_ms > 0 else 0.0
    return {
        "model_key": model_key,
        "active_model": service.active_model,
        "backend": service.backend_type,
        "runs": runs,
        "warmup": warmup,
        "avg_ms": round(avg_ms, 3),
        "min_ms": round(min(latencies_ms), 3),
        "p50_ms": round(percentile(latencies_ms, 0.50), 3),
        "p95_ms": round(percentile(latencies_ms, 0.95), 3),
        "max_ms": round(max(latencies_ms), 3),
        "throughput_fps": round(throughput, 3),
    }


def main() -> int:
    args = build_parser().parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )

    image_path = Path(args.image).resolve()
    if not image_path.exists():
        raise RuntimeError(f"Immagine benchmark non trovata: {image_path}")

    output_path = Path(args.output).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    results = [benchmark_model(model_key, image_path, args.runs, args.warmup) for model_key in args.model_keys]
    output_path.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps(results, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())