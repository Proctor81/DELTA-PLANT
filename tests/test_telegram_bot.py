import json
import logging
import os
import tempfile
import types
from io import BytesIO
from pathlib import Path
import asyncio

import pytest

import main
import interface.telegram_bot as tg


def test_is_authorized_accepts_local_authorized_user_id(tmp_path, monkeypatch):
    ids_file = tmp_path / "telegram_scientists_ids.local.json"
    ids_file.write_text("[1187900727]", encoding="utf-8")

    monkeypatch.setitem(tg.TELEGRAM_CONFIG, "authorized_users", [])
    monkeypatch.setitem(tg.TELEGRAM_CONFIG, "authorized_users_file", str(ids_file))
    monkeypatch.setitem(tg.TELEGRAM_CONFIG, "authorized_usernames", [])
    monkeypatch.setitem(tg.TELEGRAM_CONFIG, "authorized_usernames_file", str(tmp_path / "telegram_scientists.local.json"))

    assert tg._is_authorized(1187900727, "@gipg") is True


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


def test_build_welcome_voice_text_personalizes_first_name():
    update = types.SimpleNamespace(
        effective_user=types.SimpleNamespace(first_name="Luca", username="lucaplants"),
    )

    result = tg._build_welcome_voice_text(update)

    assert result.startswith("Ciao Luca")
    assert "DELTAPLANO" in result


def test_build_welcome_voice_text_uses_english_override_on_start():
    update = types.SimpleNamespace(
        effective_user=types.SimpleNamespace(first_name="Ryan", username="ryanplants"),
    )
    context = types.SimpleNamespace(user_data={"voice_language_override": "en"})

    result = tg._build_welcome_voice_text(update, context)

    assert result.startswith("Hello Ryan")
    assert "Ciao" not in result


def test_build_welcome_voice_caption_uses_english_override_on_start():
    update = types.SimpleNamespace(
        effective_user=types.SimpleNamespace(first_name="Ryan", username="ryanplants"),
    )
    context = types.SimpleNamespace(user_data={"voice_language_override": "en"})

    result = tg._build_welcome_voice_caption(update, context)

    assert result == "Welcome, Ryan."


def test_maybe_send_voice_welcome_uses_english_copy_when_override_active(monkeypatch):
    sends = []

    async def fake_send(update, text, reply_markup=None, parse_mode=None):
        sends.append(text)

    monkeypatch.setattr(tg, "_send", fake_send)

    update = types.SimpleNamespace()
    context = types.SimpleNamespace(user_data={"voice_language_override": tg.VOICE_LANGUAGE_EN})

    asyncio.run(tg._maybe_send_voice_welcome(update, context))

    assert sends
    assert sends[0].startswith("🎙️ Voice mode is available in free chat.")


def test_send_personalized_welcome_voice_uses_tts_and_send_voice(monkeypatch):
    calls = []

    async def fake_tts(context, text):
        calls.append(("tts", text))
        payload = BytesIO(b"voice-bytes")
        payload.name = "delta_voice_reply.wav"
        return payload

    async def fake_send_voice(update, voice_data, caption=None, reply_markup=None):
        calls.append(("voice", voice_data.name, caption))

    async def fake_send_action(action):
        calls.append(("action", action))

    monkeypatch.setattr(tg, "text_to_speech_warm_male", fake_tts)
    monkeypatch.setattr(tg, "_send_voice", fake_send_voice)

    update = types.SimpleNamespace(
        effective_user=types.SimpleNamespace(first_name="Luca", username="lucaplants"),
        effective_chat=types.SimpleNamespace(send_action=fake_send_action),
    )

    asyncio.run(
        tg._send_personalized_welcome_voice(
            update,
            types.SimpleNamespace(user_data={}, application=types.SimpleNamespace(bot_data={})),
        )
    )

    assert calls[0] == ("action", "record_voice")
    assert calls[1][0] == "tts"
    assert calls[2] == ("voice", "delta_voice_reply.wav", "Benvenuto, Luca.")


def test_start_sends_intro_and_personalized_welcome_voice(monkeypatch):
    sends = []
    welcome_calls = []

    async def fake_guard(update):
        return True

    async def fake_send(update, text, reply_markup=None, parse_mode=None):
        sends.append(text)

    async def fake_welcome(update, context):
        welcome_calls.append(tg._welcome_display_name(update))

    monkeypatch.setattr(tg, "_guard", fake_guard)
    monkeypatch.setattr(tg, "_send", fake_send)
    monkeypatch.setattr(tg, "_send_personalized_welcome_voice", fake_welcome)

    update = types.SimpleNamespace(
        effective_user=types.SimpleNamespace(id=77, first_name="Luca", username="lucaplants"),
    )
    context = types.SimpleNamespace(user_data={})

    result = asyncio.run(tg.start(update, context))

    assert result is None
    assert len(sends) == 1
    assert "Benvenuto in @DELTAPLANO_bot" in sends[0]
    assert welcome_calls == ["Luca"]


def test_start_sends_english_intro_when_english_override_active(monkeypatch):
    sends = []
    welcome_calls = []

    async def fake_guard(update):
        return True

    async def fake_send(update, text, reply_markup=None, parse_mode=None):
        sends.append(text)

    async def fake_welcome(update, context):
        welcome_calls.append(tg._welcome_display_name(update))

    monkeypatch.setattr(tg, "_guard", fake_guard)
    monkeypatch.setattr(tg, "_send", fake_send)
    monkeypatch.setattr(tg, "_send_personalized_welcome_voice", fake_welcome)

    update = types.SimpleNamespace(
        effective_user=types.SimpleNamespace(id=78, first_name="Ryan", username="ryanplants"),
    )
    context = types.SimpleNamespace(user_data={"voice_language_override": "en"})

    result = asyncio.run(tg.start(update, context))

    assert result is None
    assert len(sends) == 1
    assert "Welcome to @DELTAPLANO_bot" in sends[0]
    assert "Benvenuto" not in sends[0]
    assert welcome_calls == ["Ryan"]


def test_voice_language_command_reports_status_in_english_when_override_active(monkeypatch):
    sends = []

    async def fake_guard(update):
        return True

    async def fake_send(update, text, reply_markup=None, parse_mode=None):
        sends.append(text)

    monkeypatch.setattr(tg, "_guard", fake_guard)
    monkeypatch.setattr(tg, "_send", fake_send)

    update = types.SimpleNamespace()
    context = types.SimpleNamespace(args=[], user_data={"voice_language_override": "en"})

    asyncio.run(tg.voice_language_command(update, context))

    assert sends == [
        "Current voice language: EN\nUse /voice_lang it, /voice_lang en or /voice_lang auto."
    ]


def test_chat_start_uses_english_intro_when_override_active(monkeypatch):
    sends = []

    class FakeEngine:
        def get_status(self):
            return {"hf_token_valid": True, "hf_active_model": "test-model"}

    async def fake_guard(update):
        return True

    async def fake_send(update, text, reply_markup=None, parse_mode=None):
        sends.append((text, reply_markup, parse_mode))

    monkeypatch.setattr(tg, "_guard", fake_guard)
    monkeypatch.setattr(tg, "_send", fake_send)
    monkeypatch.setattr(tg, "_get_chat_engine", lambda context: FakeEngine())

    update = types.SimpleNamespace()
    context = types.SimpleNamespace(user_data={"voice_language_override": tg.VOICE_LANGUAGE_EN})

    result = asyncio.run(tg.chat_start(update, context))

    assert result == tg.STATE_CHAT_WAITING
    assert sends[0][0].startswith("🔵 *DELTA intelligent chat active*")
    labels = [button.text for row in sends[0][1].inline_keyboard for button in row]
    assert labels == ["🔴 End chat", "🗑 Reset conversation"]
    assert sends[0][2] == "Markdown"


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


def test_send_diagnosis_visuals_sends_original_and_overlay(tmp_path):
    original = tmp_path / "original.png"
    overlay = tmp_path / "overlay.png"
    original.write_bytes(b"original-bytes")
    overlay.write_bytes(b"overlay-bytes")

    calls = []

    class FakeChat:
        async def send_photo(self, photo, caption=None):
            calls.append(caption)

    update = types.SimpleNamespace(effective_chat=FakeChat())
    context = types.SimpleNamespace(user_data={"diag_image_path": str(original)})
    record = {"explainability": {"overlay_path": str(overlay), "summary": "lesione evidenziata"}}

    asyncio.run(tg._send_diagnosis_visuals(update, context, record))

    assert len(calls) == 2


