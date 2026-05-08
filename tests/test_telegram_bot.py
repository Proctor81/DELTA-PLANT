import json
import logging
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
        ("thread", "delta-telegram", True),
        ("poll", telegram_app),
        ("cli", agent),
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


def test_build_diagnosis_memory_turn_keeps_context_conversational():
    request, response = tg._build_diagnosis_memory_turn(
        user_description="Foglie con macchie gialle e margini secchi da tre giorni.",
        opinion="Esito tecnico: probabile stress combinato con rischio fungino.",
        record={
            "ai_result": {"class": "Tomato_Early_blight", "confidence": 0.91},
            "diagnosis": {
                "plant_status": "Da monitorare",
                "summary": "Probabile alternariosi in fase iniziale.",
                "explanation": "Analisi foglia: 'Tomato_Early_blight' con confidenza 91.0%.",
                "risk": "medio",
                "overall_risk": "medio",
                "quantum_risk": {
                    "quantum_risk_score": 0.42,
                    "risk_level": "medio",
                    "dominant_description": "umidita_alta",
                },
                "sensor_snapshot": {"temperature_c": 26.4, "humidity_pct": 84.2},
            },
        },
        sensor_data={"temperature_c": 26.4, "humidity_pct": 84.2},
    )

    assert request.startswith("Ho chiesto una diagnosi della pianta.")
    assert "Pianta: pomodoro." in request
    assert "Tomato_Early_blight" in request
    assert "Probabile alternariosi in fase iniziale." in request
    assert "Elementi completi della diagnosi:" in request
    assert "Stato pianta:" in request
    assert "Diagnosi:" in request
    assert "Temperatura" in request
    assert "QRS:           🟡 0.4200 [MEDIO]" in request
    assert "Sei un agronomo esperto" not in request
    assert response == "Esito tecnico: probabile stress combinato con rischio fungino."


def test_build_diagnosis_memory_turn_extracts_non_catalog_plant_name_from_description():
    request, _ = tg._build_diagnosis_memory_turn(
        user_description="Dipladenia con foglie gialle e margini secchi.",
        opinion="Valutazione preliminare.",
        followup_mode="fallback",
    )

    assert "Pianta: Dipladenia." in request


def test_send_ai_diagnosis_opinion_uses_stateless_generation_and_remembers_clean_turn(monkeypatch):
    sends = []
    remembered = []

    async def fake_send_diagnosis_paginated(update, context, text, parse_mode=None):
        sends.append((text, parse_mode))

    async def fake_to_thread(func, *args, **kwargs):
        return func(*args, **kwargs)

    async def fake_send_action(*args, **kwargs):
        return None

    class FakeEngine:
        def chat_internal(self, prompt):
            assert "UNICO messaggio finale" in prompt
            return "Diagnosi finale operativa"

        def remember_turn(self, user_id, user_input, response):
            remembered.append((user_id, user_input, response))

    monkeypatch.setattr(tg, "_send_diagnosis_paginated", fake_send_diagnosis_paginated)
    monkeypatch.setattr(tg, "_get_chat_engine", lambda context: FakeEngine())
    monkeypatch.setattr(
        tg,
        "_reclassify_with_description",
        lambda engine, ai_class, user_description: asyncio.sleep(0, result=ai_class),
    )
    monkeypatch.setattr(tg, "_sanitize_diagnosis_opinion", lambda opinion: opinion)
    monkeypatch.setattr(tg.asyncio, "to_thread", fake_to_thread)

    update = types.SimpleNamespace(
        effective_user=types.SimpleNamespace(id=77),
        effective_chat=types.SimpleNamespace(send_action=fake_send_action),
    )
    context = types.SimpleNamespace(
        user_data={
            "diag_user_description": "Foglie con lesioni scure",
            "sensor_index": 6,
            "diag_image_path": "input_images/foglia.jpg",
        }
    )
    record = {
        "ai_result": {"class": "Tomato_Early_blight", "confidence": 0.88},
        "diagnosis": {
            "plant_status": "Compromesso",
            "summary": "Alternariosi probabile",
            "overall_risk": "alto",
            "explanation": "Analisi foglia: 'Tomato_Early_blight' con confidenza 88.0%.",
            "sensor_snapshot": {"temperature_c": 25.0},
        },
        "recommendations": [
            {"category": "fungo", "priority": 1, "problem": "lesioni fogliari", "action": "trattamento mirato"},
        ],
    }

    result = asyncio.run(tg._send_ai_diagnosis_opinion(update, context, record))

    assert result == tg.ConversationHandler.END
    assert sends == [(
        "🩺 <b>RISULTATO DIAGNOSI DELTA Plant:</b>\n\nDiagnosi finale operativa",
        "HTML",
    )]
    assert remembered[0][0] == "77"
    assert remembered[0][2] == "Diagnosi finale operativa"
    assert "Sei un agronomo esperto" not in remembered[0][1]
    assert "Ho chiesto una diagnosi della pianta." in remembered[0][1]
    assert "Pianta: pomodoro." in remembered[0][1]
    assert "Elementi completi della diagnosi:" in remembered[0][1]
    assert "Raccomandazioni:" in remembered[0][1]
    assert "sensor_index" not in context.user_data
    assert "diag_image_path" not in context.user_data
    assert context.user_data["diagnosis_active"] is False


