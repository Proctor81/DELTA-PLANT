#!/usr/bin/env python3
"""Prepara il pacchetto ATTIVITA' DIVULGATIVE dai risultati Pipeline X."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parent.parent


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Prepara artefatti divulgativi da benchmark ed evaluation")
    parser.add_argument(
        "--eval-summary",
        default="logs/vision_eval/comparison_summary.json",
        help="Path comparison_summary.json generato dalla evaluation",
    )
    parser.add_argument(
        "--benchmark-summary",
        default="logs/vision_benchmark.json",
        help="Path JSON generato dal benchmark",
    )
    parser.add_argument(
        "--output-dir",
        default="logs/attivita_divulgative",
        help="Directory output pacchetto divulgativo",
    )
    return parser


def _load_json(path: Path) -> Any:
    if not path.exists() or not path.is_file():
        raise RuntimeError(f"File non trovato: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _index_by_model_key(items: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for item in items:
        model_key = str(item.get("model_key") or "")
        if model_key:
            indexed[model_key] = item
    return indexed


def _format_pct(value: Any) -> str:
    if value is None:
        return "n/d"
    return f"{float(value) * 100:.2f}%"


def _format_ms(value: Any) -> str:
    if value is None:
        return "n/d"
    return f"{float(value):.3f} ms"


def _format_fps(value: Any) -> str:
    if value is None:
        return "n/d"
    return f"{float(value):.3f} fps"


def _display_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(REPO_ROOT))
    except ValueError:
        return str(resolved)


def _model_eval_row(label: str, row: dict[str, Any]) -> str:
    return (
        f"| {label} | {_format_pct(row.get('accuracy_top1'))} | {_format_pct(row.get('accuracy_top3'))} "
        f"| {_format_pct(row.get('macro_f1'))} | {_format_pct(row.get('mean_confidence'))} |"
    )


def _model_bench_row(label: str, row: dict[str, Any]) -> str:
    return (
        f"| {label} | {_format_ms(row.get('avg_ms'))} | {_format_ms(row.get('p95_ms'))} "
        f"| {_format_ms(row.get('max_ms'))} | {_format_fps(row.get('throughput_fps'))} |"
    )


def _build_summary(eval_rows: dict[str, dict[str, Any]], bench_rows: dict[str, dict[str, Any]], args) -> dict[str, Any]:
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    eval_summary_path = Path(args.eval_summary)
    benchmark_summary_path = Path(args.benchmark_summary)
    return {
        "generated_at": generated_at,
        "eval_summary": _display_path(eval_summary_path),
        "benchmark_summary": _display_path(benchmark_summary_path),
        "models": {
            "generale": {
                "evaluation": eval_rows.get("generale", {}),
                "benchmark": bench_rows.get("generale", {}),
            },
            "efficientformer": {
                "evaluation": eval_rows.get("efficientformer", {}),
                "benchmark": bench_rows.get("efficientformer", {}),
            },
        },
        "publication_targets": [
            "README.md",
            "MODEL_CARD.md",
            "RELEASE.md",
        ],
    }


def _write_markdown_files(output_dir: Path, summary: dict[str, Any]) -> dict[str, str]:
    generale_eval = summary["models"]["generale"]["evaluation"]
    generale_bench = summary["models"]["generale"]["benchmark"]
    efficientformer_eval = summary["models"]["efficientformer"]["evaluation"]
    efficientformer_bench = summary["models"]["efficientformer"]["benchmark"]

    attivita_divulgative_md = f"""# ATTIVITA' DIVULGATIVE - Pipeline X

Generato il: {summary['generated_at']}

## Obiettivo

Questo pacchetto consolida i risultati di 'quanto e' bravo' e 'quanto e' veloce' per preparare la pubblicazione tecnica e divulgativa su GitHub.

## Quanto e' bravo

| Modello | Accuracy top-1 | Accuracy top-3 | Macro-F1 | Confidenza media |
| --- | --- | --- | --- | --- |
{_model_eval_row('Generale', generale_eval)}
{_model_eval_row('EfficientFormer', efficientformer_eval)}

## Quanto e' veloce

| Modello | Avg latency | P95 latency | Max latency | Throughput |
| --- | --- | --- | --- | --- |
{_model_bench_row('Generale', generale_bench)}
{_model_bench_row('EfficientFormer', efficientformer_bench)}

## Messaggio per comunita' scientifica

- Pubblicare accuracy top-1, top-3 e macro-F1 con link ai report completi.
- Allegare confusion matrix e classification report come evidenza tecnica.
- Contestualizzare dataset, hardware e limiti sperimentali.

## Messaggio per comunita' finanziaria e industriale

- Evidenziare latenza media, p95 e throughput on-device su Raspberry Pi 5.
- Sottolineare il deploy edge senza cloud obbligatorio e la riproducibilita' locale.
- Distinguere chiaramente baseline stabile e backend EfficientFormer validato.

## Artefatti sorgente