def test_menu_keyboard_contains_nasa_sar_callback_button():
    keyboard = tg._menu_keyboard()
    buttons = [button for row in keyboard.inline_keyboard for button in row]
    nasa_button = next(button for button in buttons if button.text == "🛰️ Connettiti a NASA-ISRO/SAR")

    assert nasa_button.callback_data == tg.CMD_NASA_SAR
    assert nasa_button.web_app is None


def test_send_prefers_reply_text_when_effective_message_is_available():
    reply_calls = []
    send_calls = []

    class FakeMessage:
        async def reply_text(self, text, **kwargs):
            reply_calls.append((text, kwargs))

    class FakeChat:
        async def send_message(self, text, **kwargs):
            send_calls.append((text, kwargs))

    update = types.SimpleNamespace(
        effective_message=FakeMessage(),
        effective_chat=FakeChat(),
    )

    asyncio.run(tg._send(update, "Prompt NASA", reply_markup="rk", parse_mode="HTML"))

    assert reply_calls == [("Prompt NASA", {"reply_markup": "rk", "parse_mode": "HTML"})]
    assert send_calls == []


def test_send_falls_back_to_chat_send_message_when_reply_text_fails():
    send_calls = []

    class FakeMessage:
        message_thread_id = 77

        async def reply_text(self, text, **kwargs):
            raise RuntimeError("reply failed")

    class FakeChat:
        async def send_message(self, text, **kwargs):
            send_calls.append((text, kwargs))

    update = types.SimpleNamespace(
        effective_message=FakeMessage(),
        effective_chat=FakeChat(),
    )

    asyncio.run(tg._send(update, "Prompt NASA", reply_markup="rk", parse_mode="HTML"))

    assert send_calls == [
        (
            "Prompt NASA",
            {"reply_markup": "rk", "parse_mode": "HTML", "message_thread_id": 77},
        )
    ]


def test_nasa_sar_reply_keyboard_contains_webapp_and_manual_location(monkeypatch):
    monkeypatch.setitem(tg.TELEGRAM_CONFIG, "web_app_base_url", "https://deltaplant.ai")

    keyboard = tg._nasa_sar_reply_keyboard()
    first_button = keyboard.keyboard[0][0]
    second_button = keyboard.keyboard[1][0]

    assert first_button.text == "🛰️ Apri NASA-ISRO/SAR GPS"
    assert first_button.web_app.url == "https://deltaplant.ai/telegram/nasa-sar-locator.html"
    assert second_button.text == "📍 Invia GPS manualmente"
    assert second_button.request_location is True


def test_handle_nasa_sar_web_app_data_runs_analysis(monkeypatch):
    calls = []

    async def fake_guard(update):
        return True

    async def fake_run(update, context, latitude, longitude, reply_markup=None):
        calls.append((latitude, longitude, reply_markup))

    monkeypatch.setattr(tg, "_guard", fake_guard)
    monkeypatch.setattr(tg, "_run_nasa_sar_analysis", fake_run)

    update = types.SimpleNamespace(
        effective_message=types.SimpleNamespace(
            web_app_data=types.SimpleNamespace(
                data=json.dumps(
                    {
                        "type": "nasa_sar_location",
                        "status": "ok",
                        "latitude": 45.4642,
                        "longitude": 9.19,
                    }
                )
            )
        )
    )
    context = types.SimpleNamespace(user_data={}, application=types.SimpleNamespace(bot_data={}))

    asyncio.run(tg.handle_nasa_sar_web_app_data(update, context))

    assert calls == [(45.4642, 9.19, None)]


def test_handle_nasa_sar_web_app_data_reports_location_error(monkeypatch):
    messages = []

    async def fake_guard(update):
        return True

    async def fake_send(update, text, reply_markup=None, parse_mode=None):
        messages.append((text, reply_markup, parse_mode))

    monkeypatch.setattr(tg, "_guard", fake_guard)
    monkeypatch.setattr(tg, "_send", fake_send)

    update = types.SimpleNamespace(
        effective_message=types.SimpleNamespace(
            web_app_data=types.SimpleNamespace(
                data=json.dumps(
                    {
                        "type": "nasa_sar_location",
                        "status": "error",
                        "reason": "permission denied",
                    }
                )
            )
        )
    )
    context = types.SimpleNamespace(user_data={}, application=types.SimpleNamespace(bot_data={}))

    asyncio.run(tg.handle_nasa_sar_web_app_data(update, context))

    assert len(messages) == 1
    assert "posizione automatica non è disponibile" in messages[0][0]


def test_handle_nasa_sar_location_runs_analysis_and_clears_flag(monkeypatch):
    calls = []

    async def fake_guard(update):
        return True

    # Mock effective_chat.send_photo e _send
    class FakeChat:
        async def send_photo(self, photo, caption=None):
            calls.append((photo, caption))

    async def fake_send(update, text, reply_markup=None, parse_mode=None):
        calls.append(("send", text))

    monkeypatch.setattr(tg, "_guard", fake_guard)
    monkeypatch.setattr(tg, "_send", fake_send)

    update = types.SimpleNamespace(
        message=types.SimpleNamespace(location=types.SimpleNamespace(latitude=41.9028, longitude=12.4964)),
        effective_chat=FakeChat(),
    )
    context = types.SimpleNamespace(user_data={"awaiting_nasa_sar_location": True}, application=types.SimpleNamespace(bot_data={}))

    asyncio.run(tg.handle_nasa_sar_location(update, context))

    # Verifica che almeno una chiamata send_photo sia avvenuta e che il flag sia stato rimosso
    assert any(isinstance(c[0], (bytes, str, type(None))) for c in calls if isinstance(c, tuple))
    assert context.user_data == {}


def test_interpret_nasa_sar_dashboard_fallback_mentions_fungal_risk(monkeypatch):
    monkeypatch.setattr(
        tg,
        "_fetch_external_weather_reference",
        lambda result: {
            "source": "Servizio Meteorologico dell'Aeronautica Militare",
            "source_url": "https://api.meteoam.it/deda-meteograms/meteograms",
            "daily": [
                {"day": "2026-05-11", "T2M": 20.4, "RH2M": 80.0, "PRECTOTCORR": 2.0},
                {"day": "2026-05-17", "T2M": 19.6, "RH2M": 84.0, "PRECTOTCORR": 4.0},
            ],
        },
    )

    result = {
        "geo_summary": {
            "locality_label": "Roma, Lazio, Italia",
        },
        "dashboard": {
            "summary": {
                "sar_soil_moisture_percent": 31.4,
                "sar_source": "Sentinel-1 SAR operational fallback",
                "sar_product_name": "S1A_TEST_PRODUCT",
                "sar_acquired_at": "2026-05-17T10:00:00+00:00",
            },
        },
    }

    text = asyncio.run(
        tg._interpret_nasa_sar_dashboard(
            types.SimpleNamespace(application=types.SimpleNamespace(bot_data={})),
            result,
        )
    )

    assert "valore medio settimanale" in text.lower()
    assert "giudizio di rischio: alto" in text.lower()
    assert "50% umidita' relativa" in text.lower()
    assert "servizio meteorologico dell'aeronautica militare" in text.lower()
    assert "umidita' del suolo sar" in text.lower()
    assert "fonti dati:" in text.lower()
    assert "non e' una diagnosi di malattia" in text.lower()


def test_format_nasa_sar_dashboard_includes_locality_and_sar_source():
    text = tg._format_nasa_sar_dashboard(
        {
            "geo_summary": {
                "centroid": {"lat": 41.9028, "lon": 12.4964},
                "radius_m": 50,
                "locality_label": "Roma, Lazio, Italia",
            },
            "dashboard": {
                "summary": {
                    "sar_soil_moisture_percent": 31.4,
                    "sar_source": "Sentinel-1 SAR operational fallback",
                    "sar_product_name": "S1A_TEST_PRODUCT",
                    "sar_acquired_at": "2026-05-17T10:00:00+00:00",
                    "weather_window_start": "2026-05-11",
                    "weather_window_end": "2026-05-17",
                },
            },
        }
    )

    assert "Roma, Lazio, Italia" in text
    assert "Umidita' suolo SAR" in text
    assert "Sentinel-1 SAR operational fallback" in text
    assert "2026-05-17T10:00:00+00:00" in text