def test_free_chat_handler_ignores_sensor_collection_markers(monkeypatch):
    async def fake_guard(update):
        return True

    async def fake_send_action(*args, **kwargs):
        return None

    update = types.SimpleNamespace(
        message=types.SimpleNamespace(text="70"),
        effective_user=types.SimpleNamespace(id=88),
        effective_chat=types.SimpleNamespace(send_action=fake_send_action),
    )
    context = types.SimpleNamespace(
        user_data={"sensor_index": 2},
        application=types.SimpleNamespace(bot_data={}),
    )
    logger = logging.getLogger("deltaplano.chat")
    old_handlers = list(logger.handlers)
    old_propagate = logger.propagate
    logger.handlers = [logging.NullHandler()]
    logger.propagate = False

    monkeypatch.setattr(tg, "_guard", fake_guard)
    monkeypatch.setattr(
        tg,
        "_get_chat_engine",
        lambda current_context: (_ for _ in ()).throw(AssertionError("engine.chat non deve essere chiamato")),
    )

    try:
        asyncio.run(tg.free_chat_handler(update, context))
    finally:
        logger.handlers = old_handlers
        logger.propagate = old_propagate


def test_free_chat_handler_ignores_dedicated_chat_session(monkeypatch):
    async def fake_guard(update):
        return True

    async def fake_send_action(*args, **kwargs):
        return None

    update = types.SimpleNamespace(
        message=types.SimpleNamespace(text="ciao"),
        effective_user=types.SimpleNamespace(id=99),
        effective_chat=types.SimpleNamespace(send_action=fake_send_action),
    )
    context = types.SimpleNamespace(
        user_data={"chat_mode_active": True},
        application=types.SimpleNamespace(bot_data={}),
    )
    logger = logging.getLogger("deltaplano.chat")
    old_handlers = list(logger.handlers)
    old_propagate = logger.propagate
    logger.handlers = [logging.NullHandler()]
    logger.propagate = False

    monkeypatch.setattr(tg, "_guard", fake_guard)
    monkeypatch.setattr(
        tg,
        "_get_chat_engine",
        lambda current_context: (_ for _ in ()).throw(AssertionError("engine.chat non deve essere chiamato")),
    )

    try:
        asyncio.run(tg.free_chat_handler(update, context))
    finally:
        logger.handlers = old_handlers
        logger.propagate = old_propagate


def test_menu_keyboard_includes_chat_button():
    keyboard = tg._menu_keyboard()
    callback_data = [button.callback_data for row in keyboard.inline_keyboard for button in row]
    assert tg.CMD_CHAT in callback_data