- Evaluation summary: {summary['eval_summary']}
- Benchmark summary: {summary['benchmark_summary']}
- Output dir divulgativo: {_display_path(output_dir)}
"""

    readme_snippet_md = f"""## EfficientFormerV2-S1 - Risultati validati su Pipeline X

| Metrica | Generale | EfficientFormer |
| --- | --- | --- |
| Accuracy top-1 | {_format_pct(generale_eval.get('accuracy_top1'))} | {_format_pct(efficientformer_eval.get('accuracy_top1'))} |
| Accuracy top-3 | {_format_pct(generale_eval.get('accuracy_top3'))} | {_format_pct(efficientformer_eval.get('accuracy_top3'))} |
| Macro-F1 | {_format_pct(generale_eval.get('macro_f1'))} | {_format_pct(efficientformer_eval.get('macro_f1'))} |
| Avg latency | {_format_ms(generale_bench.get('avg_ms'))} | {_format_ms(efficientformer_bench.get('avg_ms'))} |
| P95 latency | {_format_ms(generale_bench.get('p95_ms'))} | {_format_ms(efficientformer_bench.get('p95_ms'))} |
| Throughput | {_format_fps(generale_bench.get('throughput_fps'))} | {_format_fps(efficientformer_bench.get('throughput_fps'))} |

I numeri completi sono disponibili nei report generati dalla Pipeline X e validati su Raspberry Pi 5.
"""

    model_card_draft_md = f"""### EfficientFormerV2-S1 - Risultati Pipeline X ({summary['generated_at']})

- Accuracy top-1: {_format_pct(efficientformer_eval.get('accuracy_top1'))}
- Accuracy top-3: {_format_pct(efficientformer_eval.get('accuracy_top3'))}
- Macro-F1: {_format_pct(efficientformer_eval.get('macro_f1'))}
- Mean confidence: {_format_pct(efficientformer_eval.get('mean_confidence'))}
- Avg latency: {_format_ms(efficientformer_bench.get('avg_ms'))}
- P95 latency: {_format_ms(efficientformer_bench.get('p95_ms'))}
- Max latency: {_format_ms(efficientformer_bench.get('max_ms'))}
- Throughput: {_format_fps(efficientformer_bench.get('throughput_fps'))}

Artefatti tecnici da citare:

- {summary['eval_summary']}
- {summary['benchmark_summary']}
"""

    release_draft_md = f"""## EfficientFormer - Benchmark ed evaluation validati

- Accuracy top-1 EfficientFormer: {_format_pct(efficientformer_eval.get('accuracy_top1'))}
- Accuracy top-3 EfficientFormer: {_format_pct(efficientformer_eval.get('accuracy_top3'))}
- Macro-F1 EfficientFormer: {_format_pct(efficientformer_eval.get('macro_f1'))}
- Avg latency on-device: {_format_ms(efficientformer_bench.get('avg_ms'))}
- P95 latency on-device: {_format_ms(efficientformer_bench.get('p95_ms'))}
- Throughput on-device: {_format_fps(efficientformer_bench.get('throughput_fps'))}

Report completi: {summary['eval_summary']} e {summary['benchmark_summary']}
"""

    files = {
        "summary_md": "ATTIVITA_DIVULGATIVE.md",
        "readme_snippet": "README_METRICS_SNIPPET.md",
        "model_card_draft": "MODEL_CARD_EFFICIENTFORMER_DRAFT.md",
        "release_draft": "RELEASE_EFFICIENTFORMER_DRAFT.md",
    }
    contents = {
        "summary_md": attivita_divulgative_md,
        "readme_snippet": readme_snippet_md,
        "model_card_draft": model_card_draft_md,
        "release_draft": release_draft_md,
    }

    written: dict[str, str] = {}
    for key, filename in files.items():
        path = output_dir / filename
        path.write_text(contents[key], encoding="utf-8")
        written[key] = _display_path(path)
    return written


def main() -> int:
    args = build_parser().parse_args()
    eval_summary_path = Path(args.eval_summary).resolve()
    benchmark_summary_path = Path(args.benchmark_summary).resolve()
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    eval_data = _load_json(eval_summary_path)
    benchmark_data = _load_json(benchmark_summary_path)
    if not isinstance(eval_data, list) or not isinstance(benchmark_data, list):
        raise RuntimeError("I file summary devono contenere liste JSON di modelli")

    eval_rows = _index_by_model_key(eval_data)
    bench_rows = _index_by_model_key(benchmark_data)
    if "efficientformer" not in eval_rows or "efficientformer" not in bench_rows:
        raise RuntimeError("Risultati EfficientFormer mancanti: impossibile preparare ATTIVITA' DIVULGATIVE")

    summary = _build_summary(eval_rows, bench_rows, args)
    summary_json_path = output_dir / "dissemination_summary.json"
    summary_json_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    written_files = _write_markdown_files(output_dir, summary)

    print(json.dumps({
        "status": "completed",
        "summary_json": _display_path(summary_json_path),
        **written_files,
    }, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())