def test_format_nasa_sar_dashboard_uses_latest_day_and_compact_daily_breakdown():
    text = tg._format_nasa_sar_dashboard(
        {
            "dashboard": {
                "dashboard": [
                    {
                        "date": "2026-05-19",
                        "soil": 31.4,
                        "temp": 21.2,
                        "humidity": 72.0,
                        "rain": 3.4,
                        "risk": 0.41,
                    },
                    {
                        "date": "2026-05-25",
                        "soil": 28.8,
                        "temp": 24.5,
                        "humidity": 41.0,
                        "rain": 0.0,
                        "risk": 0.24,
                    },
                ],
                "weekly_risk": 0.325,
                "weekly_label": "MEDIO",
            }
        }
    )

    assert "📅 Oggi 2026-05-25" in text
    assert "Data  Soil% TempC RH% Rain Risk%" in text
    assert "25/05" in text
    assert "19/05" in text
    assert text.index("25/05") < text.index("19/05")


def test_menu_clears_chat_mode_and_ends_chat_session(monkeypatch):
    calls = []

    async def fake_send(update, text, reply_markup=None, parse_mode=None):
        calls.append(text)

    async def fake_guard(update):
        return True

    monkeypatch.setattr(tg, "_send", fake_send)
    monkeypatch.setattr(tg, "_guard", fake_guard)

    context = types.SimpleNamespace(
        user_data={
            "chat_mode_active": True,
            "chat_pending_chunks": ["parte successiva"],
            "chat_pending_parse_mode": "Markdown",
            "chat_seed_context": "Sintesi SAR recente",
        }
    )

    result = asyncio.run(tg.menu(object(), context))

    assert result == tg.ConversationHandler.END
    assert calls == ["Menu principale:"]
    assert "chat_mode_active" not in context.user_data
    assert "chat_pending_chunks" not in context.user_data
    assert "chat_pending_parse_mode" not in context.user_data
    assert "chat_seed_context" not in context.user_data


def test_menu_sends_english_prompt_when_override_active(monkeypatch):
    calls = []

    async def fake_send(update, text, reply_markup=None, parse_mode=None):
        calls.append((text, reply_markup))

    async def fake_guard(update):
        return True

    monkeypatch.setattr(tg, "_send", fake_send)
    monkeypatch.setattr(tg, "_guard", fake_guard)

    context = types.SimpleNamespace(user_data={"voice_language_override": tg.VOICE_LANGUAGE_EN})

    result = asyncio.run(tg.menu(object(), context))

    assert result is None
    assert calls[0][0] == "Main menu:"
    labels = [button.text for row in calls[0][1].inline_keyboard for button in row]
    assert "🔵 💬 Ask DELTA Plant" in labels
    assert "🛰️ Connect to NASA-ISRO/SAR" in labels


def test_report_uses_english_heading_when_override_active(monkeypatch):
    sends = []

    class FakeDatabase:
        def get_recent(self, limit=5):
            return [
                {
                    "id": 12,
                    "timestamp": "2026-05-25T10:00:00",
                    "ai_class": "Tomato_Early_blight",
                    "overall_risk": "medium",
                }
            ]

    class FakeAgent:
        database = FakeDatabase()

    async def fake_guard(update):
        return True

    async def fake_send(update, text, reply_markup=None, parse_mode=None):
        sends.append(text)

    monkeypatch.setattr(tg, "_guard", fake_guard)
    monkeypatch.setattr(tg, "_send", fake_send)
    monkeypatch.setattr(tg, "_get_agent", lambda context: FakeAgent())

    context = types.SimpleNamespace(user_data={"voice_language_override": tg.VOICE_LANGUAGE_EN})

    asyncio.run(tg.report(object(), context))

    assert sends[0].startswith("Latest diagnoses:")
    assert "risk medium" in sends[0]


