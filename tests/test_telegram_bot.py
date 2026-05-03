import json
import os
import types
from pathlib import Path
import asyncio

import main
import interface.telegram_bot as tg


def test_labels_for_organ_uses_correct_sets(tmp_path, monkeypatch):
    labels_file = tmp_path / "labels.txt"
    labels_file.write_text("Sano\nOidio\n", encoding="utf-8")
    monkeypatch.setitem(tg.MODEL_CONFIG, "labels_path", str(labels_file))

    leaf_labels = tg._labels_for_organ(None, "leaf")
    assert leaf_labels == ["Sano", "Oidio"]
    assert tg._labels_for_organ(None, "flower") == list(tg.FLOWER_LABELS)
    assert tg._labels_for_organ(None, "fruit") == list(tg.FRUIT_LABELS)


def test_resolve_organ_uses_label_sets():
    assert tg._resolve_organ(tg.FLOWER_LABELS[0]) == "flower"
    assert tg._resolve_organ(tg.FRUIT_LABELS[0]) == "fruit"
    assert tg._resolve_organ("Sano") == "leaf"


def test_finetune_target_by_organ():
    assert tg._finetune_target_by_organ("leaf") == tg.FINETUNING_CONFIG
    assert tg._finetune_target_by_organ("flower") == tg.FINETUNING_FLOWER_CONFIG
    assert tg._finetune_target_by_organ("fruit") == tg.FINETUNING_FRUIT_CONFIG


def test_sanitize_label():
    assert tg._sanitize_label("A b/c") == "A_b_c"


def test_store_learning_record_writes_metadata(tmp_path, monkeypatch):
    input_image = tmp_path / "input.jpg"
    input_image.write_bytes(b"fake")
    lbd_dir = tmp_path / "learning"
    monkeypatch.setattr(tg, "LEARNING_BY_DOING_DIR", lbd_dir)

    meta_path = tg._store_learning_record(
        input_image,
        plant_name="Dipladenia",
        label="Fiore_sano",
        organ="flower",
        user_info={"id": 1, "username": "@user"},
    )

    assert meta_path.exists()
    data = json.loads(meta_path.read_text(encoding="utf-8"))
    assert data["plant_name"] == "Dipladenia"
    assert data["label"] == "Fiore_sano"
    assert data["organ"] == "flower"
    assert Path(data["stored_image"]).exists()
    assert data["training_image"] is None


def test_list_input_images_orders_by_mtime(tmp_path, monkeypatch):
    monkeypatch.setattr(tg, "INPUT_IMAGES_DIR", tmp_path)
    monkeypatch.setitem(tg.VISION_CONFIG, "input_image_extensions", [".jpg", ".png"])

    older = tmp_path / "a.jpg"
    newer = tmp_path / "b.png"
    ignored = tmp_path / "c.txt"
    older.write_bytes(b"a")
    newer.write_bytes(b"b")
    ignored.write_bytes(b"c")

    os.utime(older, (1, 1))
    os.utime(newer, (2, 2))

    images = tg._list_input_images(limit=10)
    assert [img.name for img in images] == ["b.png", "a.jpg"]
    latest = tg._get_latest_input_image()
    assert latest is not None
    assert latest.name == "b.png"


def test_run_runtime_interactive_with_telegram_polls_on_main_thread(monkeypatch):
    agent = object()
    telegram_app = object()
    args = types.SimpleNamespace(daemon=False)
    calls = []

    monkeypatch.setattr(main.sys, "stdin", types.SimpleNamespace(isatty=lambda: True))
    monkeypatch.setattr(main, "_run_cli", lambda current_agent: calls.append(("cli", current_agent)))
    monkeypatch.setattr(
        main,
        "serve_telegram_polling",
        lambda current_app: calls.append(("poll", current_app)),
    )

    class FakeThread:
        def __init__(self, target, args, name, daemon):
            self._target = target
            self._args = args
            self.name = name
            self.daemon = daemon

        def start(self):
            calls.append(("thread", self.name, self.daemon))
            self._target(*self._args)

    monkeypatch.setattr(main.threading, "Thread", FakeThread)

    main._run_runtime(agent, args, telegram_app)

    assert calls == [
        ("thread", "delta-cli", True),
        ("cli", agent),
        ("poll", telegram_app),
    ]


def test_send_long_forwards_parse_mode(monkeypatch):
    calls = []

    async def fake_send(update, text, reply_markup=None, parse_mode=None):
        calls.append((text, reply_markup, parse_mode))

    monkeypatch.setattr(tg, "_send", fake_send)

    asyncio.run(tg._send_long(object(), "uno", parse_mode="HTML"))

    assert calls == [("uno", None, "HTML")]


def test_send_diagnosis_paginated_short_closes_with_smile(monkeypatch):
    calls = []

    async def fake_send(update, text, reply_markup=None, parse_mode=None):
        calls.append((text, parse_mode))

    monkeypatch.setattr(tg, "_send", fake_send)

    context = types.SimpleNamespace(user_data={})
    asyncio.run(
        tg._send_diagnosis_paginated(
            object(),
            context,
            "Risultato breve",
            parse_mode="HTML",
        )
    )

    assert calls == [
        ("Risultato breve", "HTML"),
        ("Posso fare qualcos'altro per te? Sono a tua disposizione 🙂", None),
    ]
    assert context.user_data == {}


def test_continue_diagnosis_message_sends_next_and_final_smile(monkeypatch):
    calls = []

    async def fake_send(update, text, reply_markup=None, parse_mode=None):
        calls.append((text, parse_mode))

    async def fake_guard(update):
        return True

    monkeypatch.setattr(tg, "_send", fake_send)
    monkeypatch.setattr(tg, "_guard", fake_guard)

    context = types.SimpleNamespace(
        user_data={
            "diag_pending_chunks": ["seconda parte"],
            "diag_pending_parse_mode": "HTML",
            "diag_pending_closing": "chiusura 🙂",
        }
    )

    asyncio.run(tg.continue_diagnosis_message(object(), context))

    assert calls == [
        ("seconda parte", "HTML"),
        ("chiusura 🙂", None),
    ]
    assert "diag_pending_chunks" not in context.user_data
    assert "diag_pending_parse_mode" not in context.user_data
    assert "diag_pending_closing" not in context.user_data


def test_send_chat_paginated_short_message(monkeypatch):
    calls = []

    async def fake_send(update, text, reply_markup=None, parse_mode=None):
        calls.append((text, reply_markup, parse_mode))

    monkeypatch.setattr(tg, "_send", fake_send)

    keyboard = object()
    context = types.SimpleNamespace(user_data={})

    asyncio.run(
        tg._send_chat_paginated(
            object(),
            context,
            "risposta breve",
            reply_markup=keyboard,
        )
    )

    assert calls == [("risposta breve", keyboard, None)]
    assert context.user_data == {}


def test_continue_diagnosis_message_uses_chat_pending_when_no_diag(monkeypatch):
    calls = []

    async def fake_send(update, text, reply_markup=None, parse_mode=None):
        calls.append((text, parse_mode))

    async def fake_guard(update):
        return True

    monkeypatch.setattr(tg, "_send", fake_send)
    monkeypatch.setattr(tg, "_guard", fake_guard)

    context = types.SimpleNamespace(
        user_data={
            "chat_pending_chunks": ["chat parte 2"],
            "chat_pending_parse_mode": None,
        }
    )

    asyncio.run(tg.continue_diagnosis_message(object(), context))

    assert calls == [("chat parte 2", None)]
    assert "chat_pending_chunks" not in context.user_data
    assert "chat_pending_parse_mode" not in context.user_data
