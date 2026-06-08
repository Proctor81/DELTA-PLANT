import gzip
from pathlib import Path

from interface.admin import AdminPanel


def _write_lines(path: Path, lines: list[str]) -> None:
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_collect_bot_inference_log_stats_dedupes_duplicates_and_skips_synthetic(tmp_path):
    log_a = tmp_path / "delta.log"
    log_b = tmp_path / "bot.log"
    shared_lines = [
        "2026-06-08T10:00:00 [INFO] delta.interface.telegram: free_chat_handler: Ricevuto da 123: ciao",
        "2026-06-08T10:00:01 [INFO] delta.huggingface_llm: HF risposta generata con real-model (120 chars)",
        "2026-06-08T10:00:01 [INFO] delta.chat_engine: Risposta HF [real-model] per user 123",
    ]
    _write_lines(
        log_a,
        shared_lines
        + [
            "2026-06-08T10:00:02 [INFO] delta.chat_engine: Risposta HF [fake-model] per user 77",
        ],
    )
    _write_lines(log_b, shared_lines)

    panel = AdminPanel(agent=None)
    result = panel._collect_bot_inference_log_stats([log_a, log_b])

    assert result["stats"]["123"]["requests"] == 1
    assert result["stats"]["123"]["models"] == {"real-model"}
    assert result["total_hf_calls"] == 1
    assert result["duplicate_lines_skipped"] == len(shared_lines)
    assert result["synthetic_lines_skipped"] == 1
    assert "77" not in result["stats"]


def test_collect_bot_inference_log_stats_attributes_error_to_latest_request(tmp_path):
    log_file = tmp_path / "delta.log"
    _write_lines(
        log_file,
        [
            "2026-06-08T10:00:00 [INFO] delta.interface.telegram: free_chat_handler: Ricevuto da 123: ciao",
            "2026-06-08T10:00:01 [WARNING] delta.huggingface_llm: Errore HF con modello real-model: timeout",
            "2026-06-08T10:00:01 [WARNING] delta.chat_engine: HF ha restituito errore/no-response: [DELTA] timeout",
        ],
    )

    panel = AdminPanel(agent=None)
    result = panel._collect_bot_inference_log_stats([log_file])

    assert result["total_hf_errors"] == 1
    assert result["stats"]["123"]["errors"] == 1


def test_discover_bot_inference_log_variants_includes_rotated_history(tmp_path):
    current_log = tmp_path / "delta.log"
    rotated_log = tmp_path / "delta.log.1"
    compressed_log = tmp_path / "delta.log.2.gz"
    ignored_file = tmp_path / "delta.log.backup"
    _write_lines(current_log, ["current"])
    _write_lines(rotated_log, ["rotated"])
    with gzip.open(compressed_log, "wt", encoding="utf-8") as fh:
        fh.write("compressed\n")
    _write_lines(ignored_file, ["ignore"])

    panel = AdminPanel(agent=None)
    result = panel._discover_bot_inference_log_variants(tmp_path, "delta.log")

    assert result == [compressed_log, rotated_log, current_log]


def test_collect_bot_inference_log_stats_reads_gzip_rotated_history(tmp_path):
    rotated_log = tmp_path / "delta.log.1.gz"
    current_log = tmp_path / "delta.log"
    with gzip.open(rotated_log, "wt", encoding="utf-8") as fh:
        fh.write(
            "2026-06-08T09:00:00 [INFO] delta.interface.telegram: free_chat_handler: Ricevuto da 123: storico\n"
            "2026-06-08T09:00:01 [INFO] delta.huggingface_llm: HF risposta generata con real-model (100 chars)\n"
            "2026-06-08T09:00:01 [INFO] delta.chat_engine: Risposta HF [real-model] per user 123\n"
        )
    _write_lines(
        current_log,
        [
            "2026-06-08T10:00:00 [INFO] delta.interface.telegram: free_chat_handler: Ricevuto da 456: corrente",
            "2026-06-08T10:00:01 [INFO] delta.huggingface_llm: HF risposta generata con real-model (140 chars)",
            "2026-06-08T10:00:01 [INFO] delta.chat_engine: Risposta HF [real-model] per user 456",
        ],
    )

    panel = AdminPanel(agent=None)
    result = panel._collect_bot_inference_log_stats(
        panel._discover_bot_inference_log_variants(tmp_path, "delta.log")
    )

    assert result["stats"]["123"]["requests"] == 1
    assert result["stats"]["456"]["requests"] == 1
    assert result["total_hf_calls"] == 2
    assert result["total_hf_chars"] == 240