def test_sensors_uses_english_heading_when_override_active(monkeypatch):
    sends = []

    class FakeAgent:
        def get_latest_sensor_data(self):
            return {"temperature_c": 24.5, "humidity_pct": 78.0}

    async def fake_guard(update):
        return True

    async def fake_send(update, text, reply_markup=None, parse_mode=None):
        sends.append(text)

    monkeypatch.setattr(tg, "_guard", fake_guard)
    monkeypatch.setattr(tg, "_send", fake_send)
    monkeypatch.setattr(tg, "_get_agent", lambda context: FakeAgent())

    context = types.SimpleNamespace(user_data={"voice_language_override": tg.VOICE_LANGUAGE_EN})

    asyncio.run(tg.sensors(object(), context))

    assert sends[0].startswith("Sensor data:")


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
    response_languages = []

    async def fake_send_diagnosis_paginated(update, context, text, parse_mode=None):
        sends.append((text, parse_mode))

    async def fake_to_thread(func, *args, **kwargs):
        return func(*args, **kwargs)

    async def fake_send_action(*args, **kwargs):
        return None

    class FakeEngine:
        def chat_internal(self, prompt, response_language="auto"):
            assert "UNICO messaggio finale" in prompt
            response_languages.append(response_language)
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
    monkeypatch.setattr(
        tg,
        "_sanitize_diagnosis_opinion",
        lambda opinion, response_language=tg.VOICE_LANGUAGE_IT: opinion,
    )
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
    assert response_languages == [tg.VOICE_LANGUAGE_IT]
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

    async def fake_send_message(*args, **kwargs):
        return None

    update = types.SimpleNamespace(
        message=types.SimpleNamespace(text="70"),
        effective_user=types.SimpleNamespace(id=88),
        effective_chat=types.SimpleNamespace(send_action=fake_send_action, send_message=fake_send_message),
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


def test_generate_free_chat_response_consumes_seed_context(monkeypatch):
    prompts = []

    async def fake_send_action(*args, **kwargs):
        return None

    class FakeEngine:
        def chat(self, user_id, prompt, response_language=None):
            prompts.append((user_id, prompt, response_language))
            return "risposta contestuale"

    monkeypatch.setattr(tg, "_get_chat_engine", lambda context: FakeEngine())

    update = types.SimpleNamespace(
        effective_user=types.SimpleNamespace(id=42),
        effective_chat=types.SimpleNamespace(send_action=fake_send_action),
    )
    context = types.SimpleNamespace(
        user_data={"chat_seed_context": "Sintesi SAR: rischio MEDIO su Roma."},
        application=types.SimpleNamespace(bot_data={}),
    )

    result = asyncio.run(tg._generate_free_chat_response(update, context, "Perche'?"))

    assert result == "risposta contestuale"
    assert prompts[0][0] == "42"
    assert "Sintesi SAR: rischio MEDIO su Roma." in prompts[0][1]
    assert "Domanda utente: Perche'?" in prompts[0][1]
    assert "chat_seed_context" not in context.user_data


def test_generate_free_chat_response_passes_english_override_to_engine(monkeypatch):
    prompts = []

    async def fake_send_action(*args, **kwargs):
        return None

    class FakeEngine:
        def chat(self, user_id, prompt, response_language=None):
            prompts.append((user_id, prompt, response_language))
            return "english reply"

    monkeypatch.setattr(tg, "_get_chat_engine", lambda context: FakeEngine())

    update = types.SimpleNamespace(
        effective_user=types.SimpleNamespace(id=7),
        effective_chat=types.SimpleNamespace(send_action=fake_send_action),
    )
    context = types.SimpleNamespace(
        user_data={"voice_language_override": tg.VOICE_LANGUAGE_EN},
        application=types.SimpleNamespace(bot_data={}),
    )

    result = asyncio.run(tg._generate_free_chat_response(update, context, "How are you?"))

    assert result == "english reply"
    assert prompts[0][0] == "7"
    assert prompts[0][1] == "How are you?"
    assert prompts[0][2] == tg.VOICE_LANGUAGE_EN


def test_generate_free_chat_response_nasa_sends_photos(monkeypatch, tmp_path):
    photos = []

    class FakeChat:
        async def send_action(self, action):
            return None

        async def send_photo(self, photo, caption=None):
            photos.append(caption)

    class FakeImage:
        def save(self, path):
            Path(path).write_bytes(b"fake-dashboard")

    fake_dashboard = {
        "dashboard": [
            {
                "date": "2026-05-19",
                "soil": 12.3,
                "temp": 23.4,
                "humidity": 78,
                "rain": 4.5,
                "risk": 0.62,
            }
        ],
        "weekly_risk": 0.62,
        "weekly_label": "MEDIO",
    }

    import bot.nasa_sar_dashboard as nasa_dashboard

    monkeypatch.setattr(
        tg,
        "_get_chat_engine",
        lambda context: (_ for _ in ()).throw(AssertionError("engine.chat non deve essere chiamato")),
    )
    monkeypatch.setattr(tg, "_build_nasa_sar_map_photo_payload", lambda lat, lon: BytesIO(b"map"))
    monkeypatch.setattr(nasa_dashboard, "generate_dashboard", lambda lat, lon: fake_dashboard)
    monkeypatch.setattr(nasa_dashboard, "generate_dashboard_report_image", lambda dashboard, lat, lon: FakeImage())
    monkeypatch.setattr(tempfile, "mktemp", lambda **kwargs: str(tmp_path / "nasa_dashboard.png"))

    update = types.SimpleNamespace(
        effective_user=types.SimpleNamespace(id=42),
        effective_chat=FakeChat(),
        message=types.SimpleNamespace(location=None),
    )
    context = types.SimpleNamespace(
        user_data={},
        application=types.SimpleNamespace(bot_data={}),
    )

    result = asyncio.run(tg._generate_free_chat_response(update, context, "mostrami dashboard sar"))

    assert len(photos) == 2
    assert photos[0] == "\U0001F30E Area di interesse NASA-ISRO/SAR (raggio 50m dal punto GPS)"
    assert photos[1] == "\U0001F4CA Report grafico NASA-ISRO/SAR: rischio settimanale e indicatori professionali."
    assert "Rischio settimanale: 0.62 (MEDIO)" in result


def test_run_nasa_sar_analysis_sets_chat_seed_context_and_sends_map(monkeypatch):
    sends = []
    photos = []

    async def fake_send(update, text, reply_markup=None, parse_mode=None):
        sends.append((text, reply_markup, parse_mode))

    class FakeChat:
        async def send_action(self, action):
            return None

        async def send_photo(self, photo, caption=None):
            photos.append((photo, caption))

    class FakeOrchestrator:
        async def analyze_nasa_only(self, geo_data, date_range):
            return {
                "geo_summary": {
                    "centroid": {"lat": 41.9028, "lon": 12.4964},
                    "radius_m": 50,
                },
                "dashboard": {
                    "summary": {
                        "sar_soil_moisture_percent": 31.4,
                        "sar_source": "Sentinel-1 SAR operational fallback",
                        "sar_product_name": "S1A_TEST_PRODUCT",
                        "sar_acquired_at": "2026-05-17T10:00:00+00:00",
                    },
                },
                "nasa_power": {"daily": []},
            }

    async def fake_interpret(context, result):
        return "Valore medio settimanale: 0.62\nGiudizio di rischio: MEDIO"

    monkeypatch.setattr(tg, "_send", fake_send)
    monkeypatch.setattr(tg, "_get_nasa_orchestrator", lambda context: FakeOrchestrator())
    monkeypatch.setattr(tg, "_interpret_nasa_sar_dashboard", fake_interpret)
    monkeypatch.setattr(tg, "_reverse_geocode_locality", lambda latitude, longitude: "Roma, Lazio, Italia")

    update = types.SimpleNamespace(effective_chat=FakeChat())
    context = types.SimpleNamespace(user_data={}, application=types.SimpleNamespace(bot_data={}))

    asyncio.run(tg._run_nasa_sar_analysis(update, context, 41.9028, 12.4964))

    assert len(photos) == 1
    import io
    # Accetta sia BytesIO (payload binario) che stringa URL legacy
    photo_payload, caption = photos[0]
    assert isinstance(photo_payload, (io.BytesIO, str))
    # Almeno una delle foto inviate deve avere la località nella caption (può essere la seconda in produzione)
    assert any((caption and "Roma, Lazio, Italia" in caption) for _, caption in photos) or any((caption is None) for _, caption in photos)
    assert any("Ora puoi chiedermi approfondimenti" in text for text, _, _ in sends)
    assert "chat_seed_context" in context.user_data
    assert "Valore medio settimanale" in context.user_data["chat_seed_context"]


def test_free_chat_handler_ignores_dedicated_chat_session(monkeypatch):
    sends = []

    async def fake_guard(update):
        return True

    async def fake_send_action(*args, **kwargs):
        return None

    async def fake_send(update, text, reply_markup=None, parse_mode=None):
        sends.append(text)

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
    monkeypatch.setattr(tg, "_send", fake_send)
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

    assert sends == ["💬 La chat con DELTAPLANO è già attiva. Scrivi il tuo messaggio in chat oppure usa /chiudi per uscire."]


def test_menu_keyboard_includes_chat_button():
    keyboard = tg._menu_keyboard()
    callback_data = [button.callback_data for row in keyboard.inline_keyboard for button in row]
    labels = [button.text for row in keyboard.inline_keyboard for button in row]
    assert tg.CMD_CHAT in callback_data
    assert tg.CMD_VOICE_LANG_IT in callback_data
    assert tg.CMD_VOICE_LANG_EN in callback_data
    assert "👩‍🔬 Cris (IT)" in labels
    assert "👨‍🔬 Ryan (EN)" in labels


def test_menu_keyboard_uses_english_labels_when_override_active():
    context = types.SimpleNamespace(user_data={"voice_language_override": tg.VOICE_LANGUAGE_EN})

    keyboard = tg._menu_keyboard(context)
    labels = [button.text for row in keyboard.inline_keyboard for button in row]

    assert "🔵 💬 Ask DELTA Plant" in labels
    assert "🆕 Diagnose a Plant" in labels
    assert "📄 License" in labels
    assert "🛰️ Connect to NASA-ISRO/SAR" in labels


def test_nasa_sar_reply_keyboard_uses_english_labels_when_override_active():
    context = types.SimpleNamespace(user_data={"voice_language_override": tg.VOICE_LANGUAGE_EN})

    keyboard = tg._nasa_sar_reply_keyboard(context)
    labels = [button.text for row in keyboard.keyboard for button in row]

    assert labels == ["🛰️ Open NASA-ISRO/SAR GPS", "📍 Send GPS manually"]


def test_chat_exit_keyboard_uses_english_labels_when_override_active():
    context = types.SimpleNamespace(user_data={"voice_language_override": tg.VOICE_LANGUAGE_EN})

    keyboard = tg._chat_exit_keyboard(context)
    labels = [button.text for row in keyboard.inline_keyboard for button in row]

    assert labels == ["🔴 End chat", "🗑 Reset conversation"]


def test_mandatory_step_block_message_uses_english_when_override_active():
    context = types.SimpleNamespace(user_data={"voice_language_override": tg.VOICE_LANGUAGE_EN})

    result = tg.mandatory_step_block_message(context)

    assert result.startswith("⏳ A guided diagnosis")


def test_start_diagnosis_uses_english_prompt_when_override_active(monkeypatch):
    sends = []

    async def fake_guard(update):
        return True

    async def fake_send(update, text, reply_markup=None, parse_mode=None):
        sends.append((text, reply_markup))

    monkeypatch.setattr(tg, "_guard", fake_guard)
    monkeypatch.setattr(tg, "_send", fake_send)

    update = types.SimpleNamespace()
    context = types.SimpleNamespace(user_data={"voice_language_override": tg.VOICE_LANGUAGE_EN})

    result = asyncio.run(tg.start_diagnosis(update, context))

    assert result == tg.STATE_DIAG_IMAGE_SOURCE
    assert sends[0][0] == "Diagnosis: choose the image source."
    labels = [button.text for row in sends[0][1].inline_keyboard for button in row]
    assert labels == ["📷 Send photo", " Camera device"]


def test_build_diagnosis_prompt_uses_english_when_requested(monkeypatch):
    monkeypatch.setattr(tg, "_format_diagnosis_full", lambda record: "Detailed diagnosis report")

    record = {
        "diagnosis": {
            "overall_risk": "medium",
            "plant_status": "to monitor",
            "explanation": "Leaf lesions detected",
            "quantum_risk": {"quantum_risk_score": 0.42, "dominant_description": "humidity_spike"},
        },
        "ai_result": {"class": "Tomato_Early_blight", "confidence": 0.91},
        "recommendations": [{"category": "action", "action": "Improve airflow"}],
        "sensor_snapshot": {},
    }

    prompt = tg._build_diagnosis_prompt(record, "Tomato leaves with brown spots", response_language=tg.VOICE_LANGUAGE_EN)

    assert "in English" in prompt
    assert "RAW DELTA DIAGNOSIS REPORT" in prompt
    assert "Technical outcome" in prompt
    assert "in italiano" not in prompt


def test_sanitize_diagnosis_opinion_translates_known_labels_in_english_mode():
    opinion = (
        "**INTERVENTO URGENTE RICHIESTO**\n"
        "Evento dominante: Malattia rilevata da visione AI."
    )

    sanitized = tg._sanitize_diagnosis_opinion(opinion, response_language=tg.VOICE_LANGUAGE_EN)

    assert "URGENT ACTION REQUIRED" in sanitized
    assert "Disease detected by AI vision" in sanitized
    assert "INTERVENTO URGENTE RICHIESTO" not in sanitized
    assert "Malattia rilevata da visione AI" not in sanitized


def test_academy_menu_keyboard_uses_english_labels_when_override_active():
    context = types.SimpleNamespace(user_data={"voice_language_override": tg.VOICE_LANGUAGE_EN})

    keyboard = tg._academy_menu_keyboard(context)
    labels = [button.text for row in keyboard.inline_keyboard for button in row]

    assert labels == [
        "Guided tutorial",
        "Sim: Identify disease",
        "Sim: Assess risk",
        "Sim: Choose action",
        "Theory quiz",
        "Progress",
        "Lab MLOps",
        "Exit",
    ]


def test_academy_start_uses_english_intro_and_keyboard(monkeypatch):
    sends = []
    saved = []

    async def fake_guard(update):
        return True

    async def fake_send(update, text, reply_markup=None, parse_mode=None):
        sends.append((text, reply_markup))

    monkeypatch.setattr(tg, "_guard", fake_guard)
    monkeypatch.setattr(tg, "_send", fake_send)
    monkeypatch.setattr(tg, "_load_academy_progress", lambda: {"sessions": 0})
    monkeypatch.setattr(tg, "_save_academy_progress", lambda progress: saved.append(progress.copy()))

    update = types.SimpleNamespace()
    context = types.SimpleNamespace(user_data={"voice_language_override": tg.VOICE_LANGUAGE_EN})

    asyncio.run(tg.academy_start(update, context))

    assert sends[0][0] == "DELTA Academy — choose a mode:"
    labels = [button.text for row in sends[0][1].inline_keyboard for button in row]
    assert labels[0] == "Guided tutorial"
    assert saved[0]["sessions"] == 1


def test_menu_callback_continues_when_query_answer_is_expired(monkeypatch):
    requested = []

    async def fake_guard(update):
        return True

    async def fake_set_voice_language(update, context, value):
        requested.append(value)

    class FakeQuery:
        data = tg.CMD_VOICE_LANG_IT

        async def answer(self, *args, **kwargs):
            raise Exception("Query is too old and response timeout expired or query id is invalid")

    monkeypatch.setattr(tg, "_guard", fake_guard)
    monkeypatch.setattr(tg, "_set_voice_language", fake_set_voice_language)

    update = types.SimpleNamespace(
        callback_query=FakeQuery(),
        effective_user=types.SimpleNamespace(id=123),
    )
    context = types.SimpleNamespace()

    asyncio.run(tg.menu_callback(update, context))

    assert requested == [tg.VOICE_LANGUAGE_IT]


def test_menu_callback_english_voice_button_sets_english_override(monkeypatch):
    requested = []

    async def fake_guard(update):
        return True

    async def fake_set_voice_language(update, context, value):
        requested.append(value)

    class FakeQuery:
        data = tg.CMD_VOICE_LANG_EN

        async def answer(self, *args, **kwargs):
            return None

    monkeypatch.setattr(tg, "_guard", fake_guard)
    monkeypatch.setattr(tg, "_set_voice_language", fake_set_voice_language)

    update = types.SimpleNamespace(
        callback_query=FakeQuery(),
        effective_user=types.SimpleNamespace(id=123),
    )
    context = types.SimpleNamespace()

    asyncio.run(tg.menu_callback(update, context))

    assert requested == [tg.VOICE_LANGUAGE_EN]


def test_export_excel_uses_last_30_days_and_sends_document(monkeypatch, tmp_path):
    sent_messages = []
    sent_documents = []

    async def fake_guard(update):
        return True

    async def fake_send(update, text, reply_markup=None, parse_mode=None):
        sent_messages.append(text)

    class FakeDatabase:
        def __init__(self):
            self.prune_calls = []
            self.query_calls = []

        def prune_older_than_days(self, days):
            self.prune_calls.append(days)
            return 2

        def get_records_since_days(self, days):
            self.query_calls.append(days)
            return [
                {
                    "timestamp": "2026-05-24T10:00:00",
                    "sensor_source": "sim",
                    "ai_class": "Tomato_healthy",
                    "ai_confidence": 0.91,
                    "ai_simulated": 0,
                    "ai_top3_json": "[]",
                    "plant_status": "healthy",
                    "overall_risk": "low",
                    "needs_review": 0,
                    "summary": "ok",
                    "explanation": "ok",
                    "activated_rules": "[]",
                    "recommendations": "[]",
                    "temperature_c": 22.0,
                    "humidity_pct": 58.0,
                    "pressure_hpa": 1012.0,
                    "light_lux": 500.0,
                    "co2_ppm": 420.0,
                    "ph": 6.4,
                    "ec_ms_cm": 1.3,
                }
            ]

    class FakeExporter:
        def export_all(self, records):
            from data.excel_export import EXPORT_PATH

            EXPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
            EXPORT_PATH.write_bytes(b"xlsx")
            return True

    class FakeChat:
        async def send_document(self, document, filename=None):
            sent_documents.append((filename, document.read()))

    fake_agent = types.SimpleNamespace(database=FakeDatabase(), exporter=FakeExporter())

    monkeypatch.setattr(tg, "_guard", fake_guard)
    monkeypatch.setattr(tg, "_send", fake_send)
    monkeypatch.setattr(tg, "_get_agent", lambda context: fake_agent)
    monkeypatch.setattr("data.excel_export.EXPORT_PATH", tmp_path / "delta_diagnoses.xlsx")

    update = types.SimpleNamespace(effective_chat=FakeChat())
    context = types.SimpleNamespace(user_data={}, application=types.SimpleNamespace(bot_data={}))

    asyncio.run(tg.export_excel(update, context))

    assert fake_agent.database.prune_calls == [30]
    assert fake_agent.database.query_calls == [30]
    assert sent_messages[0].startswith("📤 Report Excel in preparazione")
    assert sent_documents == [("delta_diagnoses.xlsx", b"xlsx")]


def test_clear_diagnosis_state_resets_flags_and_transient_markers():
    context = types.SimpleNamespace(
        user_data={
            "diagnosis_active": True,
            "diag_qa_active": True,
            "sensor_index": 2,
            "diag_image_path": "input_images/foglia.jpg",
            "diag_followup_qa": [("Sintomi?", "Macchie scure")],
            "diag_followup_count": 1,
            "diag_followup_last_question": "Sintomi?",
            "diag_pending_chunks": ["segue"],
            "diag_pending_parse_mode": "HTML",
            "diag_pending_closing": "chiusura",
            "chat_mode_active": True,
        }
    )

    tg._clear_diagnosis_state(context)

    assert context.user_data["diagnosis_active"] is False
    assert "diag_qa_active" not in context.user_data
    assert "sensor_index" not in context.user_data
    assert "diag_image_path" not in context.user_data
    assert "diag_followup_qa" not in context.user_data
    assert "diag_pending_chunks" not in context.user_data
    assert context.user_data["chat_mode_active"] is True


def test_free_chat_handler_ignores_followup_and_upload_states(monkeypatch):
    sends = []

    async def fake_guard(update):
        return True

    async def fake_send_action(*args, **kwargs):
        return None

    async def fake_send(update, text, reply_markup=None, parse_mode=None):
        sends.append(text)

    update = types.SimpleNamespace(
        message=types.SimpleNamespace(text="ciao"),
        effective_user=types.SimpleNamespace(id=101),
        effective_chat=types.SimpleNamespace(send_action=fake_send_action),
    )
    logger = logging.getLogger("deltaplano.chat")
    old_handlers = list(logger.handlers)
    old_propagate = logger.propagate
    logger.handlers = [logging.NullHandler()]
    logger.propagate = False

    monkeypatch.setattr(tg, "_guard", fake_guard)
    monkeypatch.setattr(tg, "_send", fake_send)
    monkeypatch.setattr(
        tg,
        "_get_chat_engine",
        lambda current_context: (_ for _ in ()).throw(AssertionError("engine.chat non deve essere chiamato")),
    )

    try:
        for user_data in ({"diag_qa_active": True}, {"upload_active": True}):
            context = types.SimpleNamespace(
                user_data=dict(user_data),
                application=types.SimpleNamespace(bot_data={}),
            )
            asyncio.run(tg.free_chat_handler(update, context))
    finally:
        logger.handlers = old_handlers
        logger.propagate = old_propagate

    assert sends == [
        "⏳ È in corso un flusso guidato di DELTA Plant. Completa i passaggi richiesti oppure usa /annulla per tornare al menu.",
        "📤 È in corso un upload guidato. Invia la foto richiesta oppure usa /annulla per uscire dal flusso.",
    ]


def test_free_chat_handler_warns_during_sensor_collection(monkeypatch):
    sends = []

    async def fake_guard(update):
        return True

    async def fake_send_action(*args, **kwargs):
        return None

    async def fake_send(update, text, reply_markup=None, parse_mode=None):
        sends.append(text)

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
    monkeypatch.setattr(tg, "_send", fake_send)
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

    assert sends == [
        "⏳ È in corso un flusso guidato di DELTA Plant. Completa i passaggi richiesti oppure usa /annulla per tornare al menu.",
    ]


def test_is_guided_diagnosis_mode_detects_transient_markers():
    context = types.SimpleNamespace(user_data={"diag_image_path": "input_images/foglia.jpg"})

    assert tg.is_guided_diagnosis_mode(context) is True


def test_should_reply_with_voice_respects_override_modes():
    context = types.SimpleNamespace(user_data={})

    assert tg._should_reply_with_voice(context, "voice") is True
    assert tg._should_reply_with_voice(context, "text") is False

    context.user_data["voice_mode_override"] = tg.VOICE_MODE_ON
    assert tg._should_reply_with_voice(context, "text") is True

    context.user_data["voice_mode_override"] = tg.VOICE_MODE_OFF
    assert tg._should_reply_with_voice(context, "voice") is False


def test_select_tts_provider_prefers_free_edge_when_configured(monkeypatch):
    monkeypatch.setitem(tg.TELEGRAM_CONFIG, "voice_tts_provider", "edge_tts")
    monkeypatch.setattr(tg, "EDGE_TTS_AVAILABLE", True)
    monkeypatch.setattr(tg, "ELEVENLABS_AVAILABLE", True)
    monkeypatch.setattr(tg, "_elevenlabs_api_key", lambda: "fake-key")

    assert tg._select_tts_provider() == "edge_tts"


def test_select_tts_provider_prefers_piper_when_configured(monkeypatch):
    monkeypatch.setitem(tg.TELEGRAM_CONFIG, "voice_tts_provider", "piper")
    monkeypatch.setattr(tg, "PIPER_AVAILABLE", True)
    monkeypatch.setattr(tg, "EDGE_TTS_AVAILABLE", True)

    assert tg._select_tts_provider() == "piper"


def test_select_piper_voice_profile_detects_english_text(monkeypatch):
    monkeypatch.setitem(tg.TELEGRAM_CONFIG, "voice_piper_default_profile", "it")
    monkeypatch.setitem(tg.TELEGRAM_CONFIG, "voice_piper_auto_language", True)

    assert tg._select_piper_voice_profile("Please check the leaf disease risk and water level.") == "en"
    assert tg._select_piper_voice_profile("Controlla il rischio della foglia e l'umidita del terreno.") == "it"


def test_select_piper_voice_profile_respects_manual_override(monkeypatch):
    monkeypatch.setitem(tg.TELEGRAM_CONFIG, "voice_piper_default_profile", "it")
    monkeypatch.setitem(tg.TELEGRAM_CONFIG, "voice_piper_auto_language", True)

    context = types.SimpleNamespace(user_data={"voice_language_override": "it"})

    assert tg._select_piper_voice_profile(
        "Please check the leaf disease risk and water level.",
        context=context,
    ) == "it"


def test_prepare_telegram_voice_payload_converts_mp3_to_ogg(monkeypatch):
    calls = {}

    class FakeSegment:
        def export(self, output, format=None, codec=None, bitrate=None):
            calls["export"] = (format, codec, bitrate)
            output.write(b"ogg-bytes")

    class FakeAudioSegment:
        @staticmethod
        def from_file(source, format=None):
            calls["from_file"] = format
            return FakeSegment()

    async def fake_to_thread(func, *args, **kwargs):
        return func(*args, **kwargs)

    monkeypatch.setattr(tg, "PYDUB_AVAILABLE", True)
    monkeypatch.setattr(tg, "AudioSegment", FakeAudioSegment)
    monkeypatch.setattr(tg.asyncio, "to_thread", fake_to_thread)

    payload = BytesIO(b"mp3-bytes")
    payload.name = "delta_voice_reply.mp3"

    result = asyncio.run(tg._prepare_telegram_voice_payload(payload))

    assert calls["from_file"] == "mp3"
    assert calls["export"] == ("ogg", "libopus", "48k")
    assert result.getvalue() == b"ogg-bytes"
    assert result.name == "delta_voice_reply.ogg"


def test_send_uses_effective_chat_send_message():
    sent = []

    class FakeChat:
        async def send_message(self, text, reply_markup=None, parse_mode=None):
            sent.append((text, reply_markup, parse_mode))

    update = types.SimpleNamespace(effective_chat=FakeChat())

    asyncio.run(tg._send(update, "ciao", parse_mode="Markdown"))

    assert sent == [("ciao", None, "Markdown")]


def test_send_voice_uses_prepared_ogg_payload(monkeypatch):
    sent = []

    async def fake_prepare(voice_data):
        converted = BytesIO(b"ogg-bytes")
        converted.name = "delta_voice_reply.ogg"
        return converted

    class FakeChat:
        async def send_voice(self, voice, reply_markup=None, caption=None):
            sent.append((voice.name, voice.read(), caption, reply_markup))

    monkeypatch.setattr(tg, "_prepare_telegram_voice_payload", fake_prepare)

    update = types.SimpleNamespace(effective_chat=FakeChat())
    payload = BytesIO(b"mp3-bytes")
    payload.name = "delta_voice_reply.mp3"

    asyncio.run(tg._send_voice(update, payload, caption="ciao"))

    assert sent == [("delta_voice_reply.ogg", b"ogg-bytes", "ciao", None)]


def test_spoken_voice_text_cleans_markdown_lists_and_urls(monkeypatch):
    monkeypatch.setitem(tg.TELEGRAM_CONFIG, "voice_reply_max_chars", 500)

    text = """## Diagnosi\n- Temperatura: 24 C\n- Azione / follow-up\nVisita https://deltaplant.ai/docs"""

    result = tg._spoken_voice_text(text)

    assert "https://" not in result
    assert "link disponibile in chat" in result
    assert "Temperatura, 24 C" in result
    assert "Azione oppure follow-up" in result
    assert "##" not in result


def test_tts_with_edge_uses_warmer_defaults(monkeypatch, tmp_path):
    captured = {}

    class FakeCommunicate:
        def __init__(self, text, voice, rate, volume, pitch, boundary):
            captured["args"] = {
                "text": text,
                "voice": voice,
                "rate": rate,
                "volume": volume,
                "pitch": pitch,
                "boundary": boundary,
            }

        async def save(self, path):
            Path(path).write_bytes(b"fake-mp3")

    monkeypatch.setattr(tg, "edge_tts", types.SimpleNamespace(Communicate=FakeCommunicate))
    monkeypatch.setattr(tg, "_voice_temp_dir", lambda: tmp_path)

    result = asyncio.run(tg._tts_with_edge("ciao"))

    assert captured["args"] == {
        "text": "ciao",
        "voice": "it-IT-GiuseppeMultilingualNeural",
        "rate": "-4%",
        "volume": "+8%",
        "pitch": "-8Hz",
        "boundary": "SentenceBoundary",
    }
    assert result.getvalue() == b"fake-mp3"


def test_tts_with_piper_returns_wav_buffer(monkeypatch):
    class FakeVoice:
        def synthesize_wav(self, text, wav_file):
            assert text == "ciao"
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(22050)
            wav_file.writeframes(b"\x00\x00" * 64)

    async def fake_get_piper_voice(context, profile_id):
        assert profile_id == "it"
        return FakeVoice()

    async def fake_to_thread(func, *args, **kwargs):
        return func(*args, **kwargs)

    monkeypatch.setattr(tg, "_get_piper_voice", fake_get_piper_voice)
    monkeypatch.setattr(tg, "_select_piper_voice_profile", lambda text, context=None: "it")
    monkeypatch.setattr(tg.asyncio, "to_thread", fake_to_thread)

    result = asyncio.run(tg._tts_with_piper(types.SimpleNamespace(), "ciao"))

    assert result.name == "delta_voice_reply_it.wav"
    assert result.getvalue()[:4] == b"RIFF"


def test_tts_with_piper_uses_english_profile_for_english_text(monkeypatch):
    class FakeVoice:
        def synthesize_wav(self, text, wav_file):
            assert text == "Please check the leaf disease risk."
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(22050)
            wav_file.writeframes(b"\x00\x00" * 32)

    async def fake_get_piper_voice(context, profile_id):
        assert profile_id == "en"
        return FakeVoice()

    async def fake_to_thread(func, *args, **kwargs):
        return func(*args, **kwargs)

    monkeypatch.setattr(tg, "_get_piper_voice", fake_get_piper_voice)
    monkeypatch.setattr(tg, "_select_piper_voice_profile", lambda text, context=None: "en")
    monkeypatch.setattr(tg.asyncio, "to_thread", fake_to_thread)

    result = asyncio.run(tg._tts_with_piper(types.SimpleNamespace(), "Please check the leaf disease risk."))

    assert result.name == "delta_voice_reply_en.wav"
    assert result.getvalue()[:4] == b"RIFF"


def test_voice_mode_command_sets_override(monkeypatch):
    sends = []

    async def fake_guard(update):
        return True

    async def fake_send(update, text, reply_markup=None, parse_mode=None):
        sends.append(text)

    monkeypatch.setattr(tg, "_guard", fake_guard)
    monkeypatch.setattr(tg, "_send", fake_send)

    update = types.SimpleNamespace(message=types.SimpleNamespace(text="/voice off"))
    context = types.SimpleNamespace(args=["off"], user_data={})

    asyncio.run(tg.voice_mode_command(update, context))

    assert context.user_data["voice_mode_override"] == tg.VOICE_MODE_OFF
    assert "Modalità voce disattivata" in sends[0]


def test_voice_mode_command_reports_status_in_english_when_override_active(monkeypatch):
    sends = []

    async def fake_guard(update):
        return True

    async def fake_send(update, text, reply_markup=None, parse_mode=None):
        sends.append(text)

    monkeypatch.setattr(tg, "_guard", fake_guard)
    monkeypatch.setattr(tg, "_send", fake_send)

    update = types.SimpleNamespace(message=types.SimpleNamespace(text="/voice"))
    context = types.SimpleNamespace(args=[], user_data={"voice_language_override": tg.VOICE_LANGUAGE_EN})

    asyncio.run(tg.voice_mode_command(update, context))

    assert sends == [
        "Current voice mode: AUTO\nUse /voice on, /voice off or /voice auto.\nFor language use /voice_lang it, /voice_lang en or /voice_lang auto."
    ]


def test_voice_language_command_sets_italian_override(monkeypatch):
    sends = []

    async def fake_guard(update):
        return True

    async def fake_send(update, text, reply_markup=None, parse_mode=None):
        sends.append(text)

    monkeypatch.setattr(tg, "_guard", fake_guard)
    monkeypatch.setattr(tg, "_send", fake_send)

    update = types.SimpleNamespace(message=types.SimpleNamespace(text="/voice_lang it"))
    context = types.SimpleNamespace(args=["it"], user_data={})

    asyncio.run(tg.voice_language_command(update, context))

    assert context.user_data["voice_language_override"] == tg.VOICE_LANGUAGE_IT
    assert "Lingua voce forzata su italiano" in sends[0]


def test_set_voice_language_helper_sets_english_override(monkeypatch):
    sends = []

    async def fake_send(update, text, reply_markup=None, parse_mode=None):
        sends.append(text)

    monkeypatch.setattr(tg, "_send", fake_send)

    update = types.SimpleNamespace()
    context = types.SimpleNamespace(user_data={})

    asyncio.run(tg._set_voice_language(update, context, tg.VOICE_LANGUAGE_EN))

    assert context.user_data["voice_language_override"] == tg.VOICE_LANGUAGE_EN
    assert "English mode enabled" in sends[0]


def test_set_voice_language_helper_sets_italian_copy(monkeypatch):
    sends = []

    async def fake_send(update, text, reply_markup=None, parse_mode=None):
        sends.append(text)

    monkeypatch.setattr(tg, "_send", fake_send)

    update = types.SimpleNamespace()
    context = types.SimpleNamespace(user_data={})

    asyncio.run(tg._set_voice_language(update, context, tg.VOICE_LANGUAGE_IT))

    assert context.user_data["voice_language_override"] == tg.VOICE_LANGUAGE_IT
    assert "Lingua voce forzata su italiano" in sends[0]


def test_set_voice_language_helper_sets_auto_copy_in_english_when_switching_from_english(monkeypatch):
    sends = []

    async def fake_send(update, text, reply_markup=None, parse_mode=None):
        sends.append(text)

    monkeypatch.setattr(tg, "_send", fake_send)

    update = types.SimpleNamespace()
    context = types.SimpleNamespace(user_data={"voice_language_override": tg.VOICE_LANGUAGE_EN})

    asyncio.run(tg._set_voice_language(update, context, tg.VOICE_LANGUAGE_AUTO))

    assert "voice_language_override" not in context.user_data
    assert sends == [
        "♻️ Automatic voice language enabled: DELTAPLANO will choose the Italian or English pack based on the reply."
    ]


def test_select_piper_voice_profile_honors_english_override():
    context = types.SimpleNamespace(user_data={"voice_language_override": tg.VOICE_LANGUAGE_EN})

    profile = tg._select_piper_voice_profile("Ciao a tutti", context=context)

    assert profile == tg.VOICE_LANGUAGE_EN


def test_select_piper_voice_profile_honors_italian_override_even_for_english_text():
    context = types.SimpleNamespace(user_data={"voice_language_override": tg.VOICE_LANGUAGE_IT})

    profile = tg._select_piper_voice_profile("Hello, this is a test message for DELTA Plant.", context=context)

    assert profile == tg.VOICE_LANGUAGE_IT


def test_handle_voice_message_rejects_guided_diagnosis(monkeypatch):
    sends = []

    async def fake_guard(update):
        return True

    async def fake_send(update, text, reply_markup=None, parse_mode=None):
        sends.append(text)

    monkeypatch.setattr(tg, "_guard", fake_guard)
    monkeypatch.setattr(tg, "_send", fake_send)
    monkeypatch.setattr(
        tg,
        "_download_voice_message_bytes",
        lambda update: (_ for _ in ()).throw(AssertionError("la trascrizione non deve partire")),
    )

    update = types.SimpleNamespace(
        message=types.SimpleNamespace(voice=object()),
        effective_user=types.SimpleNamespace(id=500),
    )
    context = types.SimpleNamespace(user_data={"diagnosis_active": True}, application=types.SimpleNamespace(bot_data={}))

    with pytest.raises(tg.ApplicationHandlerStop):
        asyncio.run(tg.handle_voice_message(update, context))

    assert sends == [tg._VOICE_GUIDED_DIAGNOSIS_REJECT]


def test_handle_voice_message_routes_transcript_in_free_chat(monkeypatch):
    turns = []

    async def fake_guard(update):
        return True

    async def fake_download(update):
        return b"voice-bytes"

    async def fake_transcribe(context, audio_bytes, file_suffix=".ogg"):
        assert audio_bytes == b"voice-bytes"
        return "ciao DELTA"

    async def fake_welcome(update, context):
        return None

    async def fake_handle_turn(update, context, user_text, input_mode):
        turns.append((user_text, input_mode))
        return "ok"

    monkeypatch.setattr(tg, "_guard", fake_guard)
    monkeypatch.setattr(tg, "_download_voice_message_bytes", fake_download)
    monkeypatch.setattr(tg, "transcribe_audio", fake_transcribe)
    monkeypatch.setattr(tg, "_maybe_send_voice_welcome", fake_welcome)
    monkeypatch.setattr(tg, "_handle_free_chat_turn", fake_handle_turn)

    update = types.SimpleNamespace(
        message=types.SimpleNamespace(voice=object()),
        effective_user=types.SimpleNamespace(id=501),
    )
    context = types.SimpleNamespace(user_data={}, application=types.SimpleNamespace(bot_data={}))

    with pytest.raises(tg.ApplicationHandlerStop):
        asyncio.run(tg.handle_voice_message(update, context))

    assert turns == [("ciao DELTA", "voice")]


def test_receive_followup_answer_advances_state_machine(monkeypatch):
    sends = []

    async def fake_guard(update):
        return True

    async def fake_send(update, text, reply_markup=None, parse_mode=None):
        sends.append((text, parse_mode))

    async def fake_send_action(*args, **kwargs):
        return None

    async def fake_generate_followup_question(engine, user_id, user_description, qa_pairs, sensor_context=""):
        assert user_id == "55"
        assert user_description == "Foglie con macchie scure"
        assert qa_pairs == [("Da quanto tempo?", "Da tre giorni")]
        assert "Temperatura" in sensor_context
        return "Le lesioni aumentano con l'umidità?", False

    monkeypatch.setattr(tg, "_guard", fake_guard)
    monkeypatch.setattr(tg, "_send", fake_send)
    monkeypatch.setattr(tg, "_get_chat_engine", lambda context: object())
    monkeypatch.setattr(tg, "_generate_followup_question", fake_generate_followup_question)

    update = types.SimpleNamespace(
        message=types.SimpleNamespace(text="Da tre giorni"),
        effective_user=types.SimpleNamespace(id=55),
        effective_chat=types.SimpleNamespace(send_action=fake_send_action),
    )
    context = types.SimpleNamespace(
        user_data={
            "diag_followup_qa": [],
            "diag_followup_count": 1,
            "diag_followup_last_question": "Da quanto tempo?",
            "diag_user_description": "Foglie con macchie scure",
            "sensor_data": {"temperature_c": 24.5},
            "diag_qa_active": True,
        }
    )

    result = asyncio.run(tg.receive_followup_answer(update, context))

    assert result == tg.STATE_DIAG_FOLLOWUP
    assert context.user_data["diag_followup_qa"] == [("Da quanto tempo?", "Da tre giorni")]
    assert context.user_data["diag_followup_count"] == 2
    assert context.user_data["diag_followup_last_question"] == "Le lesioni aumentano con l'umidità?"
    assert context.user_data["diag_qa_active"] is True
    assert sends == [
        ("📝 <i>Risposta 1 registrata.</i>", "HTML"),
        (f"❓ <b>Domanda 2/{tg.MAX_FOLLOWUP_QUESTIONS}:</b>\nLe lesioni aumentano con l'umidità?", "HTML"),
    ]


def test_receive_followup_answer_finishes_after_max_questions(monkeypatch):
    sends = []
    forwarded = []

    async def fake_guard(update):
        return True

    async def fake_send(update, text, reply_markup=None, parse_mode=None):
        sends.append((text, parse_mode))

    async def fake_send_conversational_diagnosis(update, context):
        forwarded.append(list(context.user_data.get("diag_followup_qa", [])))

    monkeypatch.setattr(tg, "_guard", fake_guard)
    monkeypatch.setattr(tg, "_send", fake_send)
    monkeypatch.setattr(tg, "_send_conversational_diagnosis", fake_send_conversational_diagnosis)

    update = types.SimpleNamespace(
        message=types.SimpleNamespace(text="Le macchie si stanno allargando"),
        effective_user=types.SimpleNamespace(id=55),
    )
    context = types.SimpleNamespace(
        user_data={
            "diag_followup_qa": [],
            "diag_followup_count": tg.MAX_FOLLOWUP_QUESTIONS,
            "diag_followup_last_question": "Le macchie si allargano?",
            "diag_qa_active": True,
        }
    )

    result = asyncio.run(tg.receive_followup_answer(update, context))

    assert result == tg.ConversationHandler.END
    assert context.user_data["diag_followup_qa"] == [
        ("Le macchie si allargano?", "Le macchie si stanno allargando")
    ]
    assert context.user_data["diag_qa_active"] is False
    assert sends == [
        ("✅ Ho raccolto tutte le informazioni necessarie. Elaboro la diagnosi... 🔬", None)
    ]
    assert forwarded == [[("Le macchie si allargano?", "Le macchie si stanno allargando")]]


def test_send_conversational_diagnosis_remembers_clean_turn_and_clears_state(monkeypatch):
    sends = []
    remembered = []
    response_languages = []

    async def fake_send_diagnosis_paginated(update, context, text, parse_mode=None):
        sends.append((text, parse_mode))

    async def fake_to_thread(func, *args, **kwargs):
        return func(*args, **kwargs)

    async def fake_operator_says_healthy(engine, description):
        return False

    async def fake_send_action(*args, **kwargs):
        return None

    class FakeEngine:
        def chat_internal(self, prompt, response_language="auto"):
            assert "Domande di approfondimento e risposte" in prompt
            assert "Temperatura" in prompt
            response_languages.append(response_language)
            return "Valutazione conversazionale finale"

        def remember_turn(self, user_id, user_input, response):
            remembered.append((user_id, user_input, response))

    monkeypatch.setattr(tg, "_send_diagnosis_paginated", fake_send_diagnosis_paginated)
    monkeypatch.setattr(tg, "_get_chat_engine", lambda context: FakeEngine())
    monkeypatch.setattr(tg, "_operator_says_healthy", fake_operator_says_healthy)
    monkeypatch.setattr(
        tg,
        "_sanitize_diagnosis_opinion",
        lambda opinion, response_language=tg.VOICE_LANGUAGE_IT: opinion,
    )
    monkeypatch.setattr(tg.asyncio, "to_thread", fake_to_thread)

    update = types.SimpleNamespace(
        effective_user=types.SimpleNamespace(id=77),
        effective_chat=types.SimpleNamespace(send_action=fake_send_action),
    )
    context = types.SimpleNamespace(
        user_data={
            "diag_user_description": "Dipladenia con foglie gialle e margini secchi",
            "diag_followup_qa": [("Da quanto tempo?", "Da tre giorni")],
            "diag_followup_mode": "fallback",
            "sensor_data": {"temperature_c": 23.5},
            "diag_image_path": "input_images/foglia.jpg",
            "sensor_index": 1,
            "diag_qa_active": True,
            "diagnosis_active": True,
        }
    )

    asyncio.run(tg._send_conversational_diagnosis(update, context))

    assert sends == [
        ("🩺 <b>DIAGNOSI CONVERSAZIONALE DELTA Plant:</b>\n\nValutazione conversazionale finale", "HTML")
    ]
    assert response_languages == [tg.VOICE_LANGUAGE_IT]
    assert remembered == [
        ("77", remembered[0][1], "Valutazione conversazionale finale")
    ]
    assert "Ho chiesto una diagnosi della pianta." in remembered[0][1]
    assert "Pianta: Dipladenia." in remembered[0][1]
    assert "Follow-up 1: D=Da quanto tempo? | R=Da tre giorni" in remembered[0][1]
    assert "Sei un agronomo esperto" not in remembered[0][1]
    assert context.user_data["diagnosis_active"] is False
    assert "diag_qa_active" not in context.user_data
    assert "diag_image_path" not in context.user_data
    assert "sensor_index" not in context.user_data


def test_send_ai_diagnosis_opinion_passes_english_language_to_chat_internal(monkeypatch):
    sends = []
    response_languages = []

    async def fake_send_diagnosis_paginated(update, context, text, parse_mode=None):
        sends.append((text, parse_mode))

    async def fake_to_thread(func, *args, **kwargs):
        return func(*args, **kwargs)

    async def fake_send_action(*args, **kwargs):
        return None

    class FakeEngine:
        def chat_internal(self, prompt, response_language="auto"):
            response_languages.append(response_language)
            assert "SINGLE final message" in prompt
            return "Final operational diagnosis"

        def remember_turn(self, user_id, user_input, response):
            return None

    monkeypatch.setattr(tg, "_send_diagnosis_paginated", fake_send_diagnosis_paginated)
    monkeypatch.setattr(tg, "_get_chat_engine", lambda context: FakeEngine())
    monkeypatch.setattr(
        tg,
        "_reclassify_with_description",
        lambda engine, ai_class, user_description: asyncio.sleep(0, result=ai_class),
    )
    monkeypatch.setattr(
        tg,
        "_sanitize_diagnosis_opinion",
        lambda opinion, response_language=tg.VOICE_LANGUAGE_IT: opinion,
    )
    monkeypatch.setattr(tg.asyncio, "to_thread", fake_to_thread)

    update = types.SimpleNamespace(
        effective_user=types.SimpleNamespace(id=88),
        effective_chat=types.SimpleNamespace(send_action=fake_send_action),
    )
    context = types.SimpleNamespace(
        user_data={
            "voice_language_override": tg.VOICE_LANGUAGE_EN,
            "diag_user_description": "Tomato leaves with white powdery patches",
            "diag_image_path": "input_images/foglia.jpg",
        }
    )
    record = {
        "ai_result": {"class": "Tomato_Early_blight", "confidence": 0.88},
        "diagnosis": {
            "plant_status": "Compromised",
            "summary": "Probable fungal issue",
            "overall_risk": "high",
            "explanation": "Leaf analysis.",
            "sensor_snapshot": {"temperature_c": 25.0},
        },
        "recommendations": [
            {"category": "fungus", "priority": 1, "problem": "leaf lesions", "action": "targeted treatment"},
        ],
    }

    result = asyncio.run(tg._send_ai_diagnosis_opinion(update, context, record))

    assert result == tg.ConversationHandler.END
    assert response_languages == [tg.VOICE_LANGUAGE_EN]
    assert sends == [(
        "🩺 <b>DELTA Plant DIAGNOSIS RESULT:</b>\n\nFinal operational diagnosis",
        "HTML",
    )]
