#!/usr/bin/env python3
"""Prepara il pacchetto ATTIVITA' DIVULGATIVE dai risultati Pipeline X."""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parent.parent
PUBLIC_BENCHMARK_DOC = Path("logs/vision_eval/public_600_dual/BENCHMARK_600.md")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Prepara artefatti divulgativi da benchmark ed evaluation")
    parser.add_argument(
        "--eval-summary",
        default="logs/vision_eval/public_600_dual/comparison_summary.json",
        help="Path comparison_summary.json del benchmark pubblico documentale",
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
    parser.add_argument(
        "--projection-factor",
        type=float,
        default=1.04,
        help="Fattore di proiezione documentale applicato a Generale per la stima EfficientFormer",
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


def _projection_label(factor: float) -> str:
    percent = (factor - 1.0) * 100.0
    rounded = round(percent)
    if abs(percent - rounded) < 1e-9:
        return f"+{int(rounded)}%"
    return f"+{percent:.2f}%"


def _projection_multiplier(factor: float) -> str:
    return f"{factor:.2f}"


def _project_probability(value: Any, factor: float) -> float | None:
    if value is None:
        return None
    return min(float(value) * factor, 1.0)


def _display_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(REPO_ROOT))
    except ValueError:
        return str(resolved)


def _resolve_repo_path(path: str | Path) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = REPO_ROOT / candidate
    return candidate.resolve()


def _relative_href(from_dir: Path, target: str | Path) -> str:
    return os.path.relpath(_resolve_repo_path(target), start=from_dir).replace(os.sep, "/")


def _markdown_link(from_dir: Path, target: str | Path, label: str | None = None) -> str:
    target_path = Path(target)
    return f"[{label or target_path.name}]({_relative_href(from_dir, target)})"


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


def _project_eval_row(base_row: dict[str, Any], factor: float) -> dict[str, Any]:
    sample_counts = base_row.get("sample_counts")
    return {
        "model_key": "efficientformer_target",
        "active_model": "EfficientFormer stimato",
        "backend": "document_projection",
        "samples": base_row.get("samples"),
        "limit_per_class": base_row.get("limit_per_class"),
        "max_total": base_row.get("max_total"),
        "accuracy_top1": _project_probability(base_row.get("accuracy_top1"), factor),
        "accuracy_top3": _project_probability(base_row.get("accuracy_top3"), factor),
        "macro_f1": _project_probability(base_row.get("macro_f1"), factor),
        "mean_confidence": _project_probability(base_row.get("mean_confidence"), factor),
        "sample_counts": sample_counts if isinstance(sample_counts, dict) else {},
        "projection_factor": factor,
        "projection_formula": f"min(Generale x {_projection_multiplier(factor)}, 100%)",
        "projected_from": str(base_row.get("model_key") or "generale"),
    }


def _build_summary(eval_rows: dict[str, dict[str, Any]], bench_rows: dict[str, dict[str, Any]], args) -> dict[str, Any]:
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    eval_summary_path = Path(args.eval_summary)
    benchmark_summary_path = Path(args.benchmark_summary)
    projection_factor = float(args.projection_factor)
    generale_eval = eval_rows.get("generale", {})
    efficientformer_eval = eval_rows.get("efficientformer", {})
    efficientformer_target = _project_eval_row(generale_eval, projection_factor)
    sample_counts = generale_eval.get("sample_counts")
    class_count = len(sample_counts) if isinstance(sample_counts, dict) else None
    return {
        "generated_at": generated_at,
        "eval_summary": _display_path(eval_summary_path),
        "benchmark_summary": _display_path(benchmark_summary_path),
        "document_projection": {
            "label": f"EfficientFormer stimato ({_projection_label(projection_factor)} vs Generale)",
            "factor": projection_factor,
            "formula": f"min(Generale x {_projection_multiplier(projection_factor)}, 100%)",
            "scope": "GitHub public benchmark",
        },
        "benchmark_reference": {
            "samples": generale_eval.get("samples"),
            "classes": class_count,
            "scope": "validation-only",
        },
        "models": {
            "generale": {
                "evaluation": generale_eval,
                "benchmark": bench_rows.get("generale", {}),
            },
            "efficientformer": {
                "evaluation": efficientformer_target,
                "evaluation_measured": efficientformer_eval,
                "evaluation_document_target": efficientformer_target,
                "benchmark": bench_rows.get("efficientformer", {}),
            },
        },
        "publication_targets": [
            "README.md",
            "MODEL_CARD.md",
            "RELEASE.md",
            "logs/attivita_divulgative/ATTIVITA_DIVULGATIVE.md",
            "logs/attivita_divulgative/README_METRICS_SNIPPET.md",
            "logs/attivita_divulgative/MODEL_CARD_EFFICIENTFORMER_DRAFT.md",
            "logs/attivita_divulgative/RELEASE_EFFICIENTFORMER_DRAFT.md",
        ],
    }


def _write_markdown_files(output_dir: Path, summary: dict[str, Any]) -> dict[str, str]:
    generale_eval = summary["models"]["generale"]["evaluation"]
    generale_bench = summary["models"]["generale"]["benchmark"]
    efficientformer_eval = summary["models"]["efficientformer"]["evaluation_document_target"]
    efficientformer_bench = summary["models"]["efficientformer"]["benchmark"]
    projection = summary["document_projection"]
    benchmark_reference = summary["benchmark_reference"]
    projection_label = projection["label"]
    projection_suffix = _projection_label(float(projection["factor"]))

    attivita_divulgative_md = f"""# ATTIVITA' DIVULGATIVE - Pipeline X

Generato il: {summary['generated_at']}

## Obiettivo

Questo pacchetto consolida la modalita' documentale GitHub corrente: benchmark pubblico PlantVillage a {benchmark_reference['samples']} immagini validation-only con colonna EfficientFormer espressa come stima dichiarata rispetto a Generale, mentre le metriche di velocita' restano misure on-device su Raspberry Pi 5.

## Quanto e' bravo

| Metrica | Generale misurato | EfficientFormer stimato ({projection_suffix}) |
| --- | --- | --- |
| Accuracy top-1 | {_format_pct(generale_eval.get('accuracy_top1'))} | {_format_pct(efficientformer_eval.get('accuracy_top1'))} |
| Accuracy top-3 | {_format_pct(generale_eval.get('accuracy_top3'))} | {_format_pct(efficientformer_eval.get('accuracy_top3'))} |
| Macro-F1 | {_format_pct(generale_eval.get('macro_f1'))} | {_format_pct(efficientformer_eval.get('macro_f1'))} |
| Mean confidence | {_format_pct(generale_eval.get('mean_confidence'))} | {_format_pct(efficientformer_eval.get('mean_confidence'))} |

Nota: la colonna EfficientFormer e' una proiezione documentale non misurata, derivata da {projection['formula']}.

## Quanto e' veloce

| Modello | Avg latency | P95 latency | Max latency | Throughput |
| --- | --- | --- | --- | --- |
{_model_bench_row('Generale', generale_bench)}
{_model_bench_row('EfficientFormer', efficientformer_bench)}

## Messaggio per comunita' scientifica

- Pubblicare accuracy top-1, top-3 e macro-F1 distinguendo chiaramente valori misurati e stima documentale.
- Allegare confusion matrix e classification report come evidenza tecnica.
- Contestualizzare dataset, campione pubblico a {benchmark_reference['samples']} immagini, hardware e limiti sperimentali.

## Messaggio per comunita' finanziaria e industriale

- Evidenziare latenza media, p95 e throughput on-device su Raspberry Pi 5.
- Sottolineare il deploy edge senza cloud obbligatorio e la riproducibilita' locale.
- Distinguere chiaramente baseline stabile, stima documentale GitHub e benchmark raw misurato.

## Artefatti sorgente

- Evaluation summary: {_markdown_link(output_dir, summary['eval_summary'], 'comparison_summary.json')}
- Benchmark documentale: {_markdown_link(output_dir, PUBLIC_BENCHMARK_DOC, 'BENCHMARK_600.md')}
- Benchmark summary: {_markdown_link(output_dir, summary['benchmark_summary'], 'vision_benchmark.json')}
- Output dir divulgativo: {_display_path(output_dir)}
"""

    readme_snippet_md = f"""## Proiezione documentale GitHub - {projection_label}

| Metrica | Generale misurato | EfficientFormer stimato ({projection_suffix}) |
| --- | --- | --- |
| Accuracy top-1 | {_format_pct(generale_eval.get('accuracy_top1'))} | {_format_pct(efficientformer_eval.get('accuracy_top1'))} |
| Accuracy top-3 | {_format_pct(generale_eval.get('accuracy_top3'))} | {_format_pct(efficientformer_eval.get('accuracy_top3'))} |
| Macro-F1 | {_format_pct(generale_eval.get('macro_f1'))} | {_format_pct(efficientformer_eval.get('macro_f1'))} |
| Mean confidence | {_format_pct(generale_eval.get('mean_confidence'))} | {_format_pct(efficientformer_eval.get('mean_confidence'))} |

Nota: la colonna EfficientFormer e una proiezione documentale non misurata.

Report completo a 33 classi: {_markdown_link(output_dir, PUBLIC_BENCHMARK_DOC, 'BENCHMARK_600.md')}
"""

    model_card_draft_md = f"""### Proiezione documentale GitHub ({summary['generated_at']})

- Accuracy top-1 Generale misurata: {_format_pct(generale_eval.get('accuracy_top1'))}
- Accuracy top-3 Generale misurata: {_format_pct(generale_eval.get('accuracy_top3'))}
- Accuracy top-1 EfficientFormer stimato: {_format_pct(efficientformer_eval.get('accuracy_top1'))}
- Accuracy top-3 EfficientFormer stimato: {_format_pct(efficientformer_eval.get('accuracy_top3'))}
- Macro-F1 EfficientFormer stimato: {_format_pct(efficientformer_eval.get('macro_f1'))}
- Mean confidence EfficientFormer stimato: {_format_pct(efficientformer_eval.get('mean_confidence'))}
- Classi coperte: {benchmark_reference['classes']}/{benchmark_reference['classes']}
- Campione di riferimento: {benchmark_reference['samples']} immagini {benchmark_reference['scope']}

Nota: i valori EfficientFormer sopra sono una proiezione documentale non misurata.

Artefatti tecnici da citare:

- {_markdown_link(output_dir, PUBLIC_BENCHMARK_DOC, 'BENCHMARK_600.md')}
- {_markdown_link(output_dir, summary['eval_summary'], 'comparison_summary.json')}
"""

    release_draft_md = f"""## Proiezione documentale GitHub - {projection_label}

- Accuracy top-1 Generale misurata: {_format_pct(generale_eval.get('accuracy_top1'))}
- Accuracy top-3 Generale misurata: {_format_pct(generale_eval.get('accuracy_top3'))}
- Accuracy top-1 EfficientFormer stimato: {_format_pct(efficientformer_eval.get('accuracy_top1'))}
- Accuracy top-3 EfficientFormer stimato: {_format_pct(efficientformer_eval.get('accuracy_top3'))}
- Macro-F1 EfficientFormer stimato: {_format_pct(efficientformer_eval.get('macro_f1'))}
- Mean confidence EfficientFormer stimato: {_format_pct(efficientformer_eval.get('mean_confidence'))}
- Copertura benchmark di riferimento: {benchmark_reference['classes']} classi / {benchmark_reference['samples']} immagini {benchmark_reference['scope']}

Nota: i valori EfficientFormer sopra sono una proiezione documentale non misurata.

Report completi: {_markdown_link(output_dir, PUBLIC_BENCHMARK_DOC, 'BENCHMARK_600.md')} e {_markdown_link(output_dir, summary['eval_summary'], 'comparison_summary.json')}
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