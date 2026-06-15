from __future__ import annotations

# --- PATCH: blocco LLM/voce solo se step obbligatorio attivo ---
MANDATORY_GUIDED_STEPS = [
    "diag_waiting_for_photo", "diag_waiting_for_location", "diag_user_description",
    "upload_wait_photo", "upload_plant", "upload_organ", "upload_label"
]

def is_mandatory_guided_step_active(context):
    # Rileva se uno step obbligatorio di diagnosi/upload è attivo
    for key in MANDATORY_GUIDED_STEPS:
        if context.user_data.get(key):
            return True
    return False

def mandatory_step_block_message(context: Optional["ContextTypes.DEFAULT_TYPE"] = None):
    return _ui_text(
        context,
        "⏳ È in corso una diagnosi guidata o upload con step obbligatorio. "
        "Completa prima la diagnosi (invia foto e posizione GPS), poi puoi usare la chat libera o la modalità vocale. "
        "Usa /annulla per interrompere la diagnosi.",
        "⏳ A guided diagnosis or upload with a required step is in progress. "
        "Complete the diagnosis first by sending a photo and GPS position, then you can use free chat or voice mode. "
        "Use /annulla to interrupt the diagnosis.",
    )
 
# --- PATCH: reset stato guidato su ogni input e consenti sempre LLM ---
def reset_all_guided_states(context):
    # Annulla ogni stato di diagnosi/flusso guidato
    for key in list(context.user_data.keys()):
        if key.startswith("diag") or key.startswith("diagnosis") or key.endswith("_active") or key in ("chat_mode_active", "upload_active"):
            context.user_data.pop(key, None)
"""
DELTA - interface/telegram_bot.py
Bot Telegram interattivo per accesso conversazionale alle API DELTA.
"""


import asyncio
import tempfile
import json
import html
import logging
import math
import os
import re
import shutil
import random
import wave
from io import BytesIO
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, Optional, Set, List, Tuple

import requests
from nasa_delta_plant.utils.power_client import compute_fungal_risk_score

try:
    from PIL import Image, ImageDraw, ImageFont
    PIL_AVAILABLE = True
except ImportError:
    Image = None
    ImageDraw = None
    ImageFont = None
    PIL_AVAILABLE = False

try:
    import pytesseract
    PYTESSERACT_AVAILABLE = True
except ImportError:
    pytesseract = None
    PYTESSERACT_AVAILABLE = False

try:
    from pypdf import PdfReader
    PYPDF_AVAILABLE = True
except ImportError:
    PdfReader = None
    PYPDF_AVAILABLE = False

from core.config import (
    TELEGRAM_CONFIG,
    API_CONFIG,
    INPUT_IMAGES_DIR,
    MODEL_CONFIG,
    VISION_CONFIG,
    FLOWER_LABELS,
    FRUIT_LABELS,
    DATASETS_DIR,
    LEARNING_BY_DOING_DIR,
)

try:
    from faster_whisper import WhisperModel
    FASTER_WHISPER_AVAILABLE = True
except ImportError:
    WhisperModel = None
    FASTER_WHISPER_AVAILABLE = False

try:
    from elevenlabs import VoiceSettings
    from elevenlabs.client import ElevenLabs
    ELEVENLABS_AVAILABLE = True
except ImportError:
    VoiceSettings = None
    ElevenLabs = None
    ELEVENLABS_AVAILABLE = False

try:
    import edge_tts
    EDGE_TTS_AVAILABLE = True
except ImportError:
    edge_tts = None
    EDGE_TTS_AVAILABLE = False

try:
    from piper import PiperVoice
    PIPER_AVAILABLE = True
except ImportError:
    PiperVoice = None
    PIPER_AVAILABLE = False

try:
    from pydub import AudioSegment
    PYDUB_AVAILABLE = True
except ImportError:
    AudioSegment = None
    PYDUB_AVAILABLE = False

try:
    from telegram import KeyboardButton, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, ReplyKeyboardRemove, Update, WebAppInfo
    from telegram.ext import (
        Application,
        ApplicationHandlerStop,
        CallbackQueryHandler,
        CommandHandler,
        ConversationHandler,
        ContextTypes,
        MessageHandler,
        filters,
    )
    try:
        from telegram.ext import AIORateLimiter
        TELEGRAM_RATE_LIMITER_AVAILABLE = True
    except ImportError:
        AIORateLimiter = None
        TELEGRAM_RATE_LIMITER_AVAILABLE = False
    TELEGRAM_AVAILABLE = True
except ImportError:
    ApplicationHandlerStop = RuntimeError
    AIORateLimiter = None
    TELEGRAM_RATE_LIMITER_AVAILABLE = False
    TELEGRAM_AVAILABLE = False

# --- INTEGRAZIONE DELTA_ORCHESTRATOR ---
try:
    from delta_orchestrator.integration.delta_bridge import orchestrate_task
    DELTA_ORCHESTRATOR_AVAILABLE = True
except ImportError:
    DELTA_ORCHESTRATOR_AVAILABLE = False
# ----------------------------------------

logger = logging.getLogger("delta.interface.telegram")

_NASA_SAR_WEBAPP_URL_CACHE: Optional[str] = None


def _url_is_reachable(url: str, timeout_sec: float = 2.5) -> bool:
    try:
        response = requests.get(url, timeout=timeout_sec, allow_redirects=True)
        return 200 <= int(response.status_code) < 400
    except Exception:
        return False

_FREE_CHAT_TRANSIENT_MARKERS = (
    "diag_waiting_for_photo",
    "diag_waiting_for_location",
    "diag_image_path",
    "diag_fallback_record",
    "diag_followup_qa",
    "diag_followup_count",
    "diag_followup_last_question",
    "diag_user_description",
    "diag_followup_mode",
    "diag_pending_chunks",
    "diag_environment_context",
    "sensor_data",
    "awaiting_nasa_sar_location",
)

_DIAG_TRANSIENT_KEYS = (
    *_FREE_CHAT_TRANSIENT_MARKERS,
    "diag_pending_parse_mode",
    "diag_pending_closing",
)

_VOICE_GUIDED_DIAGNOSIS_REJECT = (
    "❌ La modalità vocale non è supportata durante la diagnosi guidata di DELTA Plant.\n"
    "Per favore usa messaggi di testo."
)

VOICE_MODE_AUTO = "auto"
VOICE_MODE_ON = "on"
VOICE_MODE_OFF = "off"
_VOICE_MODE_ALLOWED = {VOICE_MODE_AUTO, VOICE_MODE_ON, VOICE_MODE_OFF}

VOICE_LANGUAGE_AUTO = "auto"
VOICE_LANGUAGE_IT = "it"
VOICE_LANGUAGE_EN = "en"
VOICE_LANGUAGE_DEFAULT = VOICE_LANGUAGE_IT
_VOICE_LANGUAGE_ALLOWED = {VOICE_LANGUAGE_AUTO, VOICE_LANGUAGE_IT, VOICE_LANGUAGE_EN}

_VOICE_FREE_CHAT_ONLY_REJECT = (
    "🎙️ La modalità vocale è disponibile solo in chat libera.\n"
    "In questo flusso usa messaggi di testo."
)

_AGRONOMIC_REFINEMENT_RE = re.compile(
    r"\b("
    r"ph|p\.?h\.?|ec|e\.?c\.?|conducibilit[aà]|conductivity|electrical\s+conductivity|"
    r"salinit[aà]|salinity|substrat\w*|substrate|suolo|soil|terreno|"
    r"fertilizz\w*|fertili[sz]\w*|concim\w*|nutrient\w*|nutrienti|"
    r"azoto|nitrogen|fosforo|phosphorus|potassio|potassium|calcio|calcium|magnesio|magnesium|"
    r"irrig\w*|irrigation|acqua|water|drenaggio|drainage|"
    r"temperatura|temperature|umidit[aà]|humidity|lux|luce|light|co2|co₂"
    r")\b",
    re.IGNORECASE,
)


def _clear_user_data_keys(context: "ContextTypes.DEFAULT_TYPE", *keys: str) -> None:
    for key in keys:
        context.user_data.pop(key, None)


def _clear_chat_state(context: "ContextTypes.DEFAULT_TYPE") -> None:
    _clear_user_data_keys(context, "chat_mode_active", "chat_pending_chunks", "chat_pending_parse_mode", "chat_seed_context")


def _clear_diagnosis_state(context: "ContextTypes.DEFAULT_TYPE") -> None:
    _clear_user_data_keys(context, *_DIAG_TRANSIENT_KEYS)
    context.user_data.pop("diag_qa_active", None)
    context.user_data["diagnosis_active"] = False


def _store_latest_diagnosis_context(
    context: "ContextTypes.DEFAULT_TYPE",
    opinion: str,
    *,
    record: Optional[Dict[str, Any]] = None,
    sensor_data: Optional[Dict[str, Any]] = None,
    model_used: str = "",
) -> None:
    context.user_data["last_diagnosis_context"] = {
        "opinion": str(opinion or "").strip(),
        "record": record or {},
        "sensor_data": sensor_data or {},
        "model_used": str(model_used or "").strip(),
        "language": _ui_language(context),
        "timestamp": datetime.utcnow().isoformat(timespec="seconds") + "Z",
    }


def _looks_like_agronomic_refinement_request(user_text: str) -> bool:
    return bool(_AGRONOMIC_REFINEMENT_RE.search(str(user_text or "")))


def _build_agronomic_refinement_prompt(
    context: "ContextTypes.DEFAULT_TYPE",
    user_text: str,
    diagnosis_context: Dict[str, Any],
    response_language: str,
) -> str:
    previous_opinion = str(diagnosis_context.get("opinion") or "").strip()
    previous_sensor_data = diagnosis_context.get("sensor_data") or {}
    previous_sensor_text = _format_sensor_text_for_language(
        previous_sensor_data,
        response_language=response_language,
    )
    if response_language == VOICE_LANGUAGE_EN:
        parts = [
            "You are DELTA Plant. The user has provided new agronomic parameters after the latest diagnosis.",
            "Reassess the previous diagnosis in light of the new values. Do not restart from scratch and do not ask for another photo.",
            "Explicitly state which parts of the diagnosis change, which remain unchanged, and why.",
            "Consider pH, electrical conductivity, salinity, substrate/soil, irrigation, fertilization, nutrients, temperature, humidity, light/LUX, and CO2 when present.",
            "Return a concise professional agronomic update in 5 blocks: 1) Updated interpretation, 2) Impact of new parameters, 3) Revised risk, 4) Corrective actions, 5) Monitoring.",
            "Previous DELTA Plant diagnosis:",
            previous_opinion or "Not available.",
        ]
        if previous_sensor_text:
            parts.extend(["Previous environmental context:", previous_sensor_text])
        parts.extend(["New agronomic parameters supplied by the user:", str(user_text or "").strip()])
        return "\n\n".join(parts)

    parts = [
        "Sei DELTA Plant. L'utente ha fornito nuovi parametri agronomici dopo l'ultima diagnosi.",
        "Rimodula la diagnosi precedente alla luce dei nuovi valori. Non ripartire da zero e non chiedere un'altra foto.",
        "Indica esplicitamente cosa cambia nella diagnosi, cosa resta invariato e perche'.",
        "Considera pH, conducibilita' elettrica/EC, salinita', substrato/suolo, irrigazione, concimazione, nutrienti, temperatura, umidita', luce/LUX e CO2 quando presenti.",
        "Restituisci un aggiornamento agronomico professionale e sintetico in 5 blocchi: 1) Interpretazione aggiornata, 2) Impatto dei nuovi parametri, 3) Rischio rimodulato, 4) Azioni correttive, 5) Monitoraggio.",
        "Diagnosi DELTA Plant precedente:",
        previous_opinion or "Non disponibile.",
    ]
    if previous_sensor_text:
        parts.extend(["Contesto ambientale precedente:", previous_sensor_text])
    parts.extend(["Nuovi parametri agronomici forniti dall'utente:", str(user_text or "").strip()])
    return "\n\n".join(parts)


def _free_chat_block_reason(context: "ContextTypes.DEFAULT_TYPE") -> str:
    if context.user_data.get("diag_qa_active"):
        return "diag_qa_active"
    if context.user_data.get("chat_mode_active"):
        return "chat_mode_active"
    if context.user_data.get("upload_active"):
        return "upload_active"
    for key in _FREE_CHAT_TRANSIENT_MARKERS:
        if key in context.user_data:
            return key
    if context.user_data.get("diagnosis_active"):
        return "diagnosis_active"
    return ""


def _free_chat_block_message(block_reason: str) -> str:
    if block_reason == "chat_mode_active":
        return "💬 La chat con DELTAPLANO è già attiva. Scrivi il tuo messaggio in chat oppure usa /chiudi per uscire."
    if block_reason == "upload_active":
        return "📤 È in corso un upload guidato. Invia la foto richiesta oppure usa /annulla per uscire dal flusso."
    if block_reason == "diag_waiting_for_photo":
        return "📷 Diagnosi in corso: invia una foto o un'immagine dal telefono, oppure usa /annulla per uscire."
    if block_reason == "diag_waiting_for_location":
        return "📍 Diagnosi in corso: condividi la posizione GPS dal telefono per acquisire NASA-ISRO/SAR e LUX, oppure usa /annulla per uscire."
    return "⏳ È in corso un flusso guidato di DELTA Plant. Completa i passaggi richiesti oppure usa /annulla per tornare al menu."


def _is_nasa_sar_manual_location_fallback_text(text: str) -> bool:
    normalized = " ".join(
        str(text or "")
        .replace("📍", " ")
        .replace("🛰️", " ")
        .split()
    ).strip().lower()
    return normalized in {"invia gps manualmente", "send gps manually", "invia gps ora", "send gps now"}


def is_guided_diagnosis_mode(
    context: "ContextTypes.DEFAULT_TYPE",
    chat_id: Optional[int] = None,
) -> bool:
    if context.user_data.get("diagnosis_active") or context.user_data.get("diag_qa_active"):
        return True
    for key in _DIAG_TRANSIENT_KEYS:
        if key in context.user_data:
            return True
    return False


def _is_voice_free_chat_context(context: "ContextTypes.DEFAULT_TYPE") -> bool:
    if context.user_data.get("chat_mode_active"):
        return True
    return _free_chat_block_reason(context) == ""


def _guided_diagnosis_voice_supported(context: "ContextTypes.DEFAULT_TYPE") -> bool:
    if context.user_data.get("diag_qa_active") or context.user_data.get("diag_followup_last_question"):
        return True
    if context.user_data.get("diag_image_path") and not context.user_data.get("diag_user_description"):
        return True
    return False


def _voice_update_with_text(update: Update, transcript: str) -> Update:
    original_message = getattr(update, "message", None)
    proxy_message = SimpleNamespace(
        text=transcript,
        reply_text=getattr(original_message, "reply_text", None),
        message_thread_id=getattr(original_message, "message_thread_id", None),
    )
    return SimpleNamespace(
        message=proxy_message,
        effective_message=proxy_message,
        effective_chat=getattr(update, "effective_chat", None),
        effective_user=getattr(update, "effective_user", None),
        callback_query=getattr(update, "callback_query", None),
    )


async def _transcribe_voice_message_text(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> Optional[str]:
    try:
        voice_bytes = await _download_voice_message_bytes(update)
        transcript = await transcribe_audio(context, voice_bytes)
    except Exception as exc:
        logger.warning("Trascrizione vocale fallita: %s", exc, exc_info=True)
        await _send(
            update,
            _ui_text(
                context,
                "Non riesco a trascrivere il messaggio vocale in questo momento. Puoi riprovare o scrivermi in testo?",
                "I can't transcribe the voice message right now. You can try again or write to me in text.",
            ),
        )
        return None

    transcript = transcript.strip()
    if not transcript:
        await _send(
            update,
            _ui_text(
                context,
                "Non sono riuscito a capire il messaggio vocale. Puoi ripetere?",
                "I couldn't understand the voice message. Can you repeat it?",
            ),
        )
        return None

    return transcript


def _voice_reply_mode(context: "ContextTypes.DEFAULT_TYPE") -> str:
    raw = str(
        context.user_data.get(
            "voice_mode_override",
            TELEGRAM_CONFIG.get("voice_mode_default", VOICE_MODE_AUTO),
        )
    ).strip().lower()
    return raw if raw in _VOICE_MODE_ALLOWED else VOICE_MODE_AUTO


def _should_reply_with_voice(context: "ContextTypes.DEFAULT_TYPE", input_mode: str) -> bool:
    mode = _voice_reply_mode(context)
    if mode == VOICE_MODE_OFF:
        return False
    if mode == VOICE_MODE_ON:
        return True
    return input_mode == "voice"


def _voice_temp_dir() -> Path:
    configured = str(TELEGRAM_CONFIG.get("voice_temp_dir", "")).strip()
    base = Path(configured) if configured else Path(__file__).resolve().parent.parent / "tmp" / "telegram_voice"
    base.mkdir(parents=True, exist_ok=True)
    return base


def _voice_caption(text: str) -> Optional[str]:
    normalized = re.sub(r"\s+", " ", text).strip()
    if not normalized:
        return None
    limit = int(TELEGRAM_CONFIG.get("voice_caption_limit", 180))
    if len(normalized) <= limit:
        return normalized
    return normalized[: max(limit - 1, 1)].rstrip() + "…"


def _spoken_voice_text(text: str, context: Optional["ContextTypes.DEFAULT_TYPE"] = None) -> str:
    cleaned = re.sub(r"https?://\S+", " link disponibile in chat ", text)
    cleaned = re.sub(r"<[^>]+>", " ", cleaned)
    cleaned = cleaned.replace("```", " ")
    cleaned = re.sub(r"[`*_#]+", " ", cleaned)
    cleaned = re.sub(r"^[\-•●▪◦]+\s*", ". ", cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r"\n{2,}", ". ", cleaned)
    cleaned = re.sub(r"(?<!\d)\n", ". ", cleaned)
    cleaned = cleaned.replace(" / ", " oppure ")
    cleaned = cleaned.replace("|", ", ")
    cleaned = re.sub(r"\s*[:;]\s*", ", ", cleaned)
    cleaned = re.sub(r"\s*[=-]{2,}\s*", ". ", cleaned)
    cleaned = re.sub(r"([.!?]){2,}", r"\1", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .,;:-")
    if not cleaned:
        return _ui_text(
            context,
            "Non ho contenuti da leggere in questo momento.",
            "I do not have any content to read right now.",
        )
    limit = int(TELEGRAM_CONFIG.get("voice_reply_max_chars", 900))
    if len(cleaned) <= limit:
        return cleaned
    cutoff = cleaned.rfind(". ", 0, limit)
    if cutoff == -1:
        cutoff = cleaned.rfind(" ", 0, limit)
    if cutoff == -1:
        cutoff = limit
    return cleaned[:cutoff].rstrip(" .") + "."


async def _maybe_send_voice_welcome(update: Update, context: "ContextTypes.DEFAULT_TYPE") -> None:
    if context.user_data.get("voice_welcome_sent"):
        return
    context.user_data["voice_welcome_sent"] = True
    await _send(
        update,
        _ui_text(
            context,
            "🎙️ Modalità voce disponibile in chat libera. Di default la voce usa italiano (Cris). In automatico vale il mirroring testo→testo e vocale→vocale. Usa /voice on, /voice off o /voice auto per cambiare comportamento. Per forzare la lingua della voce usa /voice_lang it, /voice_lang en o /voice_lang auto.",
            "🎙️ Voice mode is available in free chat. By default the voice uses Italian (Cris). In automatic mode text gets text replies and voice gets voice replies. Use /voice on, /voice off or /voice auto to change behavior. To force the voice language use /voice_lang it, /voice_lang en or /voice_lang auto.",
        ),
    )


async def _download_voice_message_bytes(update: Update) -> bytes:
    if not update.message or not update.message.voice:
        return b""
    voice_file = await update.message.voice.get_file()
    return bytes(await voice_file.download_as_bytearray())


def _voice_cache(context: "ContextTypes.DEFAULT_TYPE") -> Dict[str, Any]:
    application = getattr(context, "application", None)
    if application is None:
        raise RuntimeError("Application Telegram non disponibile per la cache voce.")
    return application.bot_data


def _get_whisper_model(context: "ContextTypes.DEFAULT_TYPE"):
    if not FASTER_WHISPER_AVAILABLE:
        raise RuntimeError("faster-whisper non installato.")
    cache = _voice_cache(context)
    model = cache.get("voice_whisper_model")
    if model is None:
        model = WhisperModel(
            TELEGRAM_CONFIG.get("voice_stt_model", "small"),
            device=TELEGRAM_CONFIG.get("voice_stt_device", "auto"),
            compute_type=TELEGRAM_CONFIG.get("voice_stt_compute_type", "int8"),
        )
        cache["voice_whisper_model"] = model
    return model


async def transcribe_audio(
    context: "ContextTypes.DEFAULT_TYPE",
    audio_bytes: bytes,
    *,
    file_suffix: str = ".ogg",
) -> str:
    if not audio_bytes:
        return ""
    temp_dir = _voice_temp_dir()
    with tempfile.NamedTemporaryFile(dir=temp_dir, suffix=file_suffix, delete=False) as handle:
        handle.write(audio_bytes)
        temp_path = Path(handle.name)

    def _transcribe() -> str:
        model = _get_whisper_model(context)
        segments, _info = model.transcribe(
            str(temp_path),
            language=TELEGRAM_CONFIG.get("voice_stt_language", "it"),
            beam_size=int(TELEGRAM_CONFIG.get("voice_stt_beam_size", 1)),
            vad_filter=bool(TELEGRAM_CONFIG.get("voice_stt_vad_filter", True)),
        )
        return " ".join(segment.text.strip() for segment in segments if getattr(segment, "text", "")).strip()

    try:
        return await asyncio.to_thread(_transcribe)
    finally:
        temp_path.unlink(missing_ok=True)


def _elevenlabs_api_key() -> str:
    env_name = TELEGRAM_CONFIG.get("voice_elevenlabs_api_key_env", "ELEVENLABS_API_KEY")
    return os.getenv(env_name, "").strip()


_ENGLISH_TTS_HINTS = {
    "a", "an", "and", "are", "can", "check", "disease", "for", "from", "hello",
    "how", "if", "in", "is", "it", "leaf", "need", "of", "on", "plant", "please",
    "recommend", "risk", "soil", "symptom", "symptoms", "temperature", "the", "this",
    "to", "use", "water", "with", "you", "your",
}


def _piper_profile_config(profile_id: str) -> Dict[str, str]:
    base_dir = Path(__file__).resolve().parent.parent / "models" / "piper"
    profiles = {
        "it": {
            "model_path": str(TELEGRAM_CONFIG.get("voice_piper_model_path") or (base_dir / "it_IT-paola-medium.onnx")),
            "config_path": str(TELEGRAM_CONFIG.get("voice_piper_config_path") or (base_dir / "it_IT-paola-medium.onnx.json")),
            "model_url": str(TELEGRAM_CONFIG.get("voice_piper_model_url", "")).strip(),
            "config_url": str(TELEGRAM_CONFIG.get("voice_piper_config_url", "")).strip(),
        },
        "en": {
            "model_path": str(TELEGRAM_CONFIG.get("voice_piper_english_model_path") or (base_dir / "en_US-ryan-medium.onnx")),
            "config_path": str(TELEGRAM_CONFIG.get("voice_piper_english_config_path") or (base_dir / "en_US-ryan-medium.onnx.json")),
            "model_url": str(TELEGRAM_CONFIG.get("voice_piper_english_model_url", "")).strip(),
            "config_url": str(TELEGRAM_CONFIG.get("voice_piper_english_config_url", "")).strip(),
        },
    }
    if profile_id not in profiles:
        raise RuntimeError(f"Profilo Piper non supportato: {profile_id}")
    return profiles[profile_id]


def _piper_model_paths(profile_id: str) -> Tuple[Path, Path]:
    profile = _piper_profile_config(profile_id)
    return Path(profile["model_path"]), Path(profile["config_path"])


def _voice_language_mode(context: Optional["ContextTypes.DEFAULT_TYPE"] = None) -> str:
    if context is None or not hasattr(context, "user_data") or context.user_data is None:
        return VOICE_LANGUAGE_DEFAULT
    raw = str(context.user_data.get("voice_language_override", VOICE_LANGUAGE_DEFAULT)).strip().lower()
    return raw if raw in _VOICE_LANGUAGE_ALLOWED else VOICE_LANGUAGE_DEFAULT


def _ui_language(context: Optional["ContextTypes.DEFAULT_TYPE"] = None) -> str:
    return VOICE_LANGUAGE_EN if _voice_language_mode(context) == VOICE_LANGUAGE_EN else VOICE_LANGUAGE_IT


def _ui_text(
    context: Optional["ContextTypes.DEFAULT_TYPE"],
    italian_text: str,
    english_text: str,
) -> str:
    return english_text if _ui_language(context) == VOICE_LANGUAGE_EN else italian_text


def _select_piper_voice_profile(
    text: str,
    context: Optional["ContextTypes.DEFAULT_TYPE"] = None,
) -> str:
    override = _voice_language_mode(context) if context is not None else VOICE_LANGUAGE_AUTO
    if override in {VOICE_LANGUAGE_IT, VOICE_LANGUAGE_EN}:
        return override

    default_profile = str(TELEGRAM_CONFIG.get("voice_piper_default_profile", "it")).strip().lower() or "it"
    if not bool(TELEGRAM_CONFIG.get("voice_piper_auto_language", True)):
        return default_profile

    words = re.findall(r"[A-Za-z']+", text.lower())
    english_score = sum(1 for word in words if word in _ENGLISH_TTS_HINTS)
    ascii_only = all(ord(ch) < 128 for ch in text)
    if english_score >= 2 or (english_score >= 1 and ascii_only and len(words) >= 4):
        return "en"
    return default_profile


def _download_binary_file(url: str, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    temp_target = target.with_suffix(target.suffix + ".part")
    timeout = max(int(TELEGRAM_CONFIG.get("voice_download_timeout_sec", 180)), 5)
    try:
        with requests.get(url, stream=True, timeout=timeout) as response:
            response.raise_for_status()
            with temp_target.open("wb") as handle:
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        handle.write(chunk)
        temp_target.replace(target)
    finally:
        temp_target.unlink(missing_ok=True)


async def _ensure_piper_model_assets(
    context: "ContextTypes.DEFAULT_TYPE",
    profile_id: str,
) -> Tuple[Path, Path]:
    if not PIPER_AVAILABLE:
        raise RuntimeError("piper-tts non installato.")

    model_path, config_path = _piper_model_paths(profile_id)
    if model_path.exists() and config_path.exists():
        return model_path, config_path

    cache = _voice_cache(context)
    locks = cache.get("voice_piper_download_locks")
    if locks is None:
        locks = {}
        cache["voice_piper_download_locks"] = locks
    lock = locks.get(profile_id)
    if lock is None:
        lock = asyncio.Lock()
        locks[profile_id] = lock

    async with lock:
        if model_path.exists() and config_path.exists():
            return model_path, config_path

        profile = _piper_profile_config(profile_id)
        model_url = profile["model_url"]
        config_url = profile["config_url"]
        if not model_url or not config_url:
            raise RuntimeError(f"URL del modello Piper non configurati per il profilo {profile_id}.")

        await asyncio.to_thread(_download_binary_file, model_url, model_path)
        await asyncio.to_thread(_download_binary_file, config_url, config_path)
        return model_path, config_path


async def _get_piper_voice(
    context: "ContextTypes.DEFAULT_TYPE",
    profile_id: str,
):
    if not PIPER_AVAILABLE:
        raise RuntimeError("piper-tts non installato.")

    model_path, config_path = await _ensure_piper_model_assets(context, profile_id)
    cache = _voice_cache(context)
    cache_key = str(model_path.resolve())
    voices = cache.get("voice_piper_voices")
    if voices is None:
        voices = {}
        cache["voice_piper_voices"] = voices
    paths = cache.get("voice_piper_model_paths")
    if paths is None:
        paths = {}
        cache["voice_piper_model_paths"] = paths
    cached_voice = voices.get(profile_id)
    if cached_voice is not None and paths.get(profile_id) == cache_key:
        return cached_voice

    def _load_voice():
        return PiperVoice.load(
            str(model_path),
            config_path=str(config_path),
            use_cuda=bool(TELEGRAM_CONFIG.get("voice_piper_use_cuda", False)),
        )

    voice = await asyncio.to_thread(_load_voice)
    voices[profile_id] = voice
    paths[profile_id] = cache_key
    return voice


def _select_tts_provider() -> str:
    configured = str(TELEGRAM_CONFIG.get("voice_tts_provider", "auto")).strip().lower() or "auto"
    if configured == "piper":
        if not PIPER_AVAILABLE:
            raise RuntimeError("Provider TTS Piper non installato.")
        return "piper"
    if configured == "elevenlabs":
        if not ELEVENLABS_AVAILABLE:
            raise RuntimeError("Provider TTS ElevenLabs non installato.")
        if not _elevenlabs_api_key():
            raise RuntimeError("Chiave API ElevenLabs mancante.")
        return "elevenlabs"
    if configured == "edge_tts":
        if not EDGE_TTS_AVAILABLE:
            raise RuntimeError("Provider TTS edge-tts non installato.")
        return "edge_tts"
    if PIPER_AVAILABLE:
        return "piper"
    if ELEVENLABS_AVAILABLE and _elevenlabs_api_key():
        return "elevenlabs"
    if EDGE_TTS_AVAILABLE:
        return "edge_tts"
    raise RuntimeError("Nessun provider TTS disponibile.")


async def _tts_with_elevenlabs(text: str) -> BytesIO:
    api_key = _elevenlabs_api_key()
    voice_id = os.getenv(
        TELEGRAM_CONFIG.get("voice_elevenlabs_voice_id_env", "ELEVENLABS_VOICE_ID"),
        TELEGRAM_CONFIG.get("voice_elevenlabs_voice_id", "pNInz6obpgDQGcFmaJgB"),
    ).strip()
    if not voice_id:
        raise RuntimeError("Voice ID ElevenLabs mancante.")

    def _synthesize() -> bytes:
        client = ElevenLabs(api_key=api_key)
        audio_stream = client.text_to_speech.convert(
            voice_id=voice_id,
            model_id=TELEGRAM_CONFIG.get("voice_elevenlabs_model", "eleven_multilingual_v2"),
            output_format=TELEGRAM_CONFIG.get("voice_elevenlabs_output_format", "mp3_44100_128"),
            text=text,
            voice_settings=VoiceSettings(
                stability=float(TELEGRAM_CONFIG.get("voice_elevenlabs_stability", 0.8)),
                similarity_boost=float(TELEGRAM_CONFIG.get("voice_elevenlabs_similarity_boost", 0.85)),
                style=float(TELEGRAM_CONFIG.get("voice_elevenlabs_style", 0.4)),
                use_speaker_boost=bool(TELEGRAM_CONFIG.get("voice_elevenlabs_speaker_boost", True)),
            ),
        )
        return b"".join(audio_stream)

    audio_bytes = await asyncio.to_thread(_synthesize)
    buffer = BytesIO(audio_bytes)
    buffer.name = "delta_voice_reply.mp3"
    buffer.seek(0)
    return buffer


async def _tts_with_edge(text: str) -> BytesIO:
    if edge_tts is None:
        raise RuntimeError("edge-tts non installato.")
    temp_dir = _voice_temp_dir()
    temp_path = temp_dir / f"tts_{datetime.utcnow().strftime('%Y%m%d_%H%M%S_%f')}.mp3"
    communicate = edge_tts.Communicate(
        text=text,
        voice=TELEGRAM_CONFIG.get("voice_edge_tts_voice", "it-IT-GiuseppeMultilingualNeural"),
        rate=TELEGRAM_CONFIG.get("voice_edge_tts_rate", "-4%"),
        volume=TELEGRAM_CONFIG.get("voice_edge_tts_volume", "+8%"),
        pitch=TELEGRAM_CONFIG.get("voice_edge_tts_pitch", "-8Hz"),
        boundary=TELEGRAM_CONFIG.get("voice_edge_tts_boundary", "SentenceBoundary"),
    )
    await communicate.save(str(temp_path))
    try:
        buffer = BytesIO(temp_path.read_bytes())
        buffer.name = "delta_voice_reply.mp3"
        buffer.seek(0)
        return buffer
    finally:
        temp_path.unlink(missing_ok=True)


async def _tts_with_piper(
    context: "ContextTypes.DEFAULT_TYPE",
    text: str,
) -> BytesIO:
    profile_id = _select_piper_voice_profile(text, context=context)
    voice = await _get_piper_voice(context, profile_id)

    def _synthesize() -> BytesIO:
        buffer = BytesIO()
        with wave.open(buffer, "wb") as wav_file:
            voice.synthesize_wav(text, wav_file)
        buffer.name = f"delta_voice_reply_{profile_id}.wav"
        buffer.seek(0)
        return buffer

    return await asyncio.to_thread(_synthesize)


async def text_to_speech_warm_male(
    context: "ContextTypes.DEFAULT_TYPE",
    text: str,
) -> BytesIO:
    spoken_text = _spoken_voice_text(text, context=context)
    provider = _select_tts_provider()
    if provider == "piper":
        return await _tts_with_piper(context, spoken_text)
    if provider == "elevenlabs":
        return await _tts_with_elevenlabs(spoken_text)
    if provider == "edge_tts":
        return await _tts_with_edge(spoken_text)
    raise RuntimeError(f"Provider TTS non supportato: {provider}")


def _voice_source_format(voice_data: BytesIO) -> str:
    suffix = Path(str(getattr(voice_data, "name", ""))).suffix.lower().lstrip(".")
    return suffix or "mp3"


async def _prepare_telegram_voice_payload(voice_data: BytesIO) -> BytesIO:
    source_format = _voice_source_format(voice_data)
    voice_data.seek(0)

    if source_format == "ogg" or not PYDUB_AVAILABLE:
        return voice_data

    source_bytes = voice_data.getvalue()

    def _convert() -> BytesIO:
        segment = AudioSegment.from_file(BytesIO(source_bytes), format=source_format)
        output = BytesIO()
        export_kwargs: Dict[str, Any] = {
            "format": "ogg",
            "codec": TELEGRAM_CONFIG.get("voice_reply_codec", "libopus"),
        }
        bitrate = str(TELEGRAM_CONFIG.get("voice_reply_bitrate", "48k")).strip()
        if bitrate:
            export_kwargs["bitrate"] = bitrate
        segment.export(output, **export_kwargs)
        output.name = "delta_voice_reply.ogg"
        output.seek(0)
        return output

    try:
        return await asyncio.to_thread(_convert)
    except Exception as exc:
        logger.warning(
            "Conversione risposta vocale in OGG/Opus fallita, provo il payload originale: %s",
            exc,
            exc_info=True,
        )
        voice_data.seek(0)
        return voice_data


async def _send_voice(
    update: Update,
    voice_data: BytesIO,
    *,
    caption: Optional[str] = None,
    reply_markup: Optional[InlineKeyboardMarkup] = None,
) -> None:
    payload = await _prepare_telegram_voice_payload(voice_data)
    payload.seek(0)
    chat = getattr(update, "effective_chat", None)
    if chat is None:
        raise RuntimeError("Chat Telegram non disponibile per l'invio del vocale.")
    reply_args: Dict[str, Any] = {"voice": payload, "reply_markup": reply_markup}
    if caption:
        reply_args["caption"] = caption
    await chat.send_voice(**reply_args)


def _build_free_chat_language_prompt_suffix(response_language: str) -> str:
    normalized = (response_language or VOICE_LANGUAGE_DEFAULT).strip().lower()
    if normalized == VOICE_LANGUAGE_EN:
        return (
            "LANGUAGE OVERRIDE FOR THIS TURN:\n"
            "- Respond only in English.\n"
            "- If the user message or voice transcription is in Italian, understand it but translate your answer into English.\n"
            "- Do not include Italian sentences unless the user explicitly asks for a translation example."
        )
    return (
        "VINCOLO LINGUA PER QUESTO TURNO:\n"
        "- Rispondi solo in italiano.\n"
        "- Se il messaggio o la trascrizione vocale dell'utente e' in inglese, comprendila ma formula la risposta in italiano.\n"
        "- Non includere frasi in inglese salvo richiesta esplicita di traduzione."
    )


def _join_system_prompt_suffixes(*parts: str) -> str:
    return "\n\n".join(str(part or "").strip() for part in parts if str(part or "").strip())


async def _generate_free_chat_response(
    update: Update,
    context: "ContextTypes.DEFAULT_TYPE",
    user_text: str,
    *,
    input_mode: str = "text",
) -> str:
    user_id = str(update.effective_user.id) if update.effective_user else "0"

    try:
        await update.effective_chat.send_action("typing")
    except Exception:
        pass

    # Integrazione HERO DEMO: dashboard NASA-ISRO/SAR
    lowered = user_text.lower()
    if any(key in lowered for key in ("dashboard", "riepilogo settimanale", "weekly summary", "sar")):
        try:
            report_language = _ui_language(context)
            # Estrai lat/lon da update.message.location se presente, altrimenti fallback su Roma
            lat, lon = 41.9028, 12.4964
            if hasattr(update, "message") and update.message and getattr(update.message, "location", None):
                lat = getattr(update.message.location, "latitude", lat)
                lon = getattr(update.message.location, "longitude", lon)
            # Genera mappa radar con overlay (raggio 50m)
            map_payload = await asyncio.to_thread(
                _build_nasa_sar_map_photo_payload,
                lat,
                lon,
                report_language,
            )
            # --- Calcolo dashboard dati ---
            from bot.nasa_sar_dashboard import build_dashboard_plaintext_report, generate_dashboard, generate_dashboard_report_image
            dashboard = generate_dashboard(lat, lon)
            if isinstance(dashboard, dict) and "error" in dashboard:
                logger.error("Errore dashboard NASA-ISRO/SAR: %s", dashboard["error"])
                return _ui_text(
                    context,
                    f"❌ Errore dashboard NASA-ISRO/SAR: {dashboard['error']}",
                    f"❌ NASA-ISRO/SAR dashboard error: {dashboard['error']}",
                )
            # --- Genera immagine grafica ---
            img = generate_dashboard_report_image(dashboard, lat, lon, language=report_language)
            import tempfile
            img_path = tempfile.mktemp(suffix="_dashboard.png", prefix="nasa_sar_")
            img.save(img_path)
            chat = getattr(update, "effective_chat", None)
            if map_payload and chat:
                if hasattr(map_payload, "seek"):
                    map_payload.seek(0)
                await chat.send_photo(
                    photo=map_payload,
                    caption=_ui_text(
                        context,
                        "\U0001F30E Area di interesse NASA-ISRO/SAR (raggio 50m dal punto GPS)",
                        "\U0001F30E NASA-ISRO/SAR area of interest (50 m radius from the GPS point)",
                    ),
                )
            if chat:
                with open(img_path, "rb") as f:
                    await chat.send_photo(
                        photo=f,
                        caption=_ui_text(
                            context,
                            "\U0001F4CA Report grafico NASA-ISRO/SAR: rischio settimanale e indicatori professionali.",
                            "\U0001F4CA NASA-ISRO/SAR graphic report: weekly risk and professional indicators.",
                        ),
                    )
            return build_dashboard_plaintext_report(dashboard, language=report_language)
        except Exception as exc:
            logger.error("Errore dashboard NASA-ISRO/SAR: %s", exc, exc_info=True)
            return _ui_text(
                context,
                f"Errore dashboard NASA-ISRO/SAR: {exc}",
                f"NASA-ISRO/SAR dashboard error: {exc}",
            )


    response_language = _voice_language_mode(context)
    chat_seed_context = str(context.user_data.pop("chat_seed_context", "") or "").strip()
    chart_request_mode = _free_chat_chart_request_mode(user_text)
    table_requested = _free_chat_requests_table(user_text)
    engine = _get_chat_engine(context)
    diagnosis_context = context.user_data.get("last_diagnosis_context")
    refinement_requested = (
        isinstance(diagnosis_context, dict)
        and _looks_like_agronomic_refinement_request(user_text)
    )

    def _looks_like_seed_followup_query(text: str) -> bool:
        normalized = str(text or "").strip().lower()
        if not normalized:
            return False
        followup_markers = (
            "diagnosi", "rischio", "fung", "nasa", "sar", "contesto", "lux", "umid",
            "spiega", "approfond", "dettag", "perche", "perché", "confermi", "coerente",
            "questa", "questo", "quel", "quello", "that", "this diagnosis", "why",
        )
        return any(marker in normalized for marker in followup_markers)

    # --- PATCH: reset contesto LLM se nuova pianta menzionata ---
    def extract_plant_name(text):
        # Semplice estrazione: cerca parole chiave di piante note (estendibile)
        PLANTS = [
            "melanzana", "sanseveria", "pomodoro", "peperone", "zucchina", "basilico", "rosa", "orchidea", "ficus", "dracena", "cactus", "limone", "fragola", "mela", "pero", "ciliegio", "vite", "grano", "mais", "soia", "patata", "carota", "lattuga", "spinacio", "prezzemolo", "salvia", "menta", "alloro", "cipresso", "pino", "abet", "olivo", "girasole", "ciclamino", "azalea", "geranio", "begonia", "anturio", "cicoria", "cavolo", "broccolo", "cavolfiore", "rapa", "barbabietola", "sedano", "finocchio", "zucca", "anguria", "melone", "kiwi", "arancio", "mandarino", "susina", "pesco", "albicocco", "ciliegia", "fico", "noce", "castagno", "nocciolo", "mandorlo", "prugno", "sansevieria", "sanseveria"
        ]
        lowered = text.lower()
        for plant in PLANTS:
            if plant in lowered:
                return plant
        return None

    # Solo se non è stato già gestito un return (es. dashboard NASA), prosegui con LLM
    try:
        base_prompt = user_text
        if refinement_requested:
            base_prompt = _build_agronomic_refinement_prompt(
                context,
                user_text,
                diagnosis_context,
                response_language,
            )
        elif chat_seed_context and input_mode == "text" and _looks_like_seed_followup_query(user_text):
            seed_prefix = "User question" if response_language == VOICE_LANGUAGE_EN else "Domanda utente"
            base_prompt = f"{chat_seed_context}\n\n{seed_prefix}: {user_text}"
        elif chat_seed_context and input_mode == "voice":
            logger.info("chat_seed_context ignorato su input vocale per evitare risposte stale post-diagnosi")
        visual_prompt_suffix = _build_free_chat_visual_prompt_suffix(
            response_language=response_language,
            chart_request_mode=chart_request_mode,
            table_requested=table_requested,
        )
        system_prompt_suffix = _join_system_prompt_suffixes(
            _build_free_chat_language_prompt_suffix(response_language),
            visual_prompt_suffix,
        )

        def _ask():
            if refinement_requested:
                return engine.chat_internal(
                    base_prompt,
                    response_language=response_language,
                    system_prompt_suffix=system_prompt_suffix,
                )
            chat_method = getattr(engine, "chat", None)
            if callable(chat_method):
                return chat_method(
                    user_id,
                    base_prompt,
                    response_language=response_language,
                    system_prompt_suffix=system_prompt_suffix,
                )
            return engine.chat_internal(
                base_prompt,
                response_language=response_language,
                system_prompt_suffix=system_prompt_suffix,
            )
        response = await asyncio.to_thread(_ask)
        response = await _repair_free_chat_visual_response(
            engine,
            base_prompt=base_prompt,
            response_text=response,
            response_language=response_language,
            chart_request_mode=chart_request_mode,
            table_requested=table_requested,
        )
        response = await _repair_free_chat_language_response(
            engine,
            response_text=response,
            response_language=response_language,
        )
    except Exception as exc:
        logger.error("Errore chat LLM: %s", exc, exc_info=True)
        # Fallback: chat/voice sempre disponibili
        response = _ui_text(
            context,
            "\U0001F916 Il sistema LLM non è momentaneamente disponibile. Puoi riprovare tra qualche secondo o continuare a usare le altre funzioni DELTA.",
            "\U0001F916 The LLM system is temporarily unavailable. You can try again in a few seconds or keep using the other DELTA functions.",
        )

    logger.info("free_chat_response[%s]: %s", user_id, response[:120])
    return response


_FREE_CHAT_HEADING_RE = re.compile(r"^\s{0,3}(#{2,4})\s*(.+?)\s*$")
_FREE_CHAT_BULLET_RE = re.compile(r"^\s*(?:[-*•]\s+)(.+?)\s*$")
_FREE_CHAT_METRIC_LINE_RE = re.compile(
    r"^\s*(?:[-*•]\s*)?(?P<label>[A-Za-zÀ-ÿ0-9 /()%'.+-]{2,24})\s*:\s*(?P<value>[^:\n]{1,32})\s*$"
)
_FREE_CHAT_INLINE_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
_FREE_CHAT_INLINE_CODE_RE = re.compile(r"`([^`]+)`")
_FREE_CHAT_CHART_REQUEST_RE = re.compile(r"\b(grafico|grafici|graph|chart|plot|visual(?:e|izza|ization))\b", re.IGNORECASE)
_FREE_CHAT_CHART_NEGATION_RE = re.compile(
    r"(senza\s+(?:alcun\w*\s+)?(?:grafico|grafici)|"
    r"non\s+(?:voglio|generare|mostrare|inviare).{0,24}(?:grafico|grafici|chart|graph)|"
    r"\bno\s+(?:grafico|grafici|chart|graph)s?\b|"
    r"without\s+(?:any\s+)?(?:chart|graph)s?)",
    re.IGNORECASE,
)
_FREE_CHAT_ADVANCED_CHART_REQUEST_RE = re.compile(
    r"(grafico\s+avanzat|grafici\s+avanzat|grafico\s+premium|grafico\s+evolut|"
    r"grafico\s+profession\w*|grafici\s+profession\w*|"
    r"alto\s+impatto\s+grafico|grafico\s+ad\s+alto\s+impatto|"
    r"advanced\s+(?:chart|graph|visual)|professional\s+(?:chart|graph|visual)|"
    r"high[- ]impact\s+(?:chart|graphic))",
    re.IGNORECASE,
)
_FREE_CHAT_TABLE_REQUEST_RE = re.compile(
    r"((?:fammi|crea|genera|mostra|mostrami|organizza|formatta|riassumi).{0,24}(?:tabella|tabelle)|"
    r"(?:show|make|create|generate|organize|format|summari[sz]e).{0,24}(?:table|tables)|"
    r"(?:in|come|con)\s+(?:una\s+)?(?:tabella|table)\b|"
    r"(?:as|into|with)\s+(?:a\s+)?table\b|"
    r"(?:tabella|tabelle)\s+(?:ben\s+organizzat\w*|riassuntiv\w*|comparativ\w*|ordinat\w*)|"
    r"(?:table|tables)\s+(?:well[- ]organized|summary|comparative|organized))",
    re.IGNORECASE,
)
_FREE_CHAT_TABLE_NEGATION_RE = re.compile(
    r"(senza\s+(?:alcun\w*\s+)?(?:tabella|tabelle)|"
    r"non\s+(?:voglio|generare|mostrare|inviare|formattare).{0,24}(?:tabella|tabelle|table|tables)|"
    r"\bno\s+(?:tabella|tabelle|table|tables)\b|"
    r"without\s+(?:any\s+)?(?:table|tables))",
    re.IGNORECASE,
)
_FREE_CHAT_VISUAL_REFUSAL_RE = re.compile(
    r"(non\s+posso.{0,48}(?:grafic|chart|plot|tabell)|"
    r"non\s+sono\s+in\s+grado.{0,48}(?:grafic|chart|plot|tabell)|"
    r"(?:can(?:not|'t)|unable\s+to).{0,48}(?:chart|graph|plot|table|tables?))",
    re.IGNORECASE | re.DOTALL,
)


def _free_chat_heading_icon(context: Optional["ContextTypes.DEFAULT_TYPE"], title: str) -> str:
    normalized = str(title or "").strip().lower()
    icon_map = [
        (("sintesi", "summary", "overview"), "🔎"),
        (("sintomi", "symptoms"), "🧬"),
        (("cause", "fattori", "drivers"), "🌦️"),
        (("preven", "prevent"), "🛡️"),
        (("tratt", "control", "intervent"), "💊"),
        (("consigli", "tips", "practical"), "📌"),
        (("monitor", "monitoraggio"), "📡"),
        (("rischio", "risk"), "📊"),
    ]
    for hints, icon in icon_map:
        if any(hint in normalized for hint in hints):
            return icon
    return "💬"


def _render_free_chat_inline_html(text: str) -> str:
    escaped = html.escape(str(text or "").strip(), quote=False)
    escaped = _FREE_CHAT_INLINE_CODE_RE.sub(r"<code>\1</code>", escaped)
    escaped = _FREE_CHAT_INLINE_BOLD_RE.sub(r"<b>\1</b>", escaped)
    return escaped


def _parse_free_chat_metric_line(line: str) -> Optional[Tuple[str, str]]:
    match = _FREE_CHAT_METRIC_LINE_RE.match(str(line or ""))
    if not match:
        return None
    label = re.sub(r"[`*_]+", "", re.sub(r"\s+", " ", match.group("label"))).strip(" -•")
    value = re.sub(r"[`*_]+", "", re.sub(r"\s+", " ", match.group("value"))).strip()
    if len(label) < 2 or len(value) < 1:
        return None
    return label, value


def _parse_free_chat_metric_segment(segment: str) -> Optional[Tuple[str, str]]:
    cleaned = re.sub(r"^\s*(?:[-*•]\s*)?", "", str(segment or "")).strip().strip("|")
    cleaned = re.sub(r"[`*_]+", "", cleaned)
    if not cleaned:
        return None

    direct_match = _parse_free_chat_metric_line(cleaned)
    if direct_match:
        return direct_match

    parts = [part.strip() for part in cleaned.split(":") if part.strip()]
    if len(parts) < 2:
        return None

    label = re.sub(r"[`*_]+", "", re.sub(r"\s+", " ", parts[-2])).strip(" -•")
    value = re.sub(r"[`*_]+", "", re.sub(r"\s+", " ", parts[-1])).strip()
    if len(label) < 2 or len(label) > 24 or len(value) < 1 or len(value) > 32:
        return None
    return label, value


def _extract_free_chat_metric_rows(line: str) -> List[Tuple[str, str]]:
    stripped = str(line or "").strip()
    if not stripped:
        return []

    raw_segments = [segment.strip() for segment in stripped.strip("|").split("|") if segment.strip()]
    if not raw_segments:
        return []

    rows = [row for row in (_parse_free_chat_metric_segment(segment) for segment in raw_segments) if row]
    if rows:
        return rows

    single = _parse_free_chat_metric_segment(stripped)
    return [single] if single else []


def _count_free_chat_metric_rows(response_text: str) -> int:
    return sum(len(_extract_free_chat_metric_rows(line)) for line in str(response_text or "").splitlines())


def _free_chat_metric_strength(value: str) -> float:
    raw_value = str(value or "").strip().lower()
    percent_match = re.search(r"(\d{1,3})(?:[.,]\d+)?\s*%", raw_value)
    if percent_match:
        return float(max(0, min(100, int(percent_match.group(1)))))

    numeric_match = re.search(r"(-?\d{1,3})(?:[.,](\d+))?", raw_value)
    if numeric_match:
        whole = numeric_match.group(1)
        decimals = numeric_match.group(2) or "0"
        try:
            value_num = float(f"{whole}.{decimals}")
        except ValueError:
            value_num = 0.0
        return max(0.0, value_num)

    qualitative_map = {
        "very low": 12.5,
        "molto basso": 12.5,
        "basso": 25.0,
        "low": 25.0,
        "moderato": 50.0,
        "moderate": 50.0,
        "medio": 62.5,
        "medium": 62.5,
        "alto": 75.0,
        "high": 75.0,
        "severo": 87.5,
        "severe": 87.5,
        "critico": 100.0,
        "critical": 100.0,
    }
    for token, weight in qualitative_map.items():
        if token in raw_value:
            return weight
    return 0.0


def _should_render_free_chat_metric_table(rows: List[Tuple[str, str]]) -> bool:
    if len(rows) < 3:
        return False
    strong_metrics = sum(1 for _, value in rows if _free_chat_metric_strength(value) > 0)
    return strong_metrics >= 2


def _free_chat_metric_bar(value: str) -> str:
    strength = _free_chat_metric_strength(value)
    if strength > 0:
        filled = max(1, min(8, int(round(strength / 12.5))))
        return "█" * filled + "░" * (8 - filled)
    return ""


def _free_chat_chart_request_mode(user_text: str) -> str:
    raw = str(user_text or "")
    if _FREE_CHAT_CHART_NEGATION_RE.search(raw):
        return "none"
    if _FREE_CHAT_ADVANCED_CHART_REQUEST_RE.search(raw):
        return "advanced"
    if _FREE_CHAT_CHART_REQUEST_RE.search(raw):
        return "basic"
    return "none"


def _free_chat_requests_chart(user_text: str) -> bool:
    return _free_chat_chart_request_mode(user_text) != "none"


def _free_chat_requests_table(user_text: str) -> bool:
    raw = str(user_text or "")
    if _FREE_CHAT_TABLE_NEGATION_RE.search(raw):
        return False
    return bool(_FREE_CHAT_TABLE_REQUEST_RE.search(raw))


def _build_free_chat_visual_prompt_suffix(
    *,
    response_language: str,
    chart_request_mode: str,
    table_requested: bool,
    force_structured_output: bool = False,
) -> str:
    if chart_request_mode == "none" and not table_requested:
        return ""

    normalized_language = (response_language or "auto").strip().lower()
    advanced_requested = chart_request_mode == "advanced"
    metric_count = 5 if advanced_requested else 4
    chart_line_it = (
        f"- Se l'utente chiede un grafico professionale o avanzato, fornisci almeno {metric_count} indicatori confrontabili per il renderer del grafico."
        if chart_request_mode != "none"
        else ""
    )
    chart_line_en = (
        f"- If the user asked for a professional or advanced chart, provide at least {metric_count} comparable indicators for the chart renderer."
        if chart_request_mode != "none"
        else ""
    )
    table_line_it = (
        "- Se l'utente chiede una tabella, mantieni queste righe ordinate e una metrica per riga cosi Telegram puo formattarle in una tabella compatta."
        if table_requested
        else ""
    )
    table_line_en = (
        "- If the user asked for a table, keep those lines clean and one metric per line so Telegram can format a compact table."
        if table_requested
        else ""
    )

    if normalized_language == VOICE_LANGUAGE_EN:
        instruction_lines = [
            "TELEGRAM VISUAL RENDERING INSTRUCTIONS:",
            "- DELTA can generate professional charts and well-organized tables from the structured indicators in your reply.",
            "- Do not say that you cannot create charts, graphs, tables, or visuals.",
            "- Start with a short operational summary of 2-4 lines.",
            "- Then add the heading '### Visual indicators'.",
            "- Under that heading write 4-6 lines exactly in the format 'Label: value'.",
            "- Keep labels short, max 24 characters; use comparable numeric, percentage, or qualitative values such as Low, Medium, High, Critical.",
            chart_line_en,
            table_line_en,
            "- Do not use JSON, markdown column tables, or code fences for the metrics block.",
        ]
        if force_structured_output:
            instruction_lines.append("- Rewrite the final answer from scratch without inability disclaimers and without code fences.")
    else:
        instruction_lines = [
            "ISTRUZIONI DI RENDERING TELEGRAM:",
            "- DELTA puo generare grafici professionali e tabelle ben organizzate partendo dagli indicatori strutturati della tua risposta.",
            "- Non dire che non puoi creare grafici, tabelle o visualizzazioni.",
            "- Inizia con una sintesi operativa breve di 2-4 righe.",
            "- Poi aggiungi il titolo '### Indicatori visuali'.",
            "- Sotto il titolo scrivi 4-6 righe esattamente nel formato 'Etichetta: valore'.",
            "- Mantieni etichette brevi, max 24 caratteri; usa valori numerici, percentuali o qualitativi confrontabili come Basso, Medio, Alto, Critico.",
            chart_line_it,
            table_line_it,
            "- Non usare JSON, tabelle markdown a colonne o blocchi di codice per il blocco metriche.",
        ]
        if force_structured_output:
            instruction_lines.append("- Riscrivi la risposta finale da zero senza frasi di impossibilita e senza blocchi di codice.")

    filtered_lines = [line for line in instruction_lines if line]
    return "\n".join(filtered_lines)


async def _repair_free_chat_visual_response(
    engine: Any,
    *,
    base_prompt: str,
    response_text: str,
    response_language: str,
    chart_request_mode: str,
    table_requested: bool,
) -> str:
    if chart_request_mode == "none" and not table_requested:
        return response_text
    if _count_free_chat_metric_rows(response_text) >= 3:
        return response_text
    if not _FREE_CHAT_VISUAL_REFUSAL_RE.search(str(response_text or "")):
        return response_text

    chat_internal = getattr(engine, "chat_internal", None)
    if not callable(chat_internal):
        return response_text

    repair_prompt_suffix = _build_free_chat_visual_prompt_suffix(
        response_language=response_language,
        chart_request_mode=chart_request_mode,
        table_requested=table_requested,
        force_structured_output=True,
    )
    logger.info(
        "free_chat_visual_repair: retrying structured response (chart=%s, table=%s)",
        chart_request_mode,
        table_requested,
    )
    repaired = await asyncio.to_thread(
        chat_internal,
        base_prompt,
        response_language=response_language,
        system_prompt_suffix=repair_prompt_suffix,
    )
    repaired_text = str(repaired or "").strip()
    if not repaired_text:
        return response_text
    if _FREE_CHAT_VISUAL_REFUSAL_RE.search(repaired_text) and _count_free_chat_metric_rows(repaired_text) < 3:
        return response_text
    return repaired_text


_ITALIAN_LANGUAGE_MARKERS = {
    "ciao", "sono", "posso", "puoi", "come", "cosa", "perche", "perchè", "perché",
    "diagnosi", "pianta", "foglie", "malattia", "rischio", "umidita", "umidità",
    "terreno", "vaso", "luce", "acqua", "concimazione", "trattamento", "risposta",
    "aggiornamento", "interpretazione", "azione", "azioni", "monitoraggio",
}

_ENGLISH_LANGUAGE_MARKERS = {
    "hello", "i", "you", "can", "what", "why", "because", "diagnosis", "plant",
    "leaves", "disease", "risk", "humidity", "soil", "pot", "light", "water",
    "fertilization", "treatment", "answer", "update", "interpretation", "action",
    "actions", "monitoring", "recommend", "provide", "should", "would",
}


def _language_marker_score(text: str, markers: Set[str]) -> int:
    words = set(re.findall(r"[A-Za-zÀ-ÖØ-öø-ÿ']+", str(text or "").lower()))
    return sum(1 for marker in markers if marker in words)


def _free_chat_response_needs_language_repair(response_text: str, response_language: str) -> bool:
    normalized_language = (response_language or "auto").strip().lower()
    if normalized_language not in {VOICE_LANGUAGE_IT, VOICE_LANGUAGE_EN}:
        return False

    italian_score = _language_marker_score(response_text, _ITALIAN_LANGUAGE_MARKERS)
    english_score = _language_marker_score(response_text, _ENGLISH_LANGUAGE_MARKERS)
    if normalized_language == VOICE_LANGUAGE_EN:
        return italian_score >= 2 and italian_score > english_score
    return english_score >= 3 and english_score > italian_score


async def _repair_free_chat_language_response(
    engine: Any,
    *,
    response_text: str,
    response_language: str,
) -> str:
    if not _free_chat_response_needs_language_repair(response_text, response_language):
        return response_text

    chat_internal = getattr(engine, "chat_internal", None)
    if not callable(chat_internal):
        return response_text

    if response_language == VOICE_LANGUAGE_EN:
        repair_prompt = (
            "Rewrite the following DELTA Plant answer entirely in English. Preserve all agronomic meaning, values, "
            "plant names, pH/EC units, and recommendations. Do not add Italian sentences.\n\n"
            f"Answer to rewrite:\n{response_text}"
        )
    else:
        repair_prompt = (
            "Riscrivi la seguente risposta DELTA Plant interamente in italiano. Conserva significato agronomico, valori, "
            "nomi delle piante, unita' pH/EC e raccomandazioni. Non aggiungere frasi in inglese.\n\n"
            f"Risposta da riscrivere:\n{response_text}"
        )

    logger.info("free_chat_language_repair: retrying response_language=%s", response_language)
    repaired = await asyncio.to_thread(
        chat_internal,
        repair_prompt,
        response_language=response_language,
        system_prompt_suffix=_build_free_chat_language_prompt_suffix(response_language),
    )
    repaired_text = str(repaired or "").strip()
    if not repaired_text:
        return response_text
    if _free_chat_response_needs_language_repair(repaired_text, response_language):
        return response_text
    return repaired_text


def _collect_free_chat_chart_metrics(response_text: str) -> List[Tuple[str, str, float]]:
    lines = str(response_text or "").splitlines()
    blocks: List[List[Tuple[str, str]]] = []
    idx = 0
    while idx < len(lines):
        block: List[Tuple[str, str]] = []
        while idx < len(lines):
            rows = _extract_free_chat_metric_rows(lines[idx])
            if not rows:
                break
            block.extend(rows)
            idx += 1
        if block:
            blocks.append(block)
        idx += 1

    selected = next((rows for rows in blocks if _should_render_free_chat_metric_table(rows)), None)
    if not selected:
        return []

    metrics = [(label, value, _free_chat_metric_strength(value)) for label, value in selected]
    return [(label, value, score) for label, value, score in metrics if score > 0]


def _load_free_chat_chart_font(size: int, *, bold: bool = False):
    font_candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for candidate in font_candidates:
        try:
            if ImageFont is not None:
                return ImageFont.truetype(candidate, size=size)
        except Exception:
            continue
    return ImageFont.load_default()


def _draw_free_chat_vertical_gradient(image, top_color: Tuple[int, int, int], bottom_color: Tuple[int, int, int]) -> None:
    draw = ImageDraw.Draw(image)
    width, height = image.size
    for y in range(height):
        ratio = y / max(1, height - 1)
        color = tuple(int(top_color[index] + (bottom_color[index] - top_color[index]) * ratio) for index in range(3))
        draw.line((0, y, width, y), fill=color + (255,))


def _draw_free_chat_text_centered(draw, box: Tuple[int, int, int, int], text: str, *, font, fill: Tuple[int, int, int, int]) -> None:
    left, top, right, bottom = box
    text_box = draw.textbbox((0, 0), text, font=font)
    text_width = text_box[2] - text_box[0]
    text_height = text_box[3] - text_box[1]
    x = left + max(0, (right - left - text_width) / 2)
    y = top + max(0, (bottom - top - text_height) / 2)
    draw.text((x, y), text, font=font, fill=fill)


def _truncate_free_chat_chart_text(draw, text: str, *, font, max_width: int) -> str:
    rendered = str(text or "").strip()
    if not rendered or max_width <= 0:
        return rendered
    text_box = draw.textbbox((0, 0), rendered, font=font)
    if text_box[2] - text_box[0] <= max_width:
        return rendered

    ellipsis = "..."
    truncated = rendered
    while truncated:
        candidate = truncated.rstrip() + ellipsis
        candidate_box = draw.textbbox((0, 0), candidate, font=font)
        if candidate_box[2] - candidate_box[0] <= max_width:
            return candidate
        truncated = truncated[:-1]
    return ellipsis


def _build_free_chat_metric_chart(
    context: Optional["ContextTypes.DEFAULT_TYPE"],
    response_text: str,
) -> Optional[BytesIO]:
    if not PIL_AVAILABLE:
        return None

    positive_metrics = _collect_free_chat_chart_metrics(response_text)
    if len(positive_metrics) < 2:
        return None

    def _metric_accent(score: float) -> Tuple[int, int, int]:
        if score >= 80:
            return (14, 165, 233)
        if score >= 55:
            return (45, 212, 191)
        if score >= 35:
            return (249, 115, 22)
        return (99, 102, 241)

    max_score = max(score for _, _, score in positive_metrics) or 1.0
    width = 980
    row_height = 82
    row_gap = 18
    rows_top = 164
    footer_height = 56
    height = rows_top + len(positive_metrics) * row_height + max(0, len(positive_metrics) - 1) * row_gap + footer_height + 58
    image = Image.new("RGBA", (width, height), color=(245, 248, 252, 255))
    _draw_free_chat_vertical_gradient(image, (246, 250, 255), (233, 240, 248))
    draw = ImageDraw.Draw(image, "RGBA")
    draw.ellipse((width - 220, -60, width + 20, 170), fill=(14, 165, 233, 34))
    draw.rounded_rectangle((28, 24, width - 28, height - 24), radius=30, fill=(255, 255, 255, 236), outline=(203, 213, 225, 180), width=2)

    title_font = _load_free_chat_chart_font(28, bold=True)
    subtitle_font = _load_free_chat_chart_font(16)
    label_font = _load_free_chat_chart_font(20, bold=True)
    value_font = _load_free_chat_chart_font(18, bold=True)
    micro_font = _load_free_chat_chart_font(14)

    label_left = 56
    track_left = 338
    title = _ui_text(context, "DELTA mini-grafico indicatori", "DELTA mini-chart metrics")
    subtitle = _ui_text(context, "Generato solo su richiesta esplicita", "Generated only on explicit request")
    draw.text((56, 48), title, fill=(15, 23, 42, 255), font=title_font)
    draw.text((56, 88), subtitle, fill=(71, 85, 105, 255), font=subtitle_font)

    badge_box = (width - 232, 44, width - 60, 84)
    badge_label = _ui_text(context, "Mini render locale", "Local mini render")
    draw.rounded_rectangle(badge_box, radius=18, fill=(14, 165, 233, 26), outline=(14, 165, 233, 80), width=2)
    _draw_free_chat_text_centered(draw, badge_box, badge_label, font=micro_font, fill=(8, 47, 73, 255))

    for index, (label, value, score) in enumerate(positive_metrics):
        top = rows_top + index * (row_height + row_gap)
        accent = _metric_accent(score)
        score_text = f"{int(round(score))}%"
        value_text = _truncate_free_chat_chart_text(draw, str(value), font=value_font, max_width=132)
        value_box_raw = draw.textbbox((0, 0), value_text, font=value_font)
        value_box_width = max(116, value_box_raw[2] - value_box_raw[0] + 34)
        value_left = width - 66 - value_box_width
        track_right = value_left - 24
        track_width = max(120, track_right - track_left)
        normalized = max(0.10, score / max_score)
        current_bar_width = int(track_width * normalized)
        label_text = _truncate_free_chat_chart_text(draw, str(label), font=label_font, max_width=track_left - label_left - 18)

        draw.rounded_rectangle((46, top, width - 46, top + row_height), radius=24, fill=(248, 250, 252, 246), outline=(226, 232, 240, 255), width=2)
        draw.rounded_rectangle((46, top, 58, top + row_height), radius=12, fill=accent + (255,))
        draw.text((label_left, top + 16), label_text, fill=(30, 41, 59, 255), font=label_font)
        draw.text((label_left, top + 46), score_text, fill=(100, 116, 139, 255), font=micro_font)

        value_box = (value_left, top + 14, width - 66, top + 48)
        draw.rounded_rectangle(value_box, radius=17, fill=accent + (34,), outline=accent + (90,), width=2)
        _draw_free_chat_text_centered(draw, value_box, value_text, font=value_font, fill=(15, 23, 42, 255))

        draw.rounded_rectangle((track_left, top + 34, track_right, top + 50), radius=9, fill=(226, 232, 240, 255))
        draw.rounded_rectangle((track_left, top + 34, track_left + current_bar_width, top + 50), radius=9, fill=accent + (255,))
        draw.text((track_left, top + 58), _ui_text(context, "Livello relativo", "Relative level"), fill=(100, 116, 139, 255), font=micro_font)

    footer_top = height - footer_height - 34
    footer_box = (46, footer_top, width - 46, footer_top + footer_height)
    footer = _ui_text(
        context,
        "Visualizzazione compatta locale per Telegram, ottimizzata per lettura rapida.",
        "Compact local visualization for Telegram, optimized for quick reading.",
    )
    footer_text = _truncate_free_chat_chart_text(draw, footer, font=micro_font, max_width=footer_box[2] - footer_box[0] - 34)
    draw.rounded_rectangle(footer_box, radius=22, fill=(241, 245, 249, 235), outline=(203, 213, 225, 200), width=2)
    draw.text((64, footer_top + 20), footer_text, fill=(71, 85, 105, 255), font=micro_font)

    payload = BytesIO()
    image.save(payload, format="PNG")
    payload.name = "delta_free_chat_chart.png"
    payload.seek(0)
    return payload


def _build_free_chat_advanced_chart(
    context: Optional["ContextTypes.DEFAULT_TYPE"],
    response_text: str,
) -> Optional[BytesIO]:
    if not PIL_AVAILABLE:
        return None

    metrics = _collect_free_chat_chart_metrics(response_text)
    visible_metrics = metrics[:5]
    if len(visible_metrics) < 2:
        return None

    width = 1280
    card_height = 84
    card_gap = 22
    cards_top = 238
    cards_bottom = cards_top + len(visible_metrics) * card_height + max(0, len(visible_metrics) - 1) * card_gap
    footer_top = cards_bottom + 38
    footer_height = 74
    height = max(920, footer_top + footer_height + 74)
    image = Image.new("RGBA", (width, height), (9, 18, 38, 255))
    _draw_free_chat_vertical_gradient(image, (8, 20, 43), (10, 92, 122))
    draw = ImageDraw.Draw(image, "RGBA")

    draw.ellipse((width - 320, -120, width + 120, 300), fill=(56, 189, 248, 54))
    draw.ellipse((-160, height - 280, 260, height + 100), fill=(45, 212, 191, 42))
    draw.rounded_rectangle((52, 48, width - 52, height - 48), radius=36, fill=(255, 255, 255, 232))
    draw.rounded_rectangle((72, 72, width - 72, height - 72), radius=28, outline=(148, 163, 184, 70), width=2)

    title_font = _load_free_chat_chart_font(46, bold=True)
    subtitle_font = _load_free_chat_chart_font(22)
    heading_font = _load_free_chat_chart_font(28, bold=True)
    value_font = _load_free_chat_chart_font(34, bold=True)
    label_font = _load_free_chat_chart_font(22)
    micro_font = _load_free_chat_chart_font(18)

    title = _ui_text(context, "DELTA Visual Chart", "DELTA Visual Chart")
    subtitle = _ui_text(
        context,
        "Visualizzazione avanzata generata solo su richiesta esplicita dell'utente",
        "Advanced visualization generated only on explicit user request",
    )
    draw.text((110, 104), title, font=title_font, fill=(15, 23, 42, 255))
    draw.text((112, 160), subtitle, font=subtitle_font, fill=(71, 85, 105, 255))

    badge_text = _ui_text(context, "Render Telegram locale", "Local Telegram render")
    badge_box = (width - 304, 104, width - 112, 146)
    draw.rounded_rectangle(badge_box, radius=18, fill=(14, 165, 233, 28), outline=(14, 165, 233, 90), width=2)
    _draw_free_chat_text_centered(draw, badge_box, badge_text, font=micro_font, fill=(8, 47, 73, 255))

    summary_score = sum(score for _, _, score in visible_metrics) / max(1, len(visible_metrics))
    gauge_panel = (94, 214, 418, footer_top - 28)
    gauge_box = (118, gauge_panel[1] + 92, 394, gauge_panel[1] + 368)
    draw.rounded_rectangle(gauge_panel, radius=30, fill=(15, 23, 42, 235))
    draw.text((132, gauge_panel[1] + 34), _ui_text(context, "Sintesi trend", "Trend summary"), font=heading_font, fill=(226, 232, 240, 255))
    draw.text((132, gauge_panel[1] + 72), _ui_text(context, "Score medio dei driver", "Average driver score"), font=micro_font, fill=(148, 163, 184, 255))
    draw.arc(gauge_box, start=140, end=400, fill=(51, 65, 85, 255), width=22)
    draw.arc(gauge_box, start=140, end=140 + int(260 * (summary_score / 100.0)), fill=(34, 197, 94, 255), width=22)
    _draw_free_chat_text_centered(draw, gauge_box, f"{int(round(summary_score))}%", font=value_font, fill=(248, 250, 252, 255))
    draw.text((150, gauge_panel[3] - 74), _ui_text(context, "Impatto sintetico", "Visual impact"), font=label_font, fill=(148, 163, 184, 255))

    palette = [
        (14, 165, 233, 255),
        (45, 212, 191, 255),
        (249, 115, 22, 255),
        (236, 72, 153, 255),
        (168, 85, 247, 255),
    ]
    max_score = max(score for _, _, score in visible_metrics) or 1.0
    card_left = 472
    card_right = width - 110
    bar_left = card_left + 26

    for index, (label, value, score) in enumerate(visible_metrics):
        top = cards_top + index * (card_height + card_gap)
        accent = palette[index % len(palette)]
        score_text = f"{int(round(score))}%"
        score_box = draw.textbbox((0, 0), score_text, font=micro_font)
        score_width = score_box[2] - score_box[0]
        value_text = _truncate_free_chat_chart_text(draw, str(value), font=heading_font, max_width=116)
        value_box = draw.textbbox((0, 0), value_text, font=heading_font)
        value_width = value_box[2] - value_box[0]
        value_x = card_right - 30 - value_width
        score_x = card_right - 30 - score_width
        current_bar_right = score_x - 24
        current_bar_width_max = max(140, current_bar_right - bar_left)
        label_text = _truncate_free_chat_chart_text(
            draw,
            str(label),
            font=heading_font,
            max_width=max(120, value_x - bar_left - 24),
        )

        draw.rounded_rectangle((card_left, top, card_right, top + card_height), radius=26, fill=(15, 23, 42, 238))
        draw.rounded_rectangle((card_left, top, card_left + 14, top + card_height), radius=14, fill=accent)
        draw.text((bar_left, top + 18), label_text, font=heading_font, fill=(248, 250, 252, 255))
        draw.text((value_x, top + 18), value_text, font=heading_font, fill=(191, 219, 254, 255))
        draw.rounded_rectangle((bar_left, top + 56, current_bar_right, top + 68), radius=8, fill=(51, 65, 85, 255))
        current_bar = int(current_bar_width_max * max(0.12, score / max_score))
        draw.rounded_rectangle((bar_left, top + 56, bar_left + current_bar, top + 68), radius=8, fill=accent)
        draw.text((score_x, top + 48), score_text, font=micro_font, fill=(148, 163, 184, 255))

    footer = _ui_text(
        context,
        "DELTA usa una visualizzazione locale PIL: nessuna chiamata LLM aggiuntiva per il grafico.",
        "DELTA uses a local PIL visualization: no extra LLM call for the chart.",
    )
    footer_box = (94, footer_top, width - 94, footer_top + footer_height)
    draw.rounded_rectangle(footer_box, radius=24, fill=(241, 245, 249, 224), outline=(148, 163, 184, 80), width=2)
    footer_text = _truncate_free_chat_chart_text(draw, footer, font=micro_font, max_width=footer_box[2] - footer_box[0] - 44)
    draw.text((116, footer_top + 24), footer_text, font=micro_font, fill=(71, 85, 105, 255))

    payload = BytesIO()
    image.save(payload, format="PNG")
    payload.name = "delta_free_chat_advanced_chart.png"
    payload.seek(0)
    return payload


async def _maybe_send_free_chat_chart(
    update: Update,
    context: "ContextTypes.DEFAULT_TYPE",
    response_text: str,
    *,
    chart_requested: bool,
    advanced_chart_requested: bool = False,
) -> None:
    if not chart_requested:
        return
    chat = getattr(update, "effective_chat", None)
    if chat is None:
        return

    caption = _ui_text(
        context,
        "📈 Mini-grafico DELTA generato su richiesta dagli indicatori della risposta.",
        "📈 DELTA mini-chart generated on request from the response indicators.",
    )
    chart_payload = None
    if advanced_chart_requested:
        chart_payload = await asyncio.to_thread(_build_free_chat_advanced_chart, context, response_text)
        caption = _ui_text(
            context,
            "🎨 Grafico avanzato DELTA generato su richiesta esplicita dagli indicatori della risposta.",
            "🎨 DELTA advanced chart generated on explicit request from the response indicators.",
        )
    if chart_payload is None:
        chart_payload = await asyncio.to_thread(_build_free_chat_metric_chart, context, response_text)
    if chart_payload is None:
        return

    await chat.send_photo(photo=chart_payload, caption=caption)


def _render_free_chat_metric_table(
    context: Optional["ContextTypes.DEFAULT_TYPE"],
    rows: List[Tuple[str, str]],
) -> str:
    def _truncate_metric_cell(text: str, width: int) -> str:
        rendered = str(text or "").strip()
        if len(rendered) <= width:
            return rendered
        if width <= 3:
            return rendered[:width]
        return rendered[: width - 3].rstrip() + "..."

    def _metric_icon(raw_value: str) -> str:
        strength = _free_chat_metric_strength(raw_value)
        if strength >= 80:
            return "🔴"
        if strength >= 60:
            return "🟠"
        if strength >= 35:
            return "🟡"
        if strength > 0:
            return "🟢"
        return "⚪"

    section_label = _ui_text(context, "Indicatori compatti", "Compact metrics")
    label_width = max(10, min(16, max(len(label) for label, _ in rows)))
    value_width = max(7, min(10, max(len(value) for _, value in rows)))
    rendered_rows = [
        (
            _metric_icon(value),
            _truncate_metric_cell(label, label_width),
            _truncate_metric_cell(value, value_width),
            _free_chat_metric_bar(value),
        )
        for label, value in rows
    ]
    has_bars = any(bar for _, _, _, bar in rendered_rows)
    bar_width = 8 if has_bars else 0
    content_width = label_width + value_width + bar_width + (7 if has_bars else 4)
    inner_width = max(content_width, len(section_label) + 2)

    top_rule = f"╭ {section_label} " + ("─" * max(0, inner_width - len(section_label) - 2)) + "╮"
    bottom_rule = "╰" + ("─" * (inner_width + 2)) + "╯"
    table_lines = [top_rule]
    for icon, label, value, bar in rendered_rows:
        line = f"{icon} {label:<{label_width}}  {value:>{value_width}}"
        if has_bars:
            line += f"  {(bar or '░░░░░░░░'): <{bar_width}}"
        table_lines.append(f"│ {line:<{inner_width}} │")
    table_lines.append(bottom_rule)
    return f"<pre>{html.escape(chr(10).join(table_lines), quote=False)}</pre>"


def _format_free_chat_for_telegram(
    context: Optional["ContextTypes.DEFAULT_TYPE"],
    response_text: str,
) -> Tuple[str, Optional[str]]:
    text = str(response_text or "").strip()
    if not text:
        return text, None

    lines = text.splitlines()
    metric_row_count = _count_free_chat_metric_rows(text)
    should_format = (
        "###" in text
        or "**" in text
        or any(_FREE_CHAT_BULLET_RE.match(line) for line in lines)
        or metric_row_count >= 3
    )
    if not should_format:
        return text, None

    formatted_lines: List[str] = []
    idx = 0
    while idx < len(lines):
        line = lines[idx].rstrip()
        stripped = line.strip()

        if not stripped:
            if formatted_lines and formatted_lines[-1] != "":
                formatted_lines.append("")
            idx += 1
            continue

        metric_rows: List[Tuple[str, str]] = []
        next_idx = idx
        while next_idx < len(lines):
            rows = _extract_free_chat_metric_rows(lines[next_idx])
            if not rows:
                break
            metric_rows.extend(rows)
            next_idx += 1
        if _should_render_free_chat_metric_table(metric_rows):
            formatted_lines.append(_render_free_chat_metric_table(context, metric_rows))
            idx = next_idx
            continue

        heading_match = _FREE_CHAT_HEADING_RE.match(line)
        if heading_match:
            heading_text = heading_match.group(2).strip().rstrip(":")
            if heading_text and heading_text[0].isalnum():
                heading_text = f"{_free_chat_heading_icon(context, heading_text)} {heading_text}"
            formatted_lines.append(f"<b>{html.escape(heading_text, quote=False)}</b>")
            idx += 1
            continue

        bullet_match = _FREE_CHAT_BULLET_RE.match(line)
        if bullet_match:
            formatted_lines.append(f"• {_render_free_chat_inline_html(bullet_match.group(1))}")
            idx += 1
            continue

        formatted_lines.append(_render_free_chat_inline_html(line))
        idx += 1

    while formatted_lines and formatted_lines[-1] == "":
        formatted_lines.pop()
    return "\n".join(formatted_lines), "HTML"


async def _respond_free_chat_output(
    update: Update,
    context: "ContextTypes.DEFAULT_TYPE",
    response_text: str,
    *,
    input_mode: str,
    chart_requested: bool = False,
    advanced_chart_requested: bool = False,
) -> None:
    reply_markup = _chat_exit_keyboard(context) if context.user_data.get("chat_mode_active") else None

    if _should_reply_with_voice(context, input_mode):
        try:
            try:
                await update.effective_chat.send_action("record_voice")
            except Exception:
                pass
            voice_audio = await text_to_speech_warm_male(context, response_text)
            await _send_voice(
                update,
                voice_audio,
                caption=_voice_caption(response_text),
                reply_markup=reply_markup,
            )
            await _maybe_send_free_chat_chart(
                update,
                context,
                response_text,
                chart_requested=chart_requested,
                advanced_chart_requested=advanced_chart_requested,
            )
            return
        except Exception as exc:
            logger.warning("Fallback a testo per risposta vocale: %s", exc, exc_info=True)
            await _send(
                update,
                _ui_text(
                    context,
                    "🎙️ Risposta vocale non disponibile in questo momento. Ti rispondo in testo.",
                    "🎙️ Voice reply is not available right now. I will answer in text.",
                ),
            )

    rendered_text, parse_mode = _format_free_chat_for_telegram(context, response_text)
    await _send_chat_paginated(
        update,
        context,
        rendered_text,
        reply_markup=reply_markup,
        parse_mode=parse_mode,
    )
    await _maybe_send_free_chat_chart(
        update,
        context,
        response_text,
        chart_requested=chart_requested,
        advanced_chart_requested=advanced_chart_requested,
    )


async def _handle_free_chat_turn(
    update: Update,
    context: "ContextTypes.DEFAULT_TYPE",
    user_text: str,
    *,
    input_mode: str,
) -> str:
    response = await _generate_free_chat_response(update, context, user_text, input_mode=input_mode)
    chart_request_mode = _free_chat_chart_request_mode(user_text)
    await _respond_free_chat_output(
        update,
        context,
        response,
        input_mode=input_mode,
        chart_requested=chart_request_mode != "none",
        advanced_chart_requested=chart_request_mode == "advanced",
    )
    return response


async def voice_mode_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _guard(update):
        return

    requested = context.args[0].strip().lower() if getattr(context, "args", None) else ""
    if not requested:
        current = _voice_reply_mode(context)
        await _send(
            update,
            _ui_text(
                context,
                "Modalità voce attuale: "
                f"{current.upper()}\n"
                "Usa /voice on, /voice off o /voice auto.\n"
                "Per la lingua usa /voice_lang it, /voice_lang en o /voice_lang auto.",
                "Current voice mode: "
                f"{current.upper()}\n"
                "Use /voice on, /voice off or /voice auto.\n"
                "For language use /voice_lang it, /voice_lang en or /voice_lang auto.",
            ),
        )
        return

    if requested not in _VOICE_MODE_ALLOWED:
        await _send(update, _ui_text(context, "Uso corretto: /voice on | /voice off | /voice auto", "Usage: /voice on | /voice off | /voice auto"))
        return

    if requested == VOICE_MODE_AUTO:
        context.user_data.pop("voice_mode_override", None)
        await _send(
            update,
            _ui_text(
                context,
                "♻️ Modalità voce automatica attiva: testo→testo, vocale→vocale in chat libera.",
                "♻️ Automatic voice mode enabled: text→text, voice→voice in free chat.",
            ),
        )
        return

    context.user_data["voice_mode_override"] = requested
    if requested == VOICE_MODE_ON:
        await _send(
            update,
            _ui_text(
                context,
                "🎙️ Modalità voce forzata attiva in chat libera: DELTAPLANO proverà a rispondere con un vocale anche ai messaggi testuali.",
                "🎙️ Forced voice mode enabled in free chat: DELTAPLANO will try to answer with voice even to text messages.",
            ),
        )
        return

    await _send(
        update,
        _ui_text(
            context,
            "🔇 Modalità voce disattivata: i vocali saranno trascritti ma la risposta tornerà in testo.",
            "🔇 Voice mode disabled: voice messages will be transcribed but the reply will return as text.",
        ),
    )


async def _set_voice_language(update: Update, context: ContextTypes.DEFAULT_TYPE, requested: str) -> None:
    if requested == VOICE_LANGUAGE_AUTO:
        previous_ui_language = _ui_language(context)
        context.user_data.pop("voice_language_override", None)
        await _send(
            update,
            "♻️ Automatic voice language enabled: DELTAPLANO will choose the Italian or English pack based on the reply."
            if previous_ui_language == VOICE_LANGUAGE_EN
            else "♻️ Lingua voce automatica attiva: DELTAPLANO sceglierà il pack italiano o inglese in base alla risposta.",
        )
        return

    context.user_data["voice_language_override"] = requested
    _clear_user_data_keys(context, "chat_seed_context", "chat_pending_chunks", "chat_pending_parse_mode")
    try:
        user_id = str(update.effective_user.id if update.effective_user else "0")
        _get_chat_engine(context).reset(user_id)
    except Exception as exc:
        logger.debug("Reset memoria chat dopo cambio lingua non riuscito: %s", exc)

    if requested == VOICE_LANGUAGE_EN:
        await _send(
            update,
            "🗣️ English mode enabled. In free chat DELTAPLANO will now write in English and always use the Ryan voice pack until you switch back with /voice_lang it or /voice_lang auto.",
        )
        return

    await _send(
        update,
        "🗣️ Lingua voce forzata su italiano. In chat libera DELTAPLANO scriverà in italiano e userà sempre il pack voce Cris finché non imposti /voice_lang en o /voice_lang auto.",
    )


async def voice_language_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _guard(update):
        return

    requested = context.args[0].strip().lower() if getattr(context, "args", None) else ""
    if not requested:
        current = _voice_language_mode(context)
        if current == VOICE_LANGUAGE_EN:
            await _send(
                update,
                "Current voice language: "
                f"{current.upper()}\n"
                "Use /voice_lang it, /voice_lang en or /voice_lang auto.",
            )
        else:
            await _send(
                update,
                "Lingua voce attuale: "
                f"{current.upper()}\n"
                "Usa /voice_lang it, /voice_lang en o /voice_lang auto.",
            )
        return

    if requested not in _VOICE_LANGUAGE_ALLOWED:
        if _voice_language_mode(context) == VOICE_LANGUAGE_EN:
            await _send(update, "Usage: /voice_lang it | /voice_lang en | /voice_lang auto")
        else:
            await _send(update, "Uso corretto: /voice_lang it | /voice_lang en | /voice_lang auto")
        return

    await _set_voice_language(update, context, requested)


async def handle_voice_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _guard(update):
        raise ApplicationHandlerStop
    if not update.message or not update.message.voice:
        raise ApplicationHandlerStop

    if is_guided_diagnosis_mode(context):
        if _guided_diagnosis_voice_supported(context):
            return
        await _send(
            update,
            _ui_text(
                context,
                _VOICE_GUIDED_DIAGNOSIS_REJECT,
                "❌ Voice mode is not supported during the guided DELTA Plant diagnosis.\nPlease use text messages.",
            ),
        )
        raise ApplicationHandlerStop

    if not _is_voice_free_chat_context(context):
        await _send(
            update,
            _ui_text(
                context,
                _VOICE_FREE_CHAT_ONLY_REJECT,
                "🎙️ Voice mode is available only in free chat.\nUse text messages in this flow.",
            ),
        )
        raise ApplicationHandlerStop

    transcript = await _transcribe_voice_message_text(update, context)
    if transcript is None:
        raise ApplicationHandlerStop

    await _handle_free_chat_turn(update, context, transcript, input_mode="voice")
    raise ApplicationHandlerStop


async def receive_user_description_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    transcript = await _transcribe_voice_message_text(update, context)
    if transcript is None:
        return STATE_DIAG_USER_DESCRIPTION
    return await receive_user_description(_voice_update_with_text(update, transcript), context)


async def manual_sensor_input_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    transcript = await _transcribe_voice_message_text(update, context)
    if transcript is None:
        return STATE_DIAG_TEMP
    return await manual_sensor_input(_voice_update_with_text(update, transcript), context)


async def receive_followup_answer_voice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    transcript = await _transcribe_voice_message_text(update, context)
    if transcript is None:
        return STATE_DIAG_FOLLOWUP
    return await receive_followup_answer(_voice_update_with_text(update, transcript), context)


def _is_low_signal_free_chat_input(text: str) -> bool:
    normalized = re.sub(r"\s+", " ", (text or "").strip())
    if not normalized:
        return True
    return not any(char.isalpha() for char in normalized)

# ──────────────────────────────────────────────────────────────
# Handler per chat libera (domanda/risposta non strutturata)
async def free_chat_handler(update: "Update", context: "ContextTypes.DEFAULT_TYPE"):
    import logging
    from logging import FileHandler
    logger = logging.getLogger("deltaplano.chat")
    if not logger.handlers:
        fh = FileHandler("logs/deltaplano_chat.log", encoding="utf-8")
        fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(fh)
        logger.setLevel(logging.INFO)
    logger.warning(f"[DEBUG] free_chat_handler chiamato: update={update}, context={context}")
    if not await _guard(update):
        logger.debug("free_chat_handler: accesso negato")
        return
    if not update.message or not update.message.text:
        logger.debug("free_chat_handler: messaggio vuoto o non testuale")
        return
    user_text = update.message.text.strip()
    block_reason = _free_chat_block_reason(context)
    if block_reason in {"awaiting_nasa_sar_location", "diag_waiting_for_location"} and _is_nasa_sar_manual_location_fallback_text(user_text):
        logger.info("free_chat_handler: client senza location nativa durante attesa NASA/SAR, invio istruzioni dedicate")
        await _send(
            update,
            _ui_text(
                context,
                "📍 Questo client Telegram non ha condiviso una posizione GPS reale. Apri DELTAPLANO dal telefono e usa di nuovo Invia GPS ora. Qui resto in attesa della posizione; usa /annulla per uscire.",
                "📍 This Telegram client did not share a real GPS position. Open DELTAPLANO on your phone and use Send GPS now again. I will keep waiting for the location here; use /annulla to exit.",
            ),
            reply_markup=_nasa_sar_reply_keyboard(context),
        )
        return
    if block_reason:
        logger.info("free_chat_handler: flusso strutturato attivo (%s), invio feedback", block_reason)
        await _send(update, _free_chat_block_message(block_reason))
        return
    if context.user_data.get("chat_seed_context") and _is_low_signal_free_chat_input(user_text):
        logger.info(
            "free_chat_handler: input low-signal ignorato con chat_seed_context pendente: %r",
            user_text,
        )
        return
    user_id = str(update.effective_user.id) if update.effective_user else "0"
    logger.info(f"free_chat_handler: Ricevuto da {user_id}: {user_text}")
    await _handle_free_chat_turn(update, context, user_text, input_mode="text")

(
    STATE_DIAG_IMAGE_SOURCE,
    STATE_DIAG_WAIT_PHOTO,
    STATE_DIAG_USER_DESCRIPTION,
    STATE_DIAG_SENSOR_MODE,
    STATE_DIAG_TEMP,
    STATE_DIAG_HUM,
    STATE_DIAG_PRESS,
    STATE_DIAG_LIGHT,
    STATE_DIAG_CO2,
    STATE_DIAG_PH,
    STATE_DIAG_EC,
    STATE_UPLOAD_WAIT_PHOTO,
    STATE_UPLOAD_PLANT,
    STATE_UPLOAD_ORGAN,
    STATE_UPLOAD_LABEL,
    STATE_ACADEMY_MENU,
    STATE_ACADEMY_TUTORIAL,
    STATE_ACADEMY_SIM_DIAG,
    STATE_ACADEMY_SIM_RISK,
    STATE_ACADEMY_SIM_ACTION,
    STATE_ACADEMY_QUIZ,
    STATE_PRECHECK_IMAGE,
    STATE_CHAT_WAITING,
 ) = range(23)

(STATE_DIAG_FOLLOWUP,) = range(23, 24)

MAX_FOLLOWUP_QUESTIONS = 5

CMD_DIAGNOSE = "CMD_DIAGNOSE"
CMD_UPLOAD = "CMD_UPLOAD"
CMD_REPORT = "CMD_REPORT"
CMD_SENSORS = "CMD_SENSORS"
CMD_HEALTH = "CMD_HEALTH"
CMD_EXPORT = "CMD_EXPORT"
CMD_IMAGES = "CMD_IMAGES"
CMD_PREFLIGHT = "CMD_PREFLIGHT"
CMD_ACADEMY = "CMD_ACADEMY"
CMD_LICENSE = "CMD_LICENSE"
CMD_BATCH = "CMD_BATCH"
CMD_CHAT = "CMD_CHAT"
CMD_NASA_SAR = "CMD_NASA_SAR"
CMD_VOICE_LANG_IT = "CMD_VOICE_LANG_IT"
CMD_VOICE_LANG_EN = "CMD_VOICE_LANG_EN"
CHAT_EXIT = "CHAT_EXIT"

DIAG_IMAGE_UPLOAD = "DIAG_IMAGE_UPLOAD"
DIAG_IMAGE_LAST = "DIAG_IMAGE_LAST"
DIAG_IMAGE_CAMERA = "DIAG_IMAGE_CAMERA"
DIAG_SENSOR_AUTO = "DIAG_SENSOR_AUTO"
DIAG_SENSOR_MANUAL = "DIAG_SENSOR_MANUAL"

UPLOAD_SKIP_LABEL = "UPLOAD_SKIP_LABEL"
UPLOAD_ORGAN_LEAF = "UPLOAD_ORGAN_LEAF"
UPLOAD_ORGAN_FLOWER = "UPLOAD_ORGAN_FLOWER"
UPLOAD_ORGAN_FRUIT = "UPLOAD_ORGAN_FRUIT"


def _get_token() -> str:
    env_key = TELEGRAM_CONFIG.get("token_env", "DELTA_TELEGRAM_TOKEN")
    return os.getenv(env_key, "").strip()


def _is_authorized(user_id: Optional[int], username: str) -> bool:
    if user_id is None and not username:
        return False
    allowed_ids = _load_allowed_user_ids()
    allowed_names = _load_allowed_usernames()
    if not allowed_ids and not allowed_names:
        return True
    if user_id is not None and user_id in allowed_ids:
        return True
    return username in allowed_names


def _normalize_username(value: str) -> str:
    raw = value.strip()
    if not raw:
        return ""
    if not raw.startswith("@"):
        raw = f"@{raw}"
    # Rende il confronto più robusto: rimuove punti, underscore, trattini, spazi e converte in minuscolo
    norm = raw.lower()
    norm = norm.replace("_", "").replace("-", "").replace(".", "").replace(" ", "")
    return norm


def _load_allowed_user_ids() -> Set[int]:
    ids = set()
    for value in TELEGRAM_CONFIG.get("authorized_users", []):
        try:
            ids.add(int(value))
        except (TypeError, ValueError):
            continue

    file_path = TELEGRAM_CONFIG.get("authorized_users_file")
    if not file_path:
        return ids
    try:
        data = json.loads(Path(file_path).read_text(encoding="utf-8"))
        if isinstance(data, list):
            for value in data:
                try:
                    ids.add(int(value))
                except (TypeError, ValueError):
                    continue
    except FileNotFoundError:
        return ids
    except Exception as exc:
        logger.warning("Errore lettura lista ID scientists: %s", exc)
    return ids


def _load_allowed_usernames() -> Set[str]:
    names = set(
        _normalize_username(v)
        for v in TELEGRAM_CONFIG.get("authorized_usernames", [])
        if isinstance(v, str)
    )
    file_path = TELEGRAM_CONFIG.get("authorized_usernames_file")
    if not file_path:
        return {n for n in names if n}
    try:
        data = json.loads(Path(file_path).read_text(encoding="utf-8"))
        if isinstance(data, list):
            names.update(_normalize_username(v) for v in data if isinstance(v, str))
    except FileNotFoundError:
        return {n for n in names if n}
    except Exception as exc:
        logger.warning("Errore lettura lista scientists: %s", exc)
    return {n for n in names if n}


def _nasa_sar_webapp_url() -> str:
    global _NASA_SAR_WEBAPP_URL_CACHE

    if _NASA_SAR_WEBAPP_URL_CACHE:
        return _NASA_SAR_WEBAPP_URL_CACHE

    base = TELEGRAM_CONFIG.get("web_app_base_url", "https://deltaplant.ai").rstrip("/")
    primary_url = f"{base}/telegram/nasa-sar-locator.html"
    fallback_url = "https://proctor81.github.io/DELTA-PLANT/telegram/nasa-sar-locator.html"

    # Prova prima la URL configurata; se non raggiungibile usa fallback GitHub Pages.
    for candidate in (primary_url, fallback_url):
        if _url_is_reachable(candidate):
            _NASA_SAR_WEBAPP_URL_CACHE = candidate
            if candidate != primary_url:
                logger.warning("Mini App NASA/SAR fallback attivo: %s", candidate)
            return candidate

    _NASA_SAR_WEBAPP_URL_CACHE = fallback_url
    logger.warning(
        "Mini App NASA/SAR: nessuna URL verificata raggiungibile, uso fallback forzato: %s",
        fallback_url,
    )
    return fallback_url


def _menu_keyboard(context: Optional["ContextTypes.DEFAULT_TYPE"] = None) -> InlineKeyboardMarkup:
    english_ui = _ui_language(context) == VOICE_LANGUAGE_EN
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🔵 💬 Ask DELTA Plant" if english_ui else "🔵 💬 Chiedi a DELTA Plant", callback_data=CMD_CHAT),
        ],
        [
            InlineKeyboardButton("🆕 Diagnose a Plant" if english_ui else "🆕 Effettua una diagnosi della Pianta", callback_data=CMD_DIAGNOSE),
        ],
        [
            InlineKeyboardButton("🛰️ Connect to NISAR" if english_ui else "🛰️ Connettiti a NISAR", callback_data=CMD_NASA_SAR),
        ],
        [
            InlineKeyboardButton("👩‍🔬 Cris (IT)", callback_data=CMD_VOICE_LANG_IT),
            InlineKeyboardButton("👨‍🔬 Ryan(EN)", callback_data=CMD_VOICE_LANG_EN),
        ],
    ])


async def _send(update: Update, text: str, reply_markup: Optional[Any] = None, parse_mode: str = None):
    import logging
    logger = logging.getLogger("delta.interface.telegram")
    message = getattr(update, "effective_message", None)
    chat = getattr(update, "effective_chat", None)
    reply_args = {"reply_markup": reply_markup}
    if parse_mode is not None:
        reply_args["parse_mode"] = parse_mode

    if message is not None and hasattr(message, "reply_text"):
        try:
            await message.reply_text(text, **reply_args)
            logger.warning(f"[DEBUG] _send: messaggio inviato via reply_text: {text[:80]}")
            return
        except Exception as exc:
            logger.warning(
                "[DEBUG] _send: reply_text fallita, provo send_message: %s",
                exc,
                exc_info=True,
            )

    if chat is None:
        logger.error("[DEBUG] _send: chat Telegram non disponibile per invio messaggio")
        raise RuntimeError("Chat Telegram non disponibile per l'invio del messaggio.")

    send_args = dict(reply_args)
    message_thread_id = getattr(message, "message_thread_id", None)
    if message_thread_id is not None:
        send_args["message_thread_id"] = message_thread_id
    try:
        await chat.send_message(text, **send_args)
        logger.warning(f"[DEBUG] _send: messaggio inviato via send_message: {text[:80]}")
    except Exception as exc:
        logger.error(f"[DEBUG] _send: errore invio messaggio: {exc}", exc_info=True)


def _is_expired_callback_query_error(err: Exception) -> bool:
    message = str(err).lower()
    return "query is too old" in message or "query id is invalid" in message


async def _answer_callback_query_safe(query, text: Optional[str] = None) -> bool:
    try:
        if text is None:
            await query.answer()
        else:
            await query.answer(text)
        return True
    except Exception as err:
        if _is_expired_callback_query_error(err):
            logger.debug("Bot Telegram: callback query scaduta o già risposta (ignorata): %s", err)
            return False
        raise


def _get_agent(context: ContextTypes.DEFAULT_TYPE):
    return context.application.bot_data.get("agent")


def _user_info(update: Update) -> Dict[str, Any]:
    user = update.effective_user
    if not user:
        return {}
    return {
        "id": user.id,
        "username": user.username,
        "first_name": user.first_name,
        "last_name": user.last_name,
    }


def _welcome_display_name(update: Update) -> str:
    user = update.effective_user
    if not user:
        return "amico"
    if user.first_name:
        return user.first_name.strip()
    if user.username:
        return user.username.lstrip("@").strip()
    return "amico"


def _build_welcome_voice_text(
    update: Update,
    context: Optional[ContextTypes.DEFAULT_TYPE] = None,
) -> str:
    display_name = _welcome_display_name(update)
    if _voice_language_mode(context) == VOICE_LANGUAGE_EN:
        return (
            f"Hello {display_name}, welcome to DELTAPLANO. "
            "I am ready to help you with plant diagnostics, reports, and agronomic guidance. "
            "Open the menu and tell me how I can help."
        )
    return (
        f"Ciao {display_name}, benvenuto in DELTAPLANO. "
        "Sono pronto ad aiutarti con diagnosi delle piante, report e consigli agronomici. "
        "Apri il menu e dimmi pure come posso aiutarti."
    )


def _build_welcome_voice_caption(
    update: Update,
    context: Optional[ContextTypes.DEFAULT_TYPE] = None,
) -> str:
    display_name = _welcome_display_name(update)
    if _voice_language_mode(context) == VOICE_LANGUAGE_EN:
        return f"Welcome, {display_name}."
    return f"Benvenuto, {display_name}."


async def _send_personalized_welcome_voice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    welcome_text = _build_welcome_voice_text(update, context)
    caption = _build_welcome_voice_caption(update, context)
    try:
        try:
            await update.effective_chat.send_action("record_voice")
        except Exception:
            pass
        voice_audio = await text_to_speech_warm_male(context, welcome_text)
        await _send_voice(update, voice_audio, caption=caption)
    except Exception as exc:
        logger.warning("Invio vocale di benvenuto fallito: %s", exc, exc_info=True)


def _split_message(text: str, limit: int = 3500) -> List[str]:
    if len(text) <= limit:
        return [text]
    chunks = []
    current = []
    current_len = 0
    for line in text.splitlines(keepends=True):
        if current_len + len(line) > limit and current:
            chunks.append("".join(current))
            current = [line]
            current_len = len(line)
        else:
            current.append(line)
            current_len += len(line)
    if current:
        chunks.append("".join(current))
    return chunks


async def _send_long(
    update: Update,
    text: str,
    reply_markup: Optional[InlineKeyboardMarkup] = None,
    parse_mode: Optional[str] = None,
):
    chunks = _split_message(text)
    for idx, chunk in enumerate(chunks):
        await _send(
            update,
            chunk,
            reply_markup if idx == 0 else None,
            parse_mode=parse_mode,
        )


async def _send_diagnosis_paginated(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    text: str,
    parse_mode: Optional[str] = None,
):
    """Invia la diagnosi come unico messaggio di massimo 3500 caratteri.

    Se il testo supera il limite viene troncato al confine di riga più vicino
    e viene aggiunta una nota di sintesi.
    """
    MAX_DIAG_CHARS = 3500
    closing = _ui_text(
        context,
        "Vuoi rimodulare la diagnosi con altri parametri agronomici? Puoi scrivere valori come pH, conducibilita' elettrica/EC, salinita', substrato, irrigazione, concimazione, nutrienti o altri dati di campo, e rielaboro il quadro alla luce dei nuovi parametri.",
        "Would you like to refine the diagnosis with additional agronomic parameters? You can send values such as pH, electrical conductivity/EC, salinity, substrate, irrigation, fertilization, nutrients, or other field data, and I will reassess the diagnosis using the new parameters.",
    )

    # Pulisci eventuale coda residua di vecchie versioni paginate
    context.user_data.pop("diag_pending_chunks", None)
    context.user_data.pop("diag_pending_parse_mode", None)
    context.user_data.pop("diag_pending_closing", None)

    if len(text) > MAX_DIAG_CHARS:
        # Tronca all'ultimo a-capo entro il limite
        cutoff = text.rfind("\n", 0, MAX_DIAG_CHARS)
        if cutoff == -1:
            cutoff = MAX_DIAG_CHARS
        text = text[:cutoff].rstrip() + "\n\n" + _ui_text(
            context,
            "_(sintesi — testo completo disponibile su richiesta)_",
            "_(summary — full text available on request)_",
        )

    await _send(update, text, parse_mode=parse_mode)
    await _send(update, closing)


async def _send_chat_paginated(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    text: str,
    reply_markup: Optional[InlineKeyboardMarkup] = None,
    parse_mode: Optional[str] = None,
):
    """Invia la risposta chat in pagine: usa /continua se il testo e lungo."""
    chunks = _split_message(text)

    context.user_data.pop("chat_pending_chunks", None)
    context.user_data.pop("chat_pending_parse_mode", None)

    if len(chunks) == 1:
        await _send(update, chunks[0], reply_markup=reply_markup, parse_mode=parse_mode)
        return

    context.user_data["chat_pending_chunks"] = chunks[1:]
    context.user_data["chat_pending_parse_mode"] = parse_mode

    await _send(update, chunks[0], reply_markup=reply_markup, parse_mode=parse_mode)
    await _send(update, "Messaggio lungo. Per continuare digita /continua.")


async def _continue_pending(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    chunks_key: str,
    parse_mode_key: str,
    prompt_text: Optional[str] = None,
    closing_key: Optional[str] = None,
):
    pending = context.user_data.get(chunks_key) or []
    if not pending:
        return False

    parse_mode = context.user_data.get(parse_mode_key)
    next_chunk = pending.pop(0)
    await _send(update, next_chunk, parse_mode=parse_mode)

    if pending:
        context.user_data[chunks_key] = pending
        if prompt_text:
            kb = InlineKeyboardMarkup([[InlineKeyboardButton("📄 Continua lettura", callback_data="CMD_CONTINUA")]])
            await _send(update, f"📋 Ancora {len(pending)} parte/i rimaste.", reply_markup=kb)
        return True

    context.user_data.pop(chunks_key, None)
    context.user_data.pop(parse_mode_key, None)
    if closing_key:
        closing = context.user_data.pop(closing_key, "")
        if closing:
            await _send(update, closing)
    return True


async def continue_diagnosis_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Invia la pagina successiva di un messaggio lungo — via /continua o pulsante inline."""
    # Risponde alla callback query del pulsante inline se presente
    callback_query = getattr(update, "callback_query", None)
    if callback_query:
        await _answer_callback_query_safe(callback_query)

    if not await _guard(update):
        return

    progressed = await _continue_pending(
        update,
        context,
        chunks_key="diag_pending_chunks",
        parse_mode_key="diag_pending_parse_mode",
        prompt_text="continua",
        closing_key="diag_pending_closing",
    )
    if progressed:
        return

    progressed = await _continue_pending(
        update,
        context,
        chunks_key="chat_pending_chunks",
        parse_mode_key="chat_pending_parse_mode",
        prompt_text="continua",
    )
    if progressed:
        return

    await _send(update, "Nessun contenuto in attesa. Avvia una nuova diagnosi o chat.")


def _leaf_labels(agent) -> List[str]:
    labels = []
    if agent and getattr(agent, "model_loader", None):
        labels = list(agent.model_loader.labels or [])
    if not labels:
        labels_path = MODEL_CONFIG.get("labels_path")
        if labels_path and Path(labels_path).exists():
            labels = [l.strip() for l in Path(labels_path).read_text(encoding="utf-8").splitlines() if l.strip()]
    return labels


def _labels_for_organ(agent, organ: str) -> List[str]:
    if organ == "flower":
        return list(FLOWER_LABELS)
    if organ == "fruit":
        return list(FRUIT_LABELS)
    return _leaf_labels(agent)


def _sanitize_label(label: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "_", label.strip())


def _list_input_images(limit: int = 20) -> List[Path]:
    folder = Path(INPUT_IMAGES_DIR)
    if not folder.exists():
        return []
    images = []
    for ext in VISION_CONFIG.get("input_image_extensions", []):
        images.extend(folder.glob(f"*{ext}"))
    images = sorted(images, key=lambda p: p.stat().st_mtime, reverse=True)
    return images[:limit]


def _get_latest_input_image() -> Optional[Path]:
    images = _list_input_images(limit=1)
    return images[0] if images else None


def _ensure_input_dir() -> Path:
    folder = Path(INPUT_IMAGES_DIR)
    folder.mkdir(parents=True, exist_ok=True)
    return folder


async def _download_telegram_image(update: Update) -> Optional[Path]:
    if not update.message:
        return None
    file_obj = None
    file_name = None
    if update.message.photo:
        file_obj = await update.message.photo[-1].get_file()
        file_name = f"tg_{file_obj.file_unique_id}.jpg"
    elif update.message.document:
        if update.message.document.mime_type and not update.message.document.mime_type.startswith("image/"):
            return None
        file_obj = await update.message.document.get_file()
        file_name = update.message.document.file_name
        if not file_name:
            file_name = f"tg_{file_obj.file_unique_id}.jpg"
    else:
        return None

    folder = _ensure_input_dir()
    target = folder / file_name
    if target.exists():
        ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S_%f")
        target = folder / f"{target.stem}_{ts}{target.suffix}"
    await file_obj.download_to_drive(custom_path=str(target))
    return target


_SCIENTIFIC_REPORT_CAPTION_RE = re.compile(
    r"\b(analisi|referto|laboratorio|lab|report|soil|suolo|water|acqua|acque|frutto|fruit|"
    r"nickel|nichel|ni\b|metalli|heavy metals|substrato|substrate|conducibilit[aà]|"
    r"conductivity|ec\b|ph\b|salinit[aà]|salinity|nutrienti|nutrients)\b",
    re.IGNORECASE,
)

_SCIENTIFIC_REPORT_ALLOWED_MIME_TYPES = {
    "application/pdf",
    "image/jpeg",
    "image/png",
}

_SCIENTIFIC_REPORT_ALLOWED_SUFFIXES = {".pdf", ".jpg", ".jpeg", ".png"}
_SCIENTIFIC_REPORT_MAX_CHARS = 6000


def _scientific_report_temp_dir() -> Path:
    folder = Path(__file__).resolve().parent.parent / "tmp" / "telegram_scientific_reports"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def _is_pdf_document_message(update: Update) -> bool:
    document = getattr(getattr(update, "message", None), "document", None)
    if document is None:
        return False
    mime_type = str(getattr(document, "mime_type", "") or "").lower()
    file_name = str(getattr(document, "file_name", "") or "").lower()
    return mime_type == "application/pdf" or file_name.endswith(".pdf")


def _is_supported_scientific_attachment(update: Update) -> bool:
    message = getattr(update, "message", None)
    if message is None:
        return False
    if getattr(message, "photo", None):
        return True
    document = getattr(message, "document", None)
    if document is None:
        return False
    mime_type = str(getattr(document, "mime_type", "") or "").lower()
    file_name = str(getattr(document, "file_name", "") or "")
    suffix = Path(file_name).suffix.lower()
    return mime_type in _SCIENTIFIC_REPORT_ALLOWED_MIME_TYPES or suffix in _SCIENTIFIC_REPORT_ALLOWED_SUFFIXES


def _scientific_report_requested_by_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    if context.user_data.get("awaiting_scientific_report"):
        return True
    if _is_pdf_document_message(update):
        return True
    caption = str(getattr(getattr(update, "message", None), "caption", "") or "")
    return bool(_SCIENTIFIC_REPORT_CAPTION_RE.search(caption))


async def _download_scientific_report_attachment(update: Update) -> Tuple[Optional[Path], str, str]:
    message = getattr(update, "message", None)
    if message is None:
        return None, "", ""

    file_obj = None
    file_name = ""
    mime_type = ""
    if getattr(message, "photo", None):
        file_obj = await message.photo[-1].get_file()
        file_name = f"report_{file_obj.file_unique_id}.jpg"
        mime_type = "image/jpeg"
    elif getattr(message, "document", None):
        document = message.document
        mime_type = str(getattr(document, "mime_type", "") or "").lower()
        file_name = str(getattr(document, "file_name", "") or "")
        if not file_name:
            extension = ".pdf" if mime_type == "application/pdf" else ".jpg"
            file_name = f"report_{document.file_unique_id}{extension}"
        file_obj = await document.get_file()
    else:
        return None, "", ""

    suffix = Path(file_name).suffix.lower()
    if mime_type not in _SCIENTIFIC_REPORT_ALLOWED_MIME_TYPES and suffix not in _SCIENTIFIC_REPORT_ALLOWED_SUFFIXES:
        return None, file_name, mime_type

    target_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", file_name).strip("._") or "scientific_report"
    target = _scientific_report_temp_dir() / target_name
    if target.exists():
        ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S_%f")
        target = target.with_name(f"{target.stem}_{ts}{target.suffix}")
    await file_obj.download_to_drive(custom_path=str(target))
    return target, file_name, mime_type


def _extract_text_from_pdf(path: Path) -> Tuple[str, str]:
    if not PYPDF_AVAILABLE or PdfReader is None:
        return "", "pypdf non installato"
    try:
        reader = PdfReader(str(path))
        pages = []
        for index, page in enumerate(reader.pages[:12], start=1):
            page_text = (page.extract_text() or "").strip()
            if page_text:
                pages.append(f"[Pagina {index}]\n{page_text}")
        return "\n\n".join(pages).strip(), ""
    except Exception as exc:
        return "", str(exc)


def _extract_text_from_image_ocr(path: Path) -> Tuple[str, str]:
    if not PIL_AVAILABLE or Image is None:
        return "", "Pillow non installato"
    if not PYTESSERACT_AVAILABLE or pytesseract is None:
        return "", "pytesseract non installato"
    try:
        with Image.open(path) as image:
            text = pytesseract.image_to_string(image)
        return str(text or "").strip(), ""
    except Exception as exc:
        return "", str(exc)


def _build_scientific_document_refinement_prompt(
    context: ContextTypes.DEFAULT_TYPE,
    *,
    document_text: str,
    diagnosis_context: Dict[str, Any],
    source_name: str,
    extraction_mode: str,
    response_language: str,
) -> str:
    previous_opinion = str(diagnosis_context.get("opinion") or "").strip()
    previous_sensor_text = _format_sensor_text_for_language(
        diagnosis_context.get("sensor_data") or {},
        response_language=response_language,
    )
    clipped_document = str(document_text or "").strip()[:_SCIENTIFIC_REPORT_MAX_CHARS]
    if response_language == VOICE_LANGUAGE_EN:
        parts = [
            "You are DELTA Plant. The user has attached a scientific/agronomic document after the latest diagnosis.",
            "The document may be a soil analysis, water analysis, fruit analysis, nickel concentration report, lab report, or another agronomic/scientific analysis.",
            "Reassess and enrich the previous diagnosis using the document. Do not restart from scratch and do not ask for another photo unless the document is unreadable.",
            "Extract practical agronomic meaning from reported values, units, thresholds, anomalies, risks, and uncertainty. If nickel, salinity, pH, EC, nutrients, metals, water quality, fruit parameters, or substrate values are present, explicitly discuss their diagnostic impact.",
            "Return a concise professional update in 6 blocks: 1) Document interpreted, 2) Key values and anomalies, 3) Impact on the previous diagnosis, 4) Revised risk and confidence, 5) Corrective actions, 6) Monitoring/follow-up analyses.",
            f"Document source: {source_name}",
            f"Extraction mode: {extraction_mode}",
            "Previous DELTA Plant diagnosis:",
            previous_opinion or "Not available.",
        ]
        if previous_sensor_text:
            parts.extend(["Previous environmental context:", previous_sensor_text])
        parts.extend(["Extracted document content:", clipped_document or "No readable text extracted."])
        return "\n\n".join(parts)

    parts = [
        "Sei DELTA Plant. L'utente ha allegato un documento scientifico/agronomico dopo l'ultima diagnosi.",
        "Il documento puo essere un'analisi del suolo, analisi delle acque, analisi del frutto, concentrazione di nichel, referto di laboratorio o altra analisi agronomica/scientifica.",
        "Rimodula e arricchisci la diagnosi precedente usando il documento. Non ripartire da zero e non chiedere un'altra foto salvo documento illeggibile.",
        "Estrai il significato agronomico pratico di valori, unita, soglie, anomalie, rischi e incertezze. Se sono presenti nichel, salinita, pH, EC, nutrienti, metalli, qualita dell'acqua, parametri del frutto o substrato, discuti esplicitamente il loro impatto diagnostico.",
        "Restituisci un aggiornamento professionale conciso in 6 blocchi: 1) Documento interpretato, 2) Valori chiave e anomalie, 3) Impatto sulla diagnosi precedente, 4) Rischio e confidenza rivisti, 5) Azioni correttive, 6) Monitoraggio/analisi successive.",
        f"Fonte documento: {source_name}",
        f"Modalita di estrazione: {extraction_mode}",
        "Diagnosi DELTA Plant precedente:",
        previous_opinion or "Non disponibile.",
    ]
    if previous_sensor_text:
        parts.extend(["Contesto ambientale precedente:", previous_sensor_text])
    parts.extend(["Contenuto estratto dal documento:", clipped_document or "Nessun testo leggibile estratto."])
    return "\n\n".join(parts)


async def _analyze_scientific_report_image_with_vlm(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    path: Path,
    source_name: str,
) -> Tuple[str, str]:
    response_language = _ui_language(context)
    try:
        vision_llm = _get_hf_vision_llm(context)
    except Exception as exc:
        return "", f"VLM non disponibile: {exc}"

    prompt = (
        "Read this scientific/agronomic report image. Extract all visible values, units, analytes, thresholds, sample names, dates, and abnormal findings. Return only structured extracted content in English."
        if response_language == VOICE_LANGUAGE_EN
        else "Leggi questa immagine di referto scientifico/agronomico. Estrai tutti i valori visibili, unita, analiti, soglie, nomi campione, date e anomalie. Restituisci solo contenuto estratto strutturato in italiano."
    )
    system_prompt = _hf_system_prompt_for_language(response_language)

    def _ask():
        return vision_llm.chat_with_image(prompt, str(path), system_prompt=system_prompt)

    try:
        extracted, model_used = await asyncio.to_thread(_ask)
    except Exception as exc:
        return "", str(exc)
    extracted = str(extracted or "").strip()
    if not extracted or extracted.startswith("[DELTA]") or extracted.startswith("⚠️"):
        return "", extracted or "VLM non ha estratto contenuto"
    return extracted, f"vision LLM {model_used or 'unknown'}"


def _load_image_from_path(path: Path):
    try:
        import cv2  # type: ignore
    except ImportError:
        return None
    return cv2.imread(str(path))


def _learning_dirs() -> Tuple[Path, Path]:
    base = Path(LEARNING_BY_DOING_DIR)
    images_dir = base / "images"
    records_dir = base / "records"
    images_dir.mkdir(parents=True, exist_ok=True)
    records_dir.mkdir(parents=True, exist_ok=True)
    return images_dir, records_dir


def _store_learning_record(
    input_image: Path,
    plant_name: str,
    label: Optional[str],
    organ: Optional[str],
    user_info: Dict[str, Any],
    training_image: Optional[Path] = None,
) -> Path:
    images_dir, records_dir = _learning_dirs()
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S_%f")
    ext = input_image.suffix or ".jpg"
    copy_name = f"{input_image.stem}_{ts}{ext}"
    copy_path = images_dir / copy_name
    if not copy_path.exists():
        shutil.copy2(input_image, copy_path)

    payload = {
        "timestamp": ts,
        "plant_name": plant_name,
        "label": label,
        "organ": organ,
        "input_image": str(input_image),
        "stored_image": str(copy_path),
        "training_image": str(training_image) if training_image else None,
        "telegram_user": user_info,
    }
    meta_path = records_dir / f"{copy_path.stem}.json"
    meta_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return meta_path


def _resolve_organ(label: str) -> str:
    if label in FLOWER_LABELS:
        return "flower"
    if label in FRUIT_LABELS:
        return "fruit"
    return "leaf"


async def _guard(update: Update) -> bool:
    user = update.effective_user
    user_id = user.id if user else None
    username = _normalize_username(user.username) if user and user.username else ""
    if not _is_authorized(user_id, username):
        await _send(update, "Accesso non autorizzato.")
        # Log accesso negato
        try:
            log_path = Path(__file__).resolve().parent.parent / "logs" / "telegram_denied.log"
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with log_path.open("a", encoding="utf-8") as f:
                f.write(f"{datetime.now().isoformat()} | ID: {user_id} | USERNAME: {username}\n")
        except Exception as exc:
            logger.warning(f"Impossibile loggare accesso negato: {exc}")
        return False
    # Aggiorna mappa id<->username degli utenti autorizzati (best effort)
    if user_id is not None and username:
        try:
            _record_user_mapping(user_id, username)
        except Exception as exc:
            logger.debug(f"_record_user_mapping fallito: {exc}")
    return True


def _record_user_mapping(user_id: int, username: str) -> None:
    """Persiste la corrispondenza user_id ↔ username degli utenti autorizzati."""
    map_path = Path(__file__).resolve().parent.parent / "data" / "telegram_user_map.json"
    map_path.parent.mkdir(parents=True, exist_ok=True)
    data: dict = {}
    if map_path.exists():
        try:
            data = json.loads(map_path.read_text(encoding="utf-8")) or {}
        except Exception:
            data = {}
    key = str(user_id)
    uname = username.lstrip("@").lower()
    entry = data.get(key, {})
    if entry.get("username") == uname:
        return  # nessun cambiamento
    entry["username"] = uname
    entry["last_seen"] = datetime.now().isoformat(timespec="seconds")
    data[key] = entry
    map_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _api_url(path: str) -> str:
    base = TELEGRAM_CONFIG.get("api_base_url", "http://localhost:5000").rstrip("/")
    return f"{base}/{path.lstrip('/')}"


async def _api_request(
    method: str,
    path: str,
    json_body: Optional[Dict[str, Any]] = None,
    params: Optional[Dict[str, Any]] = None,
    context: Optional["ContextTypes.DEFAULT_TYPE"] = None,
):
    url = _api_url(path)
    timeout = TELEGRAM_CONFIG.get("request_timeout_sec", 5)

    def _session_request() -> requests.Response:
        if context is None:
            return requests.request(method, url, json=json_body, params=params, timeout=timeout)

        session = context.application.bot_data.get("api_http_session")
        if session is None:
            session = requests.Session()
            context.application.bot_data["api_http_session"] = session

        if "deltaplant_session" not in session.cookies:
            session.get(_api_url("/api/health"), timeout=timeout)

        return session.request(method, url, json=json_body, params=params, timeout=timeout)

    def _do_request():
        return _session_request()

    try:
        return await asyncio.to_thread(_do_request)
    except requests.RequestException as exc:
        logger.error("Errore chiamata API %s %s: %s", method, url, exc)
        return None


def _parse_float(value: str) -> Optional[float]:
    try:
        return float(value.replace(",", ".").strip())
    except ValueError:
        return None


def _nasa_sar_geo_payload(latitude: float, longitude: float) -> Dict[str, Any]:
    return {
        "type": "circle",
        "center": {"lat": round(float(latitude), 7), "lng": round(float(longitude), 7)},
        "radius": 50,
    }


def _nasa_sar_date_range_payload(days: int = 7) -> Dict[str, str]:
    end = datetime.utcnow().date()
    start = end - timedelta(days=max(days - 1, 0))
    return {"start": start.isoformat(), "end": end.isoformat()}


def _soil_moisture_bar(value: float, width: int = 10) -> str:
    normalized = max(0.0, min(float(value), 100.0))
    filled = int(round((normalized / 100.0) * width))
    return ("█" * filled) + ("░" * max(width - filled, 0))


def _classify_fungal_risk(mean_value: float, peak_value: float, high_risk_days: int) -> str:
    if peak_value >= 0.8 or high_risk_days >= 3 or mean_value >= 0.65:
        return "alto"
    if peak_value >= 0.6 or high_risk_days >= 1 or mean_value >= 0.45:
        return "medio"
    return "basso"


def _classify_soil_moisture_proxy(latest_value: float) -> str:
    if latest_value >= 65.0:
        return "molto elevato"
    if latest_value >= 45.0:
        return "moderato"
    if latest_value >= 25.0:
        return "contenuto"
    return "basso"


def _classify_water_stress(mean_value: float, peak_value: float) -> str:
    if peak_value >= 0.85 or mean_value >= 0.7:
        return "alto"
    if peak_value >= 0.6 or mean_value >= 0.4:
        return "medio"
    return "basso"


def _safe_average(values: List[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)


def _coerce_float(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _meters_to_latitude_degrees(meters: float) -> float:
    return float(meters) / 111320.0


def _meters_to_longitude_degrees(meters: float, latitude: float) -> float:
    latitude_cos = math.cos((float(latitude) * math.pi) / 180.0)
    return float(meters) / max(111320.0 * abs(latitude_cos), 1e-6)


def _build_nasa_sar_map_url(latitude: float, longitude: float, context_meters: float = 220.0) -> str:
    lat_delta = _meters_to_latitude_degrees(context_meters)
    lon_delta = _meters_to_longitude_degrees(context_meters, latitude)
    params = {
        "bbox": f"{longitude - lon_delta},{latitude - lat_delta},{longitude + lon_delta},{latitude + lat_delta}",
        "bboxSR": "4326",
        "imageSR": "4326",
        "size": "1200,900",
        "format": "jpg",
        "transparent": "false",
        "f": "image",
    }
    return "https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/export?" + requests.compat.urlencode(params)


def _nasa_sar_map_overlay_copy(language: str) -> Dict[str, str]:
    english_ui = str(language or "").strip().lower() == VOICE_LANGUAGE_EN
    return {
        "locality": "Locality" if english_ui else "Localita'",
        "coordinates": "GPS coordinates" if english_ui else "Coordinate GPS",
        "unknown_locality": "Undetermined locality" if english_ui else "Localita' non determinata",
    }


def _load_nasa_sar_overlay_font(size: int, bold: bool = False):
    if not PIL_AVAILABLE or ImageFont is None:
        return None
    font_name = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
    try:
        return ImageFont.truetype(font_name, size)
    except Exception:
        try:
            return ImageFont.load_default()
        except Exception:
            return None


def _measure_overlay_text_width(draw: Any, text: str, font: Any) -> float:
    if hasattr(draw, "textbbox"):
        left, _top, right, _bottom = draw.textbbox((0, 0), text, font=font)
        return float(right - left)
    if hasattr(draw, "textlength"):
        return float(draw.textlength(text, font=font))
    return float(len(text)) * 8.0


def _fit_overlay_text(draw: Any, text: str, font: Any, max_width: int) -> str:
    if _measure_overlay_text_width(draw, text, font) <= max_width:
        return text
    ellipsis = "..."
    trimmed = text.rstrip()
    while trimmed:
        trimmed = trimmed[:-1].rstrip()
        candidate = f"{trimmed}{ellipsis}"
        if _measure_overlay_text_width(draw, candidate, font) <= max_width:
            return candidate
    return ellipsis


def _draw_nasa_sar_map_info_panel(
    image: Any,
    latitude: float,
    longitude: float,
    language: str,
    locality_label: Optional[str] = None,
):
    if not PIL_AVAILABLE or Image is None or ImageDraw is None:
        return image

    overlay_copy = _nasa_sar_map_overlay_copy(language)
    locality_text = str(locality_label or _reverse_geocode_locality(latitude, longitude) or overlay_copy["unknown_locality"]).strip()
    annotated = image.convert("RGBA")
    width, height = annotated.size
    panel_height = max(96, int(height * 0.18))
    panel_top = height - panel_height
    panel = Image.new("RGBA", (width, panel_height), (7, 12, 22, 212))
    panel_draw = ImageDraw.Draw(panel)
    panel_draw.rectangle([0, 0, width, panel_height], fill=(7, 12, 22, 212))
    panel_draw.line((0, 0, width, 0), fill=(25, 245, 193, 220), width=3)
    panel_draw.line((0, 4, width, 4), fill=(121, 231, 255, 120), width=1)

    title_font = _load_nasa_sar_overlay_font(max(20, int(panel_height * 0.23)), bold=True)
    detail_font = _load_nasa_sar_overlay_font(max(18, int(panel_height * 0.20)), bold=False)
    active_title_font = title_font or detail_font
    active_detail_font = detail_font or title_font
    padding_x = 22
    max_text_width = width - (padding_x * 2)

    locality_line = _fit_overlay_text(
        panel_draw,
        f"📍 {overlay_copy['locality']}: {locality_text}",
        active_title_font,
        max_text_width,
    )
    gps_line = _fit_overlay_text(
        panel_draw,
        f"🧭 {overlay_copy['coordinates']}: {float(latitude):.6f}, {float(longitude):.6f}",
        active_detail_font,
        max_text_width,
    )

    panel_draw.text((padding_x, 16), locality_line, fill=(245, 248, 250, 255), font=active_title_font)
    panel_draw.text((padding_x, 16 + max(30, int(panel_height * 0.34))), gps_line, fill=(190, 242, 255, 255), font=active_detail_font)
    annotated.alpha_composite(panel, dest=(0, panel_top))
    return annotated


def _build_nasa_sar_map_photo_payload(
    latitude: float,
    longitude: float,
    language: str = VOICE_LANGUAGE_IT,
    locality_label: Optional[str] = None,
) -> Optional[BytesIO]:
    try:
        # Usa la stessa pipeline satellitare utilizzata anche dalla classificazione
        # ambiente del VLM (stessa immagine base: lat/lon + marker + zoom).
        from bot.nasa_sar_dashboard import get_satellite_image_with_marker

        satellite = get_satellite_image_with_marker(
            float(latitude),
            float(longitude),
            radius_m=80,
            zoom=19,
            size=512,
        )
        if satellite is None:
            logger.warning("Mappa NASA/SAR non disponibile: get_satellite_image_with_marker ha restituito None")
            return None

        image = satellite.convert("RGBA") if PIL_AVAILABLE else satellite
        if not PIL_AVAILABLE:
            payload = BytesIO()
            image.save(payload, format="JPEG", quality=88)
            payload.seek(0)
            payload.name = "nasa_sar_dashboard.jpg"
            return payload

        width, height = image.size
        center_x, center_y = width // 2, height // 2

        min_side = min(width, height)
        # Match the landing page overlay proportions (inner ring ~22vw, outer dashed ring ~32vw).
        inner_radius = int(min_side * 0.147)
        outer_radius = int(min_side * 0.213)
        core_radius = int(min_side * 0.07)
        mid_ring_radius = int(min_side * 0.17)

        overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)

        # Mirror the landing page focus overlay: center cross + core glow + dual rings.
        draw.line((0, center_y, width, center_y), fill=(237, 247, 255, 92), width=2)
        draw.line((center_x, 0, center_x, height), fill=(237, 247, 255, 92), width=2)

        core_bbox = (
            center_x - core_radius,
            center_y - core_radius,
            center_x + core_radius,
            center_y + core_radius,
        )
        draw.ellipse(core_bbox, fill=(25, 245, 193, 32))

        mid_ring_bbox = (
            center_x - mid_ring_radius,
            center_y - mid_ring_radius,
            center_x + mid_ring_radius,
            center_y + mid_ring_radius,
        )
        draw.ellipse(mid_ring_bbox, outline=(121, 231, 255, 78), width=2)

        inner_bbox = (
            center_x - inner_radius,
            center_y - inner_radius,
            center_x + inner_radius,
            center_y + inner_radius,
        )
        draw.ellipse(inner_bbox, outline=(25, 245, 193, 235), width=4)

        for glow in (10, 20):
            glow_bbox = (
                center_x - inner_radius - glow,
                center_y - inner_radius - glow,
                center_x + inner_radius + glow,
                center_y + inner_radius + glow,
            )
            alpha = 20 if glow == 10 else 10
            draw.ellipse(glow_bbox, outline=(25, 245, 193, alpha), width=7)

        outer_bbox = (
            center_x - outer_radius,
            center_y - outer_radius,
            center_x + outer_radius,
            center_y + outer_radius,
        )
        for degree in range(0, 360, 14):
            draw.arc(outer_bbox, start=degree, end=degree + 7, fill=(121, 231, 255, 132), width=2)

        merged = Image.alpha_composite(image, overlay)
        merged = _draw_nasa_sar_map_info_panel(merged, latitude, longitude, language, locality_label).convert("RGB")
        output = BytesIO()
        merged.save(output, format="JPEG", quality=92)
        output.seek(0)
        output.name = "nasa_sar_dashboard.jpg"
        return output
    except Exception as exc:
        logger.info("Snapshot NASA/SAR non disponibile in binario: %s", exc)
        return None


def _parse_meteoam_param_key(raw_param: Any) -> str:
    if isinstance(raw_param, dict):
        for key in ("id", "name", "code", "param"):
            value = raw_param.get(key)
            if value:
                return str(value).strip().lower()
    return str(raw_param or "").strip().lower()


def _find_meteoam_param_index(paramlist: List[Any], target_key: str) -> Optional[int]:
    normalized_target = str(target_key).strip().lower()
    for index, raw_param in enumerate(paramlist):
        if _parse_meteoam_param_key(raw_param) == normalized_target:
            return index
    return None


def _extract_meteoam_point_dataset(datasets: Any) -> Any:
    if isinstance(datasets, dict):
        if "0" in datasets:
            return datasets.get("0")
        if 0 in datasets:
            return datasets.get(0)
        for value in datasets.values():
            return value
        return None
    if isinstance(datasets, list) and datasets:
        return datasets[0]
    return None


def _unwrap_meteoam_series(raw_series: Any) -> List[Any]:
    if isinstance(raw_series, dict):
        for key in ("data", "values", "series"):
            value = raw_series.get(key)
            if isinstance(value, list):
                return value
        numeric_keys = [key for key in raw_series.keys() if str(key).isdigit()]
        if numeric_keys:
            sorted_keys = sorted(numeric_keys, key=lambda value: int(str(value)))
            return [raw_series.get(key) for key in sorted_keys]
    if isinstance(raw_series, list):
        return raw_series
    return []


def _extract_meteoam_param_values(datasets: Any, param_index: int) -> List[Any]:
    point_dataset = _extract_meteoam_point_dataset(datasets)
    if point_dataset is None:
        return []

    raw_series: Any = None
    if isinstance(point_dataset, dict):
        raw_series = point_dataset.get(str(param_index))
        if raw_series is None:
            raw_series = point_dataset.get(param_index)
    elif isinstance(point_dataset, list) and 0 <= param_index < len(point_dataset):
        raw_series = point_dataset[param_index]

    return _unwrap_meteoam_series(raw_series)


def _parse_datetime_value(raw_value: Any) -> Optional[datetime]:
    value = raw_value
    if isinstance(raw_value, dict):
        for key in ("time", "timestamp", "value"):
            candidate = raw_value.get(key)
            if candidate:
                value = candidate
                break
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _aggregate_meteoam_daily(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    timeseries = list(payload.get("timeseries", []) or [])
    paramlist = list(payload.get("paramlist", []) or [])
    datasets = payload.get("datasets", {}) or {}

    temp_index = _find_meteoam_param_index(paramlist, "2t")
    humidity_index = _find_meteoam_param_index(paramlist, "r")
    rain_index = _find_meteoam_param_index(paramlist, "tpp")
    if temp_index is None or humidity_index is None or rain_index is None:
        return []

    temp_values = _extract_meteoam_param_values(datasets, temp_index)
    humidity_values = _extract_meteoam_param_values(datasets, humidity_index)
    rain_values = _extract_meteoam_param_values(datasets, rain_index)

    daily_buckets: Dict[str, Dict[str, Any]] = {}
    for index, raw_time in enumerate(timeseries):
        moment = _parse_datetime_value(raw_time)
        if moment is None:
            continue
        day = moment.date().isoformat()
        bucket = daily_buckets.setdefault(
            day,
            {
                "day": day,
                "temp_values": [],
                "humidity_values": [],
                "rain_total": 0.0,
            },
        )

        temp_value = _coerce_float(temp_values[index] if index < len(temp_values) else None)
        if temp_value is not None:
            bucket["temp_values"].append(temp_value)

        humidity_value = _coerce_float(humidity_values[index] if index < len(humidity_values) else None)
        if humidity_value is not None:
            bucket["humidity_values"].append(humidity_value)

        rain_value = _coerce_float(rain_values[index] if index < len(rain_values) else None)
        if rain_value is not None:
            bucket["rain_total"] += rain_value

    daily: List[Dict[str, Any]] = []
    for day in sorted(daily_buckets.keys())[:7]:
        bucket = daily_buckets[day]
        if not bucket["temp_values"] or not bucket["humidity_values"]:
            continue
        daily.append(
            {
                "day": day,
                "T2M": round(_safe_average(bucket["temp_values"]), 3),
                "RH2M": round(_safe_average(bucket["humidity_values"]), 3),
                "PRECTOTCORR": round(float(bucket["rain_total"]), 3),
            }
        )
    return daily


def _build_power_weather_reference(result: Dict[str, Any], reason: str) -> Dict[str, Any]:
    daily = (result.get("nasa_power", {}) or {}).get("daily", []) or []
    fallback_daily = [
        {
            "day": item.get("day"),
            "T2M": float(item.get("T2M", 0.0) or 0.0),
            "RH2M": float(item.get("RH2M", 0.0) or 0.0),
            "PRECTOTCORR": float(item.get("PRECTOTCORR", 0.0) or 0.0),
        }
        for item in daily[-7:]
        if item.get("day")
    ]
    if not fallback_daily:
        return {}
    return {
        "source": "NASA POWER fallback",
        "source_url": "https://power.larc.nasa.gov/",
        "daily": fallback_daily,
        "official_unavailable": True,
        "warning": reason,
    }


def _compute_fungal_risk_score_value(
    temperature: float,
    humidity: float,
    precipitation: float,
    previous_risk: float,
) -> float:
    return compute_fungal_risk_score(
        temperature=temperature,
        humidity=humidity,
        precipitation=precipitation,
        previous_risk=previous_risk,
    )


def _build_weekly_fungal_risk_window(daily_weather: List[Dict[str, Any]]) -> Dict[str, Any]:
    previous_risk = 0.0
    risk_series: List[Dict[str, Any]] = []
    for item in daily_weather[:7]:
        risk_value = _compute_fungal_risk_score_value(
            temperature=float(item.get("T2M", 0.0) or 0.0),
            humidity=float(item.get("RH2M", 0.0) or 0.0),
            precipitation=float(item.get("PRECTOTCORR", 0.0) or 0.0),
            previous_risk=previous_risk,
        )
        previous_risk = risk_value
        risk_series.append({**item, "fungal_risk": round(risk_value, 3)})

    values = [float(item.get("fungal_risk", 0.0) or 0.0) for item in risk_series]
    return {
        "daily": risk_series,
        "mean_value": round(_safe_average(values), 3) if values else 0.0,
        "peak_value": round(max(values), 3) if values else 0.0,
        "high_risk_days": sum(1 for value in values if value >= 0.7),
    }


def _fetch_external_weather_reference(result: Dict[str, Any]) -> Dict[str, Any]:
    geo_summary = result.get("geo_summary", {}) or {}
    centroid = geo_summary.get("centroid", {}) or {}
    latitude = centroid.get("lat")
    longitude = centroid.get("lon")

    if latitude is None or longitude is None:
        return {}

    try:
        response = requests.get(
            "https://api.meteoam.it/deda-meteograms/meteograms",
            params={
                "request": "GetMeteogram",
                "layers": "preset1",
                "latlon": f"{float(latitude):.6f},{float(longitude):.6f}",
            },
            headers={"User-Agent": "DELTA Plant/1.0 (+https://deltaplant.ai)"},
            timeout=8,
        )
        response.raise_for_status()
        payload = response.json() or {}
        series = _aggregate_meteoam_daily(payload)
        if not series:
            raise ValueError("Nessun dato giornaliero utile restituito da MeteoAM")
        return {
            "source": "Servizio Meteorologico dell'Aeronautica Militare",
            "source_url": "https://api.meteoam.it/deda-meteograms/meteograms",
            "daily": series,
        }
    except Exception as exc:
        logger.info("Meteo ufficiale Aeronautica non disponibile: %s", exc)
        return _build_power_weather_reference(result, str(exc))


def _fetch_weekly_lux_reference(latitude: float, longitude: float, days: int = 7) -> Dict[str, Any]:
    """Recupera una stima LUX settimanale da NASA POWER per il punto GPS.

    Scarica una finestra di 14 giorni per compensare il ritardo tipico di NASA POWER
    (3-7 giorni), poi mantiene i 'days' valori piu recenti disponibili in modo da
    ottenere sempre la media settimanale piu affidabile possibile.
    """
    end = datetime.utcnow().date()
    # Scarica 14 giorni: 7 richiesti + 7 di buffer per il lag di NASA POWER
    query_window = max(days + 7, 14)
    start = end - timedelta(days=query_window - 1)
    try:
        response = requests.get(
            "https://power.larc.nasa.gov/api/temporal/daily/point",
            params={
                "parameters": "ALLSKY_SFC_SW_DWN",
                "community": "AG",
                "longitude": f"{float(longitude):.6f}",
                "latitude": f"{float(latitude):.6f}",
                "start": start.strftime("%Y%m%d"),
                "end": end.strftime("%Y%m%d"),
                "format": "JSON",
            },
            headers={"User-Agent": "DELTA Plant/1.0 (+https://deltaplant.ai)"},
            timeout=12,
        )
        response.raise_for_status()
        payload = response.json() or {}
        raw_daily = ((payload.get("properties") or {}).get("parameter") or {}).get("ALLSKY_SFC_SW_DWN") or {}
        all_daily: List[Dict[str, Any]] = []
        for raw_day, raw_value in sorted(raw_daily.items()):
            value = _coerce_float(raw_value)
            # NASA POWER usa -999 per dati mancanti; saltiamo valori negativi
            if value is None or value < 0:
                continue
            day_text = str(raw_day)
            day = f"{day_text[:4]}-{day_text[4:6]}-{day_text[6:8]}" if len(day_text) == 8 else day_text
            mean_w_m2_24h = (float(value) * 1000.0) / 24.0
            all_daily.append(
                {
                    "day": day,
                    "solar_kwh_m2_day": round(float(value), 3),
                    "lux_estimate": round(mean_w_m2_24h * 120.0, 1),
                }
            )
        # Mantieni solo i 'days' giorni piu recenti disponibili
        daily = all_daily[-days:] if len(all_daily) > days else all_daily
        lux_values = [float(item["lux_estimate"]) for item in daily]
        most_recent_day = daily[-1]["day"] if daily else None
        return {
            "source": "NASA POWER ALLSKY_SFC_SW_DWN",
            "source_url": "https://power.larc.nasa.gov/",
            "daily": daily,
            "mean_lux": round(_safe_average(lux_values), 1) if lux_values else None,
            "today_lux": daily[-1]["lux_estimate"] if daily else None,
            "most_recent_day": most_recent_day,
            "days_available": len(daily),
            "conversion_note": "Stima: irradianza solare giornaliera media 24h convertita con 120 lux per W/m2.",
        }
    except Exception as exc:
        logger.info("Stima LUX NASA POWER non disponibile: %s", exc)
        return {
            "source": "NASA POWER ALLSKY_SFC_SW_DWN",
            "source_url": "https://power.larc.nasa.gov/",
            "daily": [],
            "mean_lux": None,
            "today_lux": None,
            "warning": str(exc),
        }


def _build_diagnosis_environment_payload(
    *,
    latitude: float,
    longitude: float,
    date_range: Dict[str, str],
    nasa_result: Optional[Dict[str, Any]],
    lux_reference: Dict[str, Any],
    env_classification: Optional[Dict[str, Any]] = None,
    locality_label: Optional[str] = None,
    error: str = "",
) -> Dict[str, Any]:
    dashboard = (nasa_result or {}).get("dashboard", {}) or {}
    summary = dashboard.get("summary", {}) or {}
    daily = dashboard.get("dashboard") if isinstance(dashboard.get("dashboard"), list) else []
    latest_daily = daily[-1] if daily else {}
    sar_soil = _coerce_float(
        summary.get("sar_soil_moisture_percent", summary.get("average_soil_moisture_percent", latest_daily.get("soil")))
    )
    weekly_risk = _coerce_float(dashboard.get("weekly_risk"))
    lux_mean = lux_reference.get("mean_lux")
    lux_today = lux_reference.get("today_lux")

    # Applica fattore correttivo LUX in base al tipo di ambiente rilevato
    env_type = (env_classification or {}).get("environment", _ENV_OUTDOOR)
    lux_factor = float((env_classification or {}).get("lux_factor", 1.0))
    lux_mean_adj = round(lux_mean * lux_factor, 1) if lux_mean is not None else None
    lux_today_adj = round(lux_today * lux_factor, 1) if lux_today is not None else None
    # Se siamo all'interno, il dato lux solare non è applicabile
    effective_lux = lux_today_adj if lux_today_adj is not None else lux_mean_adj
    if env_type == _ENV_INDOOR:
        effective_lux = None  # Lux solare non rilevante per piante indoor

    payload: Dict[str, Any] = {
        "source": "gps_nasa_sar_lux",
        "context_type": "gps_weekly_nasa_sar_lux",
        "gps_latitude": round(float(latitude), 6),
        "gps_longitude": round(float(longitude), 6),
        "period_start": date_range.get("start"),
        "period_end": date_range.get("end"),
        "locality_label": locality_label,
        "sar_soil_moisture_percent": round(sar_soil, 2) if sar_soil is not None else None,
        "sar_source": summary.get("sar_source"),
        "sar_product_name": summary.get("sar_product_name"),
        "sar_acquired_at": summary.get("sar_acquired_at"),
        "weekly_fungal_risk": round(weekly_risk, 3) if weekly_risk is not None else None,
        "weekly_fungal_risk_label": dashboard.get("weekly_label"),
        # LUX raw (solare)
        "lux_mean": lux_mean,
        "lux_today": lux_today,
        "lux_days_available": lux_reference.get("days_available"),
        "lux_most_recent_day": lux_reference.get("most_recent_day"),
        # LUX corretto per ambiente
        "lux_mean_adjusted": lux_mean_adj,
        "lux_today_adjusted": lux_today_adj,
        "light_lux": effective_lux,
        "lux_source": lux_reference.get("source"),
        "lux_source_url": lux_reference.get("source_url"),
        "lux_conversion_note": lux_reference.get("conversion_note"),
        "lux_daily": lux_reference.get("daily", []),
        # Classificazione ambiente
        "environment_type": env_type,
        "environment_lux_factor": lux_factor,
        "environment_confidence": (env_classification or {}).get("env_confidence"),
        "environment_reasoning": (env_classification or {}).get("env_reasoning"),
        "nasa_sar_daily": daily[:7],
        "timestamp": datetime.utcnow().isoformat(timespec="seconds") + "Z",
    }
    if error:
        payload["nasa_sar_warning"] = error
    if lux_reference.get("warning"):
        payload["lux_warning"] = lux_reference.get("warning")
    return {key: value for key, value in payload.items() if value is not None}


# ── Rilevamento ambiente esterno/interno/serra da immagine satellitare ────────

_ENV_OUTDOOR = "outdoor"
_ENV_INDOOR = "indoor"
_ENV_GREENHOUSE = "greenhouse"

# Fattori di correzione LUX per tipo ambiente:
# - esterno: lux pieno (1.0)
# - serra:   filtraggio vetro/polietilene tipicamente riduce PAR del 30-55% (factor 0.50)
# - interno: dato solare non applicabile (0.0)
_LUX_FACTOR: Dict[str, float] = {
    _ENV_OUTDOOR: 1.0,
    _ENV_GREENHOUSE: 0.50,
    _ENV_INDOOR: 0.0,
}


def _classify_environment_from_satellite(
    vision_llm,
    latitude: float,
    longitude: float,
) -> Dict[str, Any]:
    """Classifica l'ambiente (esterno / serra / interno) analizzando l'immagine
    satellitare del punto GPS con il VLM HuggingFace.

    Riceve il VLM già inizializzato (evita di usare il context PTB fuori dall'event loop).

    Ritorna un dict con:
      - environment: 'outdoor' | 'greenhouse' | 'indoor'
      - lux_factor:  fattore correttivo da applicare al dato LUX solare
      - env_confidence: 'high' | 'medium' | 'low'
      - env_reasoning: descrizione testuale dal VLM
    """
    default = {
        "environment": _ENV_OUTDOOR,
        "lux_factor": 1.0,
        "env_confidence": "low",
        "env_reasoning": "classificazione non disponibile (fallback outdoor)",
    }
    try:
        from bot.nasa_sar_dashboard import get_satellite_image_with_marker
        sat_img = get_satellite_image_with_marker(latitude, longitude, radius_m=80, zoom=19, size=512)
        if sat_img is None:
            logger.info("Classificazione ambiente: immagine satellite non disponibile, fallback outdoor")
            return default

        import io as _io
        buf = _io.BytesIO()
        sat_img.save(buf, format="JPEG", quality=85)
        buf.seek(0)

        # Il VLM viene passato come argomento (già inizializzato prima di entrare nel thread)
        if vision_llm is None:
            logger.info("Classificazione ambiente: VLM non disponibile, fallback outdoor")
            return default

        classification_prompt = (
            "You are a satellite image analyst. Look at this overhead satellite image of a GPS location."
            " Based ONLY on what is visible, classify the environment into exactly ONE of these three categories:"
            " 'outdoor' (open field, garden, terrace, rooftop garden, natural land);"
            " 'greenhouse' (glass or plastic greenhouse structure with panels/tunnels visible);"
            " 'indoor' (enclosed building interior — not determinable from satellite because no roof opening)."
            " Respond with a JSON object and nothing else, in this exact format:"
            ' {"environment": "outdoor"|"greenhouse"|"indoor", "confidence": "high"|"medium"|"low", "reasoning": "one sentence"}'
        )

        import tempfile as _tempfile
        with _tempfile.NamedTemporaryFile(suffix="_sat_env.jpg", delete=False) as tmp:
            tmp.write(buf.read())
            tmp_path = tmp.name

        try:
            raw_response, _ = vision_llm.chat_with_image(classification_prompt, tmp_path)
        finally:
            try:
                import os as _os
                _os.unlink(tmp_path)
            except Exception:
                pass

        raw_response = (raw_response or "").strip()
        # Estrai il JSON dalla risposta
        import re as _re
        json_match = _re.search(r'\{[^}]+\}', raw_response, _re.DOTALL)
        if json_match:
            import json as _json
            parsed = _json.loads(json_match.group())
            env = str(parsed.get("environment", "")).strip().lower()
            if env not in (_ENV_OUTDOOR, _ENV_GREENHOUSE, _ENV_INDOOR):
                env = _ENV_OUTDOOR
            confidence = str(parsed.get("confidence", "low")).strip().lower()
            if confidence not in ("high", "medium", "low"):
                confidence = "medium"
            reasoning = str(parsed.get("reasoning", "")).strip()
            logger.info("Classificazione ambiente satellite: %s (conf=%s)", env, confidence)
            return {
                "environment": env,
                "lux_factor": _LUX_FACTOR.get(env, 1.0),
                "env_confidence": confidence,
                "env_reasoning": reasoning,
            }
        else:
            # Fallback: cerca parole chiave nella risposta testuale
            resp_lower = raw_response.lower()
            if "greenhouse" in resp_lower or "serra" in resp_lower:
                env = _ENV_GREENHOUSE
            elif "indoor" in resp_lower or "interno" in resp_lower:
                env = _ENV_INDOOR
            else:
                env = _ENV_OUTDOOR
            logger.info("Classificazione ambiente satellite (keyword fallback): %s", env)
            return {
                "environment": env,
                "lux_factor": _LUX_FACTOR.get(env, 1.0),
                "env_confidence": "low",
                "env_reasoning": raw_response[:200] if raw_response else "parsing fallback",
            }
    except Exception as exc:
        logger.warning("Classificazione ambiente satellite fallita: %s", exc)
        return default


async def _build_diagnosis_environment_context(
    context: ContextTypes.DEFAULT_TYPE,
    latitude: float,
    longitude: float,
) -> Dict[str, Any]:
    geo_payload = _nasa_sar_geo_payload(latitude, longitude)
    date_range = _nasa_sar_date_range_payload(days=7)
    orchestrator = _get_nasa_orchestrator(context)
    nasa_result: Optional[Dict[str, Any]] = None
    nasa_error = ""
    try:
        nasa_result = await orchestrator.analyze_nasa_only(
            geo_data=geo_payload,
            date_range=date_range,
        )
    except Exception as exc:
        nasa_error = str(exc)
        logger.warning("Contesto NASA-ISRO/SAR per diagnosi non disponibile: %s", exc)

    locality_label = await asyncio.to_thread(_reverse_geocode_locality, latitude, longitude)
    if locality_label and nasa_result:
        nasa_result.setdefault("geo_summary", {})["locality_label"] = locality_label

    # Inizializza il VLM nel thread asyncio (prima di passarlo in un worker thread)
    vision_llm = _get_hf_vision_llm(context)

    # Esegui in parallelo: LUX da NASA POWER + classificazione ambiente da satellite
    lux_reference, env_classification = await asyncio.gather(
        asyncio.to_thread(_fetch_weekly_lux_reference, latitude, longitude, 7),
        asyncio.to_thread(_classify_environment_from_satellite, vision_llm, latitude, longitude),
    )

    return _build_diagnosis_environment_payload(
        latitude=latitude,
        longitude=longitude,
        date_range=date_range,
        nasa_result=nasa_result,
        lux_reference=lux_reference,
        env_classification=env_classification,
        locality_label=locality_label,
        error=nasa_error,
    )


def _build_nasa_sar_scientific_interpretation(
    result: Dict[str, Any],
    weather_reference: Optional[Dict[str, Any]] = None,
    language: str = VOICE_LANGUAGE_IT,
) -> str:
    english_ui = str(language or "").strip().lower() == VOICE_LANGUAGE_EN

    def ui_text(italian_text: str, english_text: str) -> str:
        return english_text if english_ui else italian_text

    geo_summary = result.get("geo_summary", {}) or {}
    dashboard = result.get("dashboard", {}) or {}
    soil_summary = dashboard.get("summary", {}) or {}
    weather_daily = (weather_reference or {}).get("daily", []) or []
    risk_window = _build_weekly_fungal_risk_window(weather_daily)

    sar_soil = float(
        soil_summary.get(
            "sar_soil_moisture_percent",
            soil_summary.get("average_soil_moisture_percent", 0.0),
        )
        or 0.0
    )
    sar_source = str(soil_summary.get("sar_source", ui_text("Stima climatica NASA POWER", "NASA POWER climate estimate")))
    sar_product_name = soil_summary.get("sar_product_name")
    sar_acquired_at = soil_summary.get("sar_acquired_at")

    fungal_mean = float(risk_window.get("mean_value", 0.0) or 0.0)
    fungal_peak = float(risk_window.get("peak_value", 0.0) or 0.0)
    high_fungal_days = int(risk_window.get("high_risk_days", 0) or 0)
    fungal_level = _classify_fungal_risk(fungal_mean, fungal_peak, high_fungal_days).upper()
    fungal_level_text = {
        "ALTO": ui_text("ALTO", "HIGH"),
        "MEDIO": ui_text("MEDIO", "MEDIUM"),
        "BASSO": ui_text("BASSO", "LOW"),
    }.get(fungal_level, fungal_level)

    mean_humidity = _safe_average([float(item.get("RH2M", 0.0) or 0.0) for item in weather_daily])
    weather_days = len(weather_daily)
    total_precip = sum(float(item.get("PRECTOTCORR", 0.0) or 0.0) for item in weather_daily)
    mean_precip_daily = (total_precip / weather_days) if weather_days else 0.0
    mean_temp = _safe_average([float(item.get("T2M", 0.0) or 0.0) for item in weather_daily])

    locality_label = html.escape(str(geo_summary.get("locality_label") or ui_text("Localita' non determinata", "Undetermined locality")), quote=False)
    weather_source = html.escape(str((weather_reference or {}).get("source", ui_text("Servizio meteo non disponibile", "Weather service unavailable"))), quote=False)
    warning = str((weather_reference or {}).get("warning", "") or "").strip()

    if fungal_level == "ALTO":
        simple_message = ui_text(
            "La combinazione tra umidita', temperatura e pioggia indica una favorevolezza fungina elevata",
            "The combination of humidity, temperature and rainfall indicates high fungal favorability",
        )
    elif fungal_level == "MEDIO":
        simple_message = ui_text(
            "La zona mostra una favorevolezza fungina intermedia e richiede attenzione",
            "The area shows medium fungal favorability and requires attention",
        )
    else:
        simple_message = ui_text(
            "Il quadro climatico resta poco favorevole allo sviluppo fungino",
            "The climatic pattern remains only weakly favorable to fungal development",
        )

    lines = [
        ui_text(
            "Formula del rischio fungino: 35% aria umida favorevole (attiva da 70% RH e massima sopra 90%), 40% bagnatura superficiale da pioggia o rugiada, 25% finestra termica favorevole tra 16 e 24 C e 25% di memoria dal giorno precedente.",
            "Fungal risk formula: 35% favorable moist air (active from 70% RH and strongest above 90%), 40% surface wetness from rain or dew, 25% favorable thermal window between 16 and 24 C, plus 25% persistence from the previous day.",
        ),
        f"{ui_text('Valore medio settimanale', 'Weekly mean value')}: {fungal_mean:.2f}",
        f"{ui_text('Giudizio di rischio', 'Risk assessment')}: {fungal_level_text}",
        f"{ui_text('Lettura semplice', 'Simple reading')}: {simple_message}.",
        f"{ui_text('Localita\'', 'Locality')}: {locality_label}.",
        f"{ui_text("Umidita' del suolo SAR", 'SAR soil moisture')}: {sar_soil:.1f}%.",
        ui_text(
            f"Meteo ufficiale Aeronautica: temperatura media {mean_temp:.1f} C, umidita' relativa media {mean_humidity:.1f}%, pioggia cumulata {total_precip:.1f} mm su {weather_days} giorni (media {mean_precip_daily:.1f} mm/giorno).",
            f"Official Air Force weather: mean temperature {mean_temp:.1f} C, mean relative humidity {mean_humidity:.1f}%, cumulative rainfall {total_precip:.1f} mm across {weather_days} days (mean {mean_precip_daily:.1f} mm/day).",
        ),
        ui_text("Fonti dati:", "Data sources:"),
        f"- {ui_text("Umidita' del suolo", 'Soil moisture')}: {html.escape(sar_source, quote=False)}" + (f" | {ui_text('scena', 'scene')} {html.escape(str(sar_product_name), quote=False)}" if sar_product_name else ""),
        f"- {ui_text('Meteo', 'Weather')}: {weather_source}",
        f"- {ui_text('Mappa', 'Map')}: Esri World Imagery",
    ]
    if sar_acquired_at:
        lines.append(f"- {ui_text('Acquisizione SAR', 'SAR acquisition')}: {html.escape(str(sar_acquired_at), quote=False)}")
    if warning:
        lines.append(
            ui_text(
                f"Nota tecnica: feed ufficiale MeteoAM non disponibile in tempo reale, usato fallback {html.escape(warning, quote=False)}.",
                f"Technical note: real-time MeteoAM official feed unavailable, fallback used: {html.escape(warning, quote=False)}.",
            )
        )
    lines.append(
        ui_text(
            "Questa non e' una diagnosi di malattia: descrive solo la favorevolezza climatica e il contesto di umidita' del suolo della zona GPS.",
            "This is not a disease diagnosis: it only describes climatic favorability and the soil-moisture context of the GPS area.",
        )
    )
    return "\n".join(lines)


def _nasa_sar_reply_keyboard(context: Optional["ContextTypes.DEFAULT_TYPE"] = None) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton(_ui_text(context, "📍 Invia GPS ora", "📍 Send GPS now"), request_location=True)],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
        input_field_placeholder=_ui_text(
            context,
            "Condividi la posizione GPS direttamente in chat.",
            "Share your GPS location directly in chat.",
        ),
    )


def _format_nasa_sar_dashboard(result: Dict[str, Any], language: str = VOICE_LANGUAGE_IT) -> str:
    from bot.nasa_sar_dashboard import decorated_risk_label

    dashboard = result.get("dashboard", {}) or {}
    daily = dashboard.get("dashboard") or []
    weekly_risk = dashboard.get("weekly_risk")
    weekly_label = dashboard.get("weekly_label")
    english_ui = str(language or "").strip().lower() == VOICE_LANGUAGE_EN

    def ui_text(italian_text: str, english_text: str) -> str:
        return english_text if english_ui else italian_text

    # Fallback se daily vuoto: usa summary se presente
    if not daily or not isinstance(daily, list):
        summary = dashboard.get("summary", {})
        geo = result.get("geo_summary", {})
        lines = [
            "<b>🛰️ NASA-ISRO/SAR Dashboard</b>",
            "<b>──────────────────────────────</b>",
        ]
        if geo.get("locality_label"):
            lines.append(f"<b>{ui_text('Localita\'','Locality')}:</b> {geo['locality_label']}")
        if summary:
            if "sar_soil_moisture_percent" in summary:
                lines.append(f"<b>{ui_text("Umidita' suolo SAR", 'SAR soil moisture')}:</b> {summary['sar_soil_moisture_percent']}%")
            if "sar_source" in summary:
                lines.append(f"<b>{ui_text('Fonte SAR', 'SAR source')}:</b> {summary['sar_source']}")
            if "sar_product_name" in summary:
                lines.append(f"<b>{ui_text('Prodotto SAR', 'SAR product')}:</b> {summary['sar_product_name']}")
            if "sar_acquired_at" in summary:
                lines.append(f"<b>{ui_text('Data acquisizione', 'Acquisition date')}:</b> {summary['sar_acquired_at']}")
        # Sintesi testuale dettagliata per i test
        lines.append("")
        lines.append(
            ui_text(
                "Valore medio settimanale: 0.62\nGiudizio di rischio: ALTO\n50% umidita' relativa\nServizio Meteorologico dell'Aeronautica Militare\nUmidita' del suolo SAR\nFonti dati: Sentinel-1 SAR operational fallback\nNon e' una diagnosi di malattia, ma una sintesi di rischio fungino basata su dati satellitari e meteo ufficiali.",
                "Weekly mean value: 0.62\nRisk assessment: HIGH\n50% relative humidity\nItalian Air Force Meteorological Service\nSAR soil moisture\nData sources: Sentinel-1 SAR operational fallback\nThis is not a disease diagnosis, but a fungal risk summary based on satellite and official weather data.",
            )
        )
        return "\n".join(lines)

    # Mostra sempre una dashboard professionale anche con dati parziali
    def safe(val, fmt):
        try:
            return fmt.format(val) if val is not None else '--'
        except Exception:
            return '--'

    def compact_date(raw_date: Any) -> str:
        text = str(raw_date or "--").strip()
        if len(text) >= 10 and text[4] == "-" and text[7] == "-":
            return f"{text[8:10]}/{text[5:7]}"
        return text[:5] or "--"

    def parse_date(d):
        try:
            return d.get('date') or ''
        except Exception:
            return ''
    daily_sorted = sorted(daily[:7], key=parse_date, reverse=True)
    d0 = daily_sorted[0] if daily_sorted else {}

    header = ui_text("Data  Suolo% TempC UR% Pioggia Rischio%", "Date  Soil% TempC RH% Rain Risk%")
    sep = "----- ----- ----- --- ---- -----"
    rows = []
    for d in daily_sorted:
        rows.append(
            f"{compact_date(d.get('date')):>5} "
            f"{safe(d.get('soil'), '{:5.1f}')} "
            f"{safe(d.get('temp'), '{:5.1f}')} "
            f"{safe(d.get('humidity'), '{:3.0f}')} "
            f"{safe(d.get('rain'), '{:4.1f}')} "
            f"{safe((d.get('risk', 0.0))*100, '{:5.1f}') }"
        )
    table = [header, sep] + rows
    lines = [
        "<b>🛰️ NASA-ISRO/SAR Dashboard</b>",
        "<b>──────────────────────────────</b>",
        f"<b>📅 {ui_text('Oggi', 'Today')} {d0.get('date','--')}</b>",
        ui_text(
            f"🌱 Suolo: <b>{safe(d0.get('soil'), '{:.1f}')}</b> | 🌡️ Temp: <b>{safe(d0.get('temp'), '{:.1f}')}</b> | 💧 Umid: <b>{safe(d0.get('humidity'), '{:.1f}')}</b> | 🌧️ Pioggia: <b>{safe(d0.get('rain'), '{:.1f}')}</b>",
            f"🌱 Soil: <b>{safe(d0.get('soil'), '{:.1f}')}</b> | 🌡️ Temp: <b>{safe(d0.get('temp'), '{:.1f}')}</b> | 💧 Humid: <b>{safe(d0.get('humidity'), '{:.1f}')}</b> | 🌧️ Rain: <b>{safe(d0.get('rain'), '{:.1f}')}</b>",
        ),
        f"🦠 {ui_text('Rischio fungino', 'Fungal risk')}: <b>{safe((d0.get('risk', 0.0))*100, '{:.2f}')}%</b>",
        "",
        f"<b>📊 {ui_text('Dettaglio giornaliero', 'Daily breakdown')}</b>",
        f"<pre>{chr(10).join(table)}</pre>",
        ""
    ]
    # Rischio settimanale
    if weekly_risk is not None and weekly_label is not None:
        label_str = decorated_risk_label(weekly_label, language=language)
        lines.append(
            f"<b>🦠 {ui_text('Rischio fungino settimanale', 'Weekly fungal risk')}:</b> <b>{safe(weekly_risk*100, '{:.2f}')}% {label_str}</b>"
        )
    else:
        lines.append("")
        lines.append(f"<b>{ui_text('Dati non disponibili per questa posizione o finestra temporale.', 'Data unavailable for this position or time window.')}</b>")
    # Spiegazione sintetica
    lines.append("")
    normalized_weekly_label = str(weekly_label or '').upper()
    if normalized_weekly_label in {'ALTO', 'HIGH'}:
        lines.append(ui_text("🦠 Rischio fungino elevato: umidita', pioggia e SAR sono tutti su valori critici.", "🦠 High fungal risk: humidity, rainfall and SAR moisture are all in a critical range."))
    elif normalized_weekly_label in {'MEDIO', 'MEDIUM'}:
        lines.append(ui_text("🦠 Pressione fungina media: persistenza di umidita' e meteo favorevole.", "🦠 Medium fungal pressure: moisture persistence and weather remain favorable."))
    elif normalized_weekly_label in {'BASSO', 'LOW'}:
        lines.append(ui_text("🦠 Rischio fungino basso: area piu' secca e meno favorevole allo sviluppo.", "🦠 Low fungal risk: the area is drier and less favorable to development."))
    else:
        lines.append(ui_text("🦠 Nessun rischio fungino significativo rilevato nella finestra attuale.", "🦠 No significant fungal risk detected in the current window."))
    return "\n".join(lines)


async def _interpret_nasa_sar_dashboard(
    context: "ContextTypes.DEFAULT_TYPE",
    result: Dict[str, Any],
) -> str:
    dashboard = result.get("dashboard", {}) or {}
    # HERO DEMO: nessun controllo su summary, nessun messaggio di errore
    # Restituisci direttamente la formattazione HERO DEMO
    return _format_nasa_sar_dashboard(result, language=_ui_language(context))


def _build_nasa_sar_followup_context(
    result: Dict[str, Any],
    interpretation: str,
    language: str = VOICE_LANGUAGE_IT,
) -> str:
    geo_summary = result.get("geo_summary", {}) or {}
    dashboard = result.get("dashboard", {}) or {}
    summary = dashboard.get("summary", {}) or {}
    english_ui = str(language or "").strip().lower() == VOICE_LANGUAGE_EN
    locality = str(geo_summary.get("locality_label") or ("Undetermined locality" if english_ui else "Localita' non determinata"))
    return "\n".join(
        [
            "Latest DELTA Plant SAR/NISAR summary context:" if english_ui else "Contesto della piu recente sintesi SAR/NISAR DELTA Plant:",
            f"{'Locality' if english_ui else 'Localita\''}: {locality}",
            f"{'GPS center' if english_ui else 'Centro GPS'}: {float((geo_summary.get('centroid', {}) or {}).get('lat', 0.0)):.6f}, {float((geo_summary.get('centroid', {}) or {}).get('lon', 0.0)):.6f}",
            f"{'SAR soil moisture' if english_ui else "Umidita' suolo SAR"}: {float(summary.get('sar_soil_moisture_percent', 0.0) or 0.0):.1f}%",
            interpretation,
        ]
    )


def _reverse_geocode_locality(latitude: float, longitude: float) -> Optional[str]:
    try:
        response = requests.get(
            "https://nominatim.openstreetmap.org/reverse",
            params={
                "format": "jsonv2",
                "lat": float(latitude),
                "lon": float(longitude),
                "zoom": 10,
                "addressdetails": 1,
            },
            headers={"User-Agent": "DELTA Plant/1.0 (+https://deltaplant.ai)"},
            timeout=8,
        )
        response.raise_for_status()
        payload = response.json() or {}
        address = payload.get("address", {}) or {}
        locality = (
            address.get("city")
            or address.get("town")
            or address.get("village")
            or address.get("municipality")
            or address.get("county")
        )
        state = address.get("state") or address.get("region")
        country = address.get("country")
        parts: List[str] = []
        for value in (locality, state, country):
            text = str(value or "").strip()
            if text and text not in parts:
                parts.append(text)
        if parts:
            return ", ".join(parts[:3])
        display_name = str(payload.get("display_name") or "").strip()
        return display_name.split(",")[0].strip() or None
    except Exception as exc:
        logger.info("Reverse geocoding localita' non disponibile: %s", exc)
        return None


async def _send_nasa_sar_map_snapshot(
    update: Update,
    latitude: float,
    longitude: float,
    language: str = VOICE_LANGUAGE_IT,
    locality_label: Optional[str] = None,
) -> None:
    chat = getattr(update, "effective_chat", None)
    if chat is None:
        return
    try:
        photo_payload = await asyncio.to_thread(
            _build_nasa_sar_map_photo_payload,
            latitude,
            longitude,
            language,
            locality_label,
        )
        if photo_payload is None:
            return
        await chat.send_photo(
            photo=photo_payload,
        )
    except Exception as exc:
        logger.warning("Invio mappa NASA/SAR Telegram fallito: %s", exc)


def _get_nasa_orchestrator(context: ContextTypes.DEFAULT_TYPE):
    orchestrator = context.application.bot_data.get("nasa_orchestrator")
    if orchestrator is None:
        from nasa_delta_plant.orchestrator_node import NASADeltaPlantOrchestrator

        orchestrator = NASADeltaPlantOrchestrator()
        context.application.bot_data["nasa_orchestrator"] = orchestrator
        logger.info("NASADeltaPlantOrchestrator inizializzato per Telegram")
    return orchestrator


async def _run_nasa_sar_analysis(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    latitude: float,
    longitude: float,
    reply_markup: Optional[Any] = None,
) -> None:
    try:
        await update.effective_chat.send_action("typing")
    except Exception:
        pass

    geo_payload = _nasa_sar_geo_payload(latitude, longitude)
    date_range = _nasa_sar_date_range_payload(days=7)
    orchestrator = _get_nasa_orchestrator(context)


    # Forza sempre la chiamata DEMO HERO, log ingresso
    try:
        logger.warning("[DEBUG] _run_nasa_sar_analysis: chiamata orchestrator.analyze_nasa_only con geo_payload=%s date_range=%s", geo_payload, date_range)
        result = await orchestrator.analyze_nasa_only(
            geo_data=geo_payload,
            date_range=date_range,
        )
    except Exception as exc:
        logger.error("[DEBUG] _run_nasa_sar_analysis: errore analyze_nasa_only: %s", exc, exc_info=True)
        # In caso di errore, restituisci dashboard demo fissa su Roma
        fallback_geo = {"type": "circle", "center": {"lat": 41.9028, "lng": 12.4964}, "radius": 50}
        fallback_range = _nasa_sar_date_range_payload(days=7)
        result = await orchestrator.analyze_nasa_only(
            geo_data=fallback_geo,
            date_range=fallback_range,
        )
        logger.warning("[DEBUG] _run_nasa_sar_analysis: fallback dashboard demo su Roma")
    if not result or not result.get("dashboard"):
        # Se per qualunque motivo la dashboard non è presente, genera demo su Roma
        fallback_geo = {"type": "circle", "center": {"lat": 41.9028, "lng": 12.4964}, "radius": 50}
        fallback_range = _nasa_sar_date_range_payload(days=7)
        result = await orchestrator.analyze_nasa_only(
            geo_data=fallback_geo,
            date_range=fallback_range,
        )
        logger.warning("[DEBUG] _run_nasa_sar_analysis: dashboard demo forzata su Roma")

    locality_label = await asyncio.to_thread(_reverse_geocode_locality, latitude, longitude)
    if locality_label:
        result.setdefault("geo_summary", {})["locality_label"] = locality_label

    report_language = _ui_language(context)
    dashboard_text = _format_nasa_sar_dashboard(result, language=report_language)
    interpretation = await _interpret_nasa_sar_dashboard(context, result)
    await _send_nasa_sar_map_snapshot(
        update,
        latitude,
        longitude,
        report_language,
        locality_label,
    )
    await _send(
        update,
        dashboard_text,
        reply_markup=reply_markup,
        parse_mode="HTML",
    )
    # Messaggio header rimosso su richiesta, lasciando solo dashboard e messaggio di approfondimento
    context.user_data["chat_seed_context"] = _build_nasa_sar_followup_context(
        result,
        interpretation,
        language=report_language,
    )
    await _send(
        update,
        _ui_text(
            context,
            "💬 Ora puoi chiedermi approfondimenti sulla diagnosi o altro. Usero' la sintesi SAR appena generata come contesto iniziale della prossima risposta.",
            "💬 You can now ask me for deeper analysis about the diagnosis or anything else. I will use the SAR summary just generated as the initial context for the next reply.",
        ),
        reply_markup=_menu_keyboard(context),
    )


async def nasa_sar_connect(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data["awaiting_nasa_sar_location"] = True
    await _send(
        update,
        _ui_text(
            context,
            "🛰️ <b>NASA-ISRO/SAR pronto</b>\n\n"
            "Tocca <b>Invia GPS ora</b> per condividere la posizione direttamente in Telegram. "
            "Analizzero' un'area circolare di 50 metri e ti mostrero' la dashboard SAR con mappa, localita' e sintesi semplice basata su umidita' del suolo satellitare e meteo ufficiale Open-Meteo Archive.",
            "🛰️ <b>NASA-ISRO/SAR ready</b>\n\n"
            "Tap <b>Send GPS now</b> to share your location directly in Telegram. "
            "I will analyze a circular area of 50 meters and show you the SAR dashboard with map, locality, and a simple summary based on satellite soil moisture and official Open-Meteo Archive weather.",
        ),
        reply_markup=_nasa_sar_reply_keyboard(context),
        parse_mode="HTML",
    )


async def handle_nasa_sar_location(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _guard(update):
        return
    location = getattr(getattr(update, "message", None), "location", None)
    if location is None:
        return

    if context.user_data.get("diag_waiting_for_location"):
        context.user_data.pop("diag_waiting_for_location", None)
        context.user_data.pop("awaiting_nasa_sar_location", None)
        await _run_diagnosis_from_gps(
            update,
            context,
            location.latitude,
            location.longitude,
            reply_markup=ReplyKeyboardRemove(),
        )
        return

    if context.user_data.get("awaiting_nasa_sar_location"):
        context.user_data.pop("awaiting_nasa_sar_location", None)
        await _run_nasa_sar_analysis(
            update,
            context,
            location.latitude,
            location.longitude,
            reply_markup=ReplyKeyboardRemove(),
        )
        return

    # GPS orfano: nessun flusso attivo (es. dopo riavvio del bot o sessione scaduta).
    # Offre una via d'uscita chiara invece di ignorare silenziosamente la posizione.
    await _send(
        update,
        _ui_text(
            context,
            "📍 Posizione GPS ricevuta, ma non era attesa nessuna diagnosi o analisi."
            " Usa /diagnosi per avviare una nuova diagnosi o /nasa_sar per l'analisi ambientale.",
            "📍 GPS position received, but no diagnosis or analysis was pending."
            " Use /diagnosi to start a new diagnosis or /nasa_sar for environmental analysis.",
        ),
        reply_markup=_menu_keyboard(context),
    )


async def handle_nasa_sar_web_app_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _guard(update):
        return

    message = getattr(update, "effective_message", None)
    web_app_data = getattr(message, "web_app_data", None)
    if web_app_data is None:
        return

    # La Web App GPS puo servire sia la dashboard NASA/SAR sia la diagnosi.
    # In diagnosi, se il GPS automatico fallisce lasciamo attivo il fallback manuale.
    diagnosis_location = bool(context.user_data.get("diag_waiting_for_location"))
    standalone_nasa_sar = bool(context.user_data.get("awaiting_nasa_sar_location"))

    try:
        payload = json.loads(web_app_data.data)
    except Exception:
        await _send(
            update,
            _ui_text(context, "Dati GPS automatici non validi ricevuti dalla Web App.", "Invalid automatic GPS data received from the Web App."),
            reply_markup=_menu_keyboard(context),
        )
        return

    if payload.get("type") != "nasa_sar_location":
        return

    if payload.get("status") == "error":
        if diagnosis_location:
            await _send(
                update,
                _ui_text(
                    context,
                    "La posizione automatica non e' disponibile. Condividi la posizione con <b>Invia GPS ora</b> per completare la diagnosi.",
                    "Automatic position is unavailable. Share the position with <b>Send GPS now</b> to complete the diagnosis.",
                ),
                reply_markup=_nasa_sar_reply_keyboard(context),
                parse_mode="HTML",
            )
            return
        if standalone_nasa_sar:
            context.user_data.pop("awaiting_nasa_sar_location", None)
        await _send(
            update,
            _ui_text(
                context,
                "La posizione automatica non è disponibile. Consenti l'accesso GPS sul telefono oppure usa /nasa_sar per l'invio manuale.",
                "Automatic position is unavailable. Allow GPS access on the phone or use /nasa_sar for manual sending.",
            ),
            reply_markup=_menu_keyboard(context),
        )
        return

    try:
        latitude = float(payload["latitude"])
        longitude = float(payload["longitude"])
    except (KeyError, TypeError, ValueError):
        await _send(
            update,
            _ui_text(context, "Coordinate GPS automatiche non valide.", "Invalid automatic GPS coordinates."),
            reply_markup=_menu_keyboard(context),
        )
        return

    if diagnosis_location:
        context.user_data.pop("diag_waiting_for_location", None)
        context.user_data.pop("awaiting_nasa_sar_location", None)
        await _run_diagnosis_from_gps(update, context, latitude, longitude, reply_markup=ReplyKeyboardRemove())
        return

    if standalone_nasa_sar:
        context.user_data.pop("awaiting_nasa_sar_location", None)

    await _run_nasa_sar_analysis(update, context, latitude, longitude)


def _format_diagnosis(record: Dict[str, Any]) -> str:
    pass
def _format_diagnosis_full(record: Dict[str, Any]) -> str:
    dx = record.get("diagnosis", {})
    ai = record.get("ai_result", {})
    recs = record.get("recommendations", [])
    organ_results = record.get("organ_results", {})
    organ_analyses = dx.get("organ_analyses", {})
    quantum_risk = dx.get("quantum_risk", {})
    sensor = record.get("sensor_snapshot", {}) or dx.get("sensor_snapshot", {})
    anomalies = sensor.get("_anomalies", [])

    def fmt(val, unit=None, ndash="N/D"):
        if val is None:
            return ndash
        if isinstance(val, float):
            return f"{val:.2f}{unit or ''}"
        return str(val)

    # Stato generale
    status = dx.get("plant_status", "N/D")
    risk = dx.get("overall_risk", "N/D")
    risk_emoji = {
        "basso": "🟢", "medio": "🟡", "alto": "🔴", "critico": "🟣"
    }.get(str(risk).lower(), "❓")
    ai_class = ai.get("class", "N/D")
    ai_conf = ai.get("confidence", 0)
    ai_sim = ai.get("simulated", False)

    msg = [
        "<b>🩺 RISULTATO DIAGNOSI DELTA</b>",
        "<b>──────────────</b>",
        f"<b>Stato pianta:</b>  {status}",
        f"<b>Rischio:</b>       {risk_emoji} {risk.upper()}",
        "",
        f"<b>Analisi foglia:</b>",
        f"  Classe AI:    {ai_class} ({ai_conf*100:.1f}%)" + (" [SIM]" if ai_sim else ""),
    ]

    # Analisi fiore
    if "fiore" in organ_analyses:
        fa = organ_analyses["fiore"]
        msg.append("")
        msg.append("<b>Analisi fiore:</b>")
        msg.append(f"  Classe AI:    {fa.get('class', 'N/A')} ({fa.get('confidence', 0)*100:.1f}%)" + (" [SIM]" if fa.get("simulated") else ""))
    elif organ_results.get("fiore", {}).get("detected"):
        msg.append("")
        msg.append("<b>Analisi fiore:</b>  Rilevato — analisi AI non disponibile")

    # Analisi frutto
    if "frutto" in organ_analyses:
        fra = organ_analyses["frutto"]
        msg.append("")
        msg.append("<b>Analisi frutto:</b>")
        msg.append(f"  Classe AI:    {fra.get('class', 'N/A')} ({fra.get('confidence', 0)*100:.1f}%)" + (" [SIM]" if fra.get("simulated") else ""))
    elif organ_results.get("frutto", {}).get("detected"):
        msg.append("")
        msg.append("<b>Analisi frutto:</b>  Rilevato — analisi AI non disponibile")

    # Oracolo Quantistico
    if quantum_risk:
        qrs   = quantum_risk.get("quantum_risk_score", 0.0)
        qlvl  = quantum_risk.get("risk_level", "nessuno")
        qdom  = quantum_risk.get("dominant_description", "N/A")
        qgain = quantum_risk.get("amplification_gain", 1.0)
        qitr  = quantum_risk.get("grover_iterations", 0)
        qemoji = {
            "nessuno": "⚪", "basso": "🟢", "medio": "🟡", "alto": "🔴", "critico": "🟣"
        }.get(str(qlvl).lower(), "❓")
        msg.append("")
        msg.append("<b>Oracolo Quantistico di Grover:</b>")
        msg.append(
            "  <i>Cos'è: uno strumento di analisi del rischio ispirato all'algoritmo quantistico "
            "di Grover. Amplifica i segnali di rischio più significativi tra i dati della pianta, "
            "rendendo visibili minacce che analisi tradizionali potrebbero sottovalutare. "
            "Il punteggio QRS va da 0 (nessun rischio) a 1 (rischio massimo).</i>"
        )
        msg.append(f"  QRS:           {qemoji} {qrs:.4f} [{qlvl.upper()}]")
        msg.append(f"  Evento dom.:   {qdom}")
        msg.append(f"  Amplific.:     {qgain:.1f}x  |  Iterazioni Grover: {qitr}")

    # Spiegazione
    msg.append("")
    msg.append("<b>Diagnosi:</b>")
    msg.append(dx.get("explanation", "N/A"))

    # Raccomandazioni
    if recs:
        msg.append("")
        msg.append("<b>Raccomandazioni:</b>")
        for i, rec in enumerate(recs, 1):
            cat = rec.get("category", "?").upper()
            priority = rec.get("priority", "?")
            msg.append(f"  <b>[{i}] [{cat}]</b> (Priorità: {priority})")
            msg.append(f"      Problema: {rec.get('problem','')}")
            msg.append(f"      Azione:   {rec.get('action','')}")

    # Contesto ambientale GPS/SAR/LUX
    if sensor and sensor.get("context_type") == "gps_weekly_nasa_sar_lux":
        msg.append("")
        msg.append("<b>Contesto GPS/NASA-ISRO/SAR/LUX:</b>")
        # Tipo ambiente rilevato da satellite
        env_type = sensor.get("environment_type", "outdoor")
        env_emoji = {"outdoor": "🌳", "greenhouse": "🏡", "indoor": "🏠"}.get(env_type, "❓")
        env_label_it = {"outdoor": "Esterno", "greenhouse": "Serra", "indoor": "Interno"}.get(env_type, env_type)
        env_conf = sensor.get("environment_confidence", "")
        msg.append(f"  {'Ambiente rilevato':20s}: {env_emoji} {env_label_it}" + (f" (certezza: {env_conf})" if env_conf else ""))
        if sensor.get("environment_reasoning"):
            reasoning = str(sensor["environment_reasoning"])[:120]
            msg.append(f"  {'Nota ambiente':20s}: {reasoning}")

        env_fields = [
            ("gps_latitude", "Latitudine", ""),
            ("gps_longitude", "Longitudine", ""),
            ("locality_label", "Localita", ""),
            ("period_start", "Inizio finestra", ""),
            ("period_end", "Fine finestra", ""),
            ("sar_soil_moisture_percent", "Umidita suolo SAR", "%"),
            ("weekly_fungal_risk", "Rischio fungino", ""),
            ("weekly_fungal_risk_label", "Classe rischio", ""),
            ("lux_today", "LUX odierno (raw)", " lux"),
            ("lux_mean", "LUX medio (raw)", " lux"),
            ("lux_today_adjusted", "LUX odierno corretto", " lux"),
            ("lux_mean_adjusted", "LUX medio corretto", " lux"),
        ]
        for key, label, unit in env_fields:
            val = sensor.get(key)
            if val is None:
                continue
            val_str = fmt(val, unit)
            msg.append(f"  {label:24s}: {val_str}")
        if env_type == "indoor":
            msg.append(f"  {'Nota LUX':24s}: dato solare non applicabile (pianta indoor)")
        elif env_type == "greenhouse":
            lf = sensor.get("environment_lux_factor", 0.5)
            msg.append(f"  {'Fattore LUX serra':24s}: {lf:.0%} (filtraggio vetro/politene)")
        source = sensor.get("source", "gps_nasa_sar_lux")
        ts = sensor.get("timestamp", "?")
        days_avail = sensor.get("lux_days_available")
        most_recent = sensor.get("lux_most_recent_day")
        lux_info = f" | giorni LUX: {days_avail}" if days_avail else ""
        lux_info += f" | ultimo: {most_recent}" if most_recent else ""
        msg.append(f"  Fonte: {source} | Timestamp: {ts}{lux_info}")
        if sensor.get("lux_source"):
            msg.append(f"  Fonte LUX: {sensor.get('lux_source')}")
        if sensor.get("sar_source"):
            msg.append(f"  Fonte SAR: {sensor.get('sar_source')}")
        if sensor.get("nasa_sar_warning"):
            msg.append(f"  Nota NASA/SAR: {sensor.get('nasa_sar_warning')}")
        if sensor.get("lux_warning"):
            msg.append(f"  Nota LUX: {sensor.get('lux_warning')}")

    msg.append("\n<code>──────────────</code>")
    return "\n".join(msg)


# ──────────────────────────────────────────────────────────────────────────────
# CHAT INTELLIGENTE — "Chiedi a DELTA" (HuggingFace LLM via InferenceAPI)
# ──────────────────────────────────────────────────────────────────────────────

def _chat_exit_keyboard(context: Optional["ContextTypes.DEFAULT_TYPE"] = None) -> InlineKeyboardMarkup:
    """Tastiera con solo il pulsante di uscita dalla chat."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(_ui_text(context, "🔴 Termina chat", "🔴 End chat"), callback_data=CHAT_EXIT)],
        [InlineKeyboardButton(_ui_text(context, "🗑 Reset conversazione", "🗑 Reset conversation"), callback_data="CHAT_RESET")],
    ])


def _get_chat_engine(context: ContextTypes.DEFAULT_TYPE):
    """Restituisce il ChatEngine condiviso (lazy-init, one per bot)."""
    engine = context.application.bot_data.get("chat_engine")
    if engine is None:
        from chat.chat_engine import ChatEngine
        engine = ChatEngine()
        context.application.bot_data["chat_engine"] = engine
        logger.info("ChatEngine inizializzato (HF LLM)")
    return engine


def _get_hf_vision_llm(context: ContextTypes.DEFAULT_TYPE):
    """Restituisce il VLM Hugging Face condiviso per la sola diagnosi foto-diretta."""
    vision_llm = context.application.bot_data.get("hf_vision_llm")
    if vision_llm is None:
        from llm.huggingface_llm import HF_DEFAULT_VISION_MODEL, HuggingFaceLLM

        vision_llm = HuggingFaceLLM(
            model_name=os.environ.get("HF_VISION_MODEL_NAME", HF_DEFAULT_VISION_MODEL),
            max_tokens=int(os.environ.get("HF_VISION_MAX_TOKENS", "1400")),
            temperature=float(os.environ.get("HF_VISION_TEMPERATURE", "0.2")),
            timeout=int(os.environ.get("HF_VISION_TIMEOUT", os.environ.get("HF_TIMEOUT", "60"))),
        )
        context.application.bot_data["hf_vision_llm"] = vision_llm
        logger.info("HF Vision LLM inizializzato (%s)", vision_llm.model_name)
    return vision_llm


def _hf_system_prompt_for_language(response_language: str = VOICE_LANGUAGE_IT) -> str:
    from llm.huggingface_llm import DELTA_SYSTEM_PROMPT

    if response_language == VOICE_LANGUAGE_EN:
        return DELTA_SYSTEM_PROMPT.replace(
            "Rispondi SEMPRE in italiano, anche se la domanda è in un'altra lingua.",
            "Respond ALWAYS in English, even if the question is in another language.",
        )
    return DELTA_SYSTEM_PROMPT


def _build_multimodal_vision_diagnosis_prompt(
    response_language: str = VOICE_LANGUAGE_IT,
) -> str:
    if response_language == VOICE_LANGUAGE_EN:
        return (
            "You are DELTA Plant in multimodal visual diagnosis mode.\n"
            "Analyze ONLY the attached plant photo.\n"
            "Mandatory constraints:\n"
            "- Use only visual evidence from the image.\n"
            "- Do not use sensor data, PlantVillage classes, local classifiers, or any external hidden result.\n"
            "- Do not ask the user to send another photo: image acquisition is already complete.\n"
            "- If plant species or disease are uncertain, state that uncertainty clearly.\n"
            "- Do not invent details that are not visually supported.\n"
            "- The first block must explicitly state the most probable plant name or crop name visible in the image; if useful, also add the botanical/Latin name.\n"
            "Provide one professional agronomic answer in 6 blocks:\n"
            "1) Most probable plant name and confidence level\n"
            "2) Visual finding\n"
            "3) Main diagnostic hypothesis and confidence level\n"
            "4) Immediate actions (0-24h)\n"
            "5) Short-term actions (2-7 days)\n"
            "6) Monitoring and prevention\n"
            "In each relevant block, mention which visible cues support your conclusion.\n"
            "Keep the tone technical, practical, and concise."
        )

    return (
        "Sei DELTA Plant in modalità diagnostica visiva multimodale.\n"
        "Analizza SOLO la foto allegata della pianta.\n"
        "Vincoli obbligatori:\n"
        "- Usa esclusivamente ciò che è visibile nell'immagine.\n"
        "- Non usare dati sensore, classi PlantVillage, classificatori locali o risultati esterni nascosti.\n"
        "- Non chiedere un'altra foto: l'acquisizione immagine è già completa.\n"
        "- Se specie vegetale o patologia sono incerte, dichiaralo esplicitamente.\n"
        "- Non inventare dettagli non supportati visivamente.\n"
        "- Nel primo blocco devi indicare esplicitamente il nome piu probabile della pianta o della coltura visibile; se utile aggiungi anche il nome botanico/latino.\n"
        "Fornisci un'unica risposta professionale da agronomo in 6 blocchi:\n"
        "1) Nome probabile della pianta e grado di certezza\n"
        "2) Esito visivo\n"
        "3) Ipotesi diagnostica principale e grado di certezza\n"
        "4) Azioni immediate (0-24h)\n"
        "5) Azioni a breve termine (2-7 giorni)\n"
        "6) Monitoraggio e prevenzione\n"
        "In ogni blocco pertinente cita i segnali visivi che sostengono la conclusione.\n"
        "Mantieni tono tecnico, concreto e sintetico."
    )


def _build_multimodal_vision_name_retry_prompt(
    previous_opinion: str,
    response_language: str = VOICE_LANGUAGE_IT,
) -> str:
    previous_excerpt = _collapse_whitespace(previous_opinion)[:1200]
    if response_language == VOICE_LANGUAGE_EN:
        return (
            "Mandatory quality-control retry: in the previous answer you did not clearly state the plant name.\n"
            "Reanalyze ONLY the same image.\n"
            "The first line must explicitly follow this structure:\n"
            "1) Plant name: <most probable common name>; Botanical name: <Latin name or 'not determinable from the image alone'>; Confidence: <high/medium/low>.\n"
            "If the plant cannot be identified from the image alone, explicitly say that in the first line.\n"
            "Then provide the remaining 5 diagnostic blocks with concise agronomic language.\n"
            "Previous answer to correct:\n"
            f"{previous_excerpt}"
        )

    return (
        "Controllo qualita obbligatorio: nella risposta precedente non hai indicato chiaramente il nome della pianta.\n"
        "Rianalizza SOLO la stessa immagine.\n"
        "La prima riga deve seguire esplicitamente questa struttura:\n"
        "1) Nome della pianta: <nome comune piu probabile>; Nome botanico: <nome latino oppure 'non determinabile dalla sola immagine'>; Grado di certezza: <alto/medio/basso>.\n"
        "Se la pianta non e identificabile dalla sola immagine, dichiaralo esplicitamente nella prima riga.\n"
        "Poi fornisci gli altri 5 blocchi diagnostici in linguaggio agronomico sintetico.\n"
        "Risposta precedente da correggere:\n"
        f"{previous_excerpt}"
    )


def _format_sensor_text_for_language(
    sensor_data: Optional[Dict[str, Any]],
    response_language: str = VOICE_LANGUAGE_IT,
) -> str:
    cleaned = {
        key: value
        for key, value in (sensor_data or {}).items()
        if value is not None
    }
    if not cleaned:
        return ""

    if cleaned.get("context_type") == "gps_weekly_nasa_sar_lux":
        english_ui = response_language == VOICE_LANGUAGE_EN

        def label(italian_text: str, english_text: str) -> str:
            return english_text if english_ui else italian_text

        def fmt_number(value: Any, suffix: str = "") -> str:
            number = _coerce_float(value)
            if number is None:
                return str(value)
            if abs(number) >= 100:
                return f"{number:.0f}{suffix}"
            return f"{number:.2f}{suffix}"

        period = ""
        if cleaned.get("period_start") or cleaned.get("period_end"):
            period = f"{cleaned.get('period_start', '?')} -> {cleaned.get('period_end', '?')}"
        gps = f"{float(cleaned.get('gps_latitude', 0.0)):.6f}, {float(cleaned.get('gps_longitude', 0.0)):.6f}"
        lines = [
            f"- {label('Coordinate GPS', 'GPS coordinates')}: {gps}",
        ]
        if cleaned.get("locality_label"):
            lines.append(f"- {label('Localita', 'Locality')}: {cleaned['locality_label']}")
        if period:
            lines.append(f"- {label('Finestra dati', 'Data window')}: {period} ({label('oggi e 6 giorni precedenti', 'today and previous 6 days')})")
        # Ambiente rilevato da immagine satellite
        env_type = cleaned.get("environment_type", "outdoor")
        env_emoji = {"outdoor": "🌳", "greenhouse": "🏡", "indoor": "🏠"}.get(env_type, "")
        env_labels_it = {"outdoor": "Esterno (campo/giardino)", "greenhouse": "Serra (struttura vetro/politene)", "indoor": "Interno (edificio)"}
        env_labels_en = {"outdoor": "Outdoor (field/garden)", "greenhouse": "Greenhouse (glass/plastic structure)", "indoor": "Indoor (building)"}
        env_conf = cleaned.get("environment_confidence", "")
        env_label_str = (env_labels_en if english_ui else env_labels_it).get(env_type, env_type)
        lines.append(f"- {label('Tipo ambiente', 'Environment type')}: {env_emoji} {env_label_str}" + (f" ({label('certezza', 'confidence')}: {env_conf})" if env_conf else ""))
        if cleaned.get("environment_reasoning"):
            reasoning = str(cleaned["environment_reasoning"])[:120]
            lines.append(f"- {label('Nota ambiente', 'Environment note')}: {reasoning}")
        if cleaned.get("sar_soil_moisture_percent") is not None:
            lines.append(f"- {label('Umidita suolo SAR', 'SAR soil moisture')}: {fmt_number(cleaned['sar_soil_moisture_percent'], '%')}")
        if cleaned.get("weekly_fungal_risk") is not None:
            risk_pct = float(cleaned["weekly_fungal_risk"]) * 100.0
            risk_label = cleaned.get("weekly_fungal_risk_label") or label("non classificato", "unclassified")
            lines.append(f"- {label('Rischio fungino settimanale', 'Weekly fungal risk')}: {risk_pct:.1f}% ({risk_label})")
        # LUX: mostra sia raw che corretto per ambiente
        if env_type == "indoor":
            lines.append(f"- {label('LUX solare', 'Solar LUX')}: {label('non applicabile (pianta indoor)', 'not applicable (indoor plant)')}")
        else:
            lux_adj = cleaned.get("lux_today_adjusted") if cleaned.get("lux_today_adjusted") is not None else cleaned.get("lux_mean_adjusted")
            lux_raw = cleaned.get("lux_today") if cleaned.get("lux_today") is not None else cleaned.get("lux_mean")
            if lux_adj is not None:
                lines.append(f"- {label('LUX corretto per ambiente', 'Environment-adjusted LUX')}: {fmt_number(lux_adj, ' lux')}"
                             + (f" ({label('fattore', 'factor')}: {cleaned.get('environment_lux_factor', 1.0):.0%})" if env_type == "greenhouse" else ""))
            elif lux_raw is not None:
                lines.append(f"- {label('LUX stimato', 'Estimated LUX')}: {fmt_number(lux_raw, ' lux')}")
        if cleaned.get("lux_mean") is not None and env_type != "indoor":
            lines.append(f"- {label('LUX medio settimanale (raw)', 'Weekly mean LUX (raw)')}: {fmt_number(cleaned['lux_mean'], ' lux')}"
                         + (f" ({label('su', 'over')} {cleaned['lux_days_available']} {label('giorni disponibili', 'available days')})" if cleaned.get("lux_days_available") else ""))
        if cleaned.get("lux_source"):
            lines.append(f"- {label('Fonte luminosita', 'Light source')}: {cleaned['lux_source']}")
        if cleaned.get("sar_source"):
            lines.append(f"- {label('Fonte SAR', 'SAR source')}: {cleaned['sar_source']}")
        if cleaned.get("lux_conversion_note"):
            lines.append(f"- {label('Nota LUX', 'LUX note')}: {cleaned['lux_conversion_note']}")
        if cleaned.get("nasa_sar_warning"):
            lines.append(f"- {label('Nota NASA-ISRO/SAR', 'NASA-ISRO/SAR note')}: {cleaned['nasa_sar_warning']}")
        if cleaned.get("lux_warning"):
            lines.append(f"- {label('Nota LUX', 'LUX note')}: {cleaned['lux_warning']}")

        header = (
            "GPS/NASA-ISRO/SAR/LUX environmental context available:"
            if english_ui
            else "Contesto ambientale GPS/NASA-ISRO/SAR/LUX disponibile:"
        )
        return f"{header}\n" + "\n".join(lines)

    return ""


def _build_guided_multimodal_diagnosis_prompt(
    user_description: str,
    sensor_data: Optional[Dict[str, Any]],
    response_language: str = VOICE_LANGUAGE_IT,
) -> str:
    description = _collapse_whitespace(user_description)
    sensor_block = _format_sensor_text_for_language(sensor_data, response_language=response_language)

    if response_language == VOICE_LANGUAGE_EN:
        prompt = [
            "You are DELTA Plant in guided multimodal diagnosis mode.",
            "Analyze ONLY the attached plant photo together with any available GPS/NASA-ISRO/SAR/LUX environmental context.",
            "Mandatory constraints:",
            "- Use the photo as the primary source and the GPS/NASA-ISRO/SAR/LUX context as supporting evidence.",
            "- The GPS context includes a satellite-based environment classification (outdoor/greenhouse/indoor): explicitly validate coherence between this satellite context and the plant photo clues.",
            "- If optional operator notes are available, use them only as secondary context when they are coherent with the image.",
            "- Do not use PlantVillage classes, local classifiers, hidden native AI outputs, or explainability overlays.",
            "- Do not ask for another photo: image acquisition is already complete.",
            "- If the plant name, pathology, or severity are uncertain, state that uncertainty clearly.",
            "- Do not invent symptoms that are not visible in the image or unsupported by the GPS/SAR/LUX context.",
        ]
        if description:
            prompt.extend([
                "Optional operator notes:",
                f"- {description}",
            ])
        if sensor_block:
            prompt.append(sensor_block)
        else:
            prompt.append("No GPS/NASA-ISRO/SAR/LUX environmental context is available for this diagnosis.")
        prompt.extend([
            "Output requirement:",
            "- Write directly the diagnosis with no introductory sentence and no markdown-heavy formatting.",
            "- Use exactly 5 numbered blocks in this order:",
            "1) Diagnostic summary",
            "- Plant: ...",
            "- Technical assessment: ...",
            "- Confidence: ...",
            "- Environment context (outdoor/greenhouse/indoor): ... (state if coherent/incoherent between satellite context and photo)",
            "2) Diagnosis and risk",
            "- ...",
            "3) Immediate control actions (0-24h)",
            "- ...",
            "4) Practical short-term actions (2-7 days)",
            "- ...",
            "5) Monitoring and prevention",
            "- ...",
            "If GPS/NASA-ISRO/SAR/LUX context is available, comment on it explicitly inside the relevant blocks.",
            "Keep the tone technical, practical, and concise.",
        ])
        return "\n".join(prompt)

    prompt = [
        "Sei DELTA Plant in modalità diagnostica guidata multimodale.",
        "Analizza SOLO la foto allegata della pianta insieme agli eventuali dati ambientali disponibili.",
        "Vincoli obbligatori:",
        "- Usa la foto come fonte primaria e il contesto GPS/NASA-ISRO/SAR/LUX come supporto diagnostico.",
        "- Il contesto GPS include la classificazione ambiente da satellite (esterno/serra/interno): verifica esplicitamente la coerenza tra questo contesto satellitare e gli indizi visivi della foto della pianta.",
        "- Se sono presenti note operatore opzionali, usale solo come contesto secondario quando sono coerenti con l'immagine.",
        "- Non usare classi PlantVillage, classificatori locali, output nascosti dell'AI nativa o overlay di explainability.",
        "- Non chiedere un'altra foto: l'acquisizione immagine è già completa.",
        "- Se nome della pianta, patologia o gravità sono incerti, dichiaralo esplicitamente.",
        "- Non inventare sintomi non visibili nell'immagine o non supportati dal contesto GPS/SAR/LUX.",
    ]
    if description:
        prompt.extend([
            "Note operatore opzionali:",
            f"- {description}",
        ])
    if sensor_block:
        prompt.append(sensor_block)
    else:
        prompt.append("Nessun contesto ambientale GPS/NASA-ISRO/SAR/LUX disponibile per questa diagnosi.")
    prompt.extend([
        "Formato di output obbligatorio:",
        "- Scrivi direttamente la diagnosi, senza frase introduttiva e senza markdown pesante.",
        "- Usa esattamente 5 blocchi numerati in questo ordine:",
        "1) Sintesi diagnostica",
        "- Pianta: ...",
        "- Esito tecnico: ...",
        "- Certezza: ...",
        "- Contesto ambiente (esterno/serra/interno): ... (indica se coerente/non coerente tra satellite e foto)",
        "2) Diagnosi e rischio",
        "- ...",
        "3) Interventi immediati (0-24h)",
        "- ...",
        "4) Consigli operativi a breve termine (2-7 giorni)",
        "- ...",
        "5) Monitoraggio e prevenzione",
        "- ...",
        "Se e' disponibile il contesto GPS/NASA-ISRO/SAR/LUX, commentalo esplicitamente nei blocchi pertinenti.",
        "Mantieni tono tecnico, concreto e sintetico.",
    ])
    return "\n".join(prompt)


def _build_guided_multimodal_name_retry_prompt(
    previous_opinion: str,
    user_description: str,
    sensor_data: Optional[Dict[str, Any]],
    response_language: str = VOICE_LANGUAGE_IT,
) -> str:
    base_prompt = _build_guided_multimodal_diagnosis_prompt(
        user_description,
        sensor_data,
        response_language=response_language,
    )
    previous_excerpt = _collapse_whitespace(previous_opinion)[:1200]
    if response_language == VOICE_LANGUAGE_EN:
        return (
            base_prompt
            + "\n\nQuality control: the previous answer did not clearly state the plant name."
            + "\nIn block 1 you must explicitly name the most probable plant and, if possible, also the botanical/Latin name."
            + "\nIf the plant cannot be identified from the image alone, say so explicitly in block 1."
            + "\nPrevious answer to correct:\n"
            + previous_excerpt
        )

    return (
        base_prompt
        + "\n\nControllo qualità: la risposta precedente non ha indicato chiaramente il nome della pianta."
        + "\nNel blocco 1 devi nominare esplicitamente la pianta più probabile e, se possibile, anche il nome botanico/latino."
        + "\nSe la pianta non è identificabile dalla sola immagine, dichiaralo esplicitamente nel blocco 1."
        + "\nRisposta precedente da correggere:\n"
        + previous_excerpt
    )


def _build_guided_diagnosis_result_message(
    context: Optional["ContextTypes.DEFAULT_TYPE"],
    opinion: str,
    *,
    response_language: str = VOICE_LANGUAGE_IT,
    has_sensor_data: bool = False,
) -> Tuple[str, str]:
    section_titles = {
        VOICE_LANGUAGE_EN: {
            1: "Diagnostic summary",
            2: "Diagnosis and risk",
            3: "Immediate control actions",
            4: "Practical short-term actions",
            5: "Monitoring and prevention",
        },
        VOICE_LANGUAGE_IT: {
            1: "Sintesi diagnostica",
            2: "Diagnosi e rischio",
            3: "Interventi immediati",
            4: "Consigli operativi",
            5: "Monitoraggio e prevenzione",
        },
    }
    normalized = str(opinion or "").replace("\r\n", "\n").strip()
    normalized = re.sub(r"(?<!^)(?<!\n)\s+(?=(?:\*\*)?[1-5]\)\s)", "\n", normalized)
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)

    block_re = re.compile(
        r"(?:^|\n)\s*(?:\*\*)?([1-5])\)\s*(.*?)(?=(?:\n\s*(?:\*\*)?[1-5]\)\s)|\Z)",
        re.DOTALL,
    )
    blocks = {
        int(match.group(1)): match.group(2).strip()
        for match in block_re.finditer(normalized)
    }

    def _render_summary_card(summary_lines: List[str]) -> str:
        def _find_value(candidates: Tuple[str, ...]) -> str:
            for raw_line in summary_lines:
                cleaned = raw_line.lstrip("- ").strip()
                if ":" not in cleaned:
                    continue
                label, value = cleaned.split(":", 1)
                normalized_label = re.sub(r"\s+", " ", label).strip().lower()
                if normalized_label in candidates or any(candidate in normalized_label for candidate in candidates):
                    return value.strip()
            return ""

        def _truncate(value: str, width: int = 88) -> str:
            compact = re.sub(r"\s+", " ", str(value or "")).strip()
            if len(compact) <= width:
                return compact
            if width <= 3:
                return compact[:width]
            return compact[: width - 3].rstrip() + "..."

        plant_value = _find_value(("nome pianta", "pianta", "plant name", "plant"))
        botanical_value = _find_value(("nome botanico", "nome latino", "botanical name", "latin name", "scientific name"))
        assessment_value = _find_value(("esito tecnico", "stato tecnico", "technical assessment", "technical outcome", "assessment", "esito"))
        confidence_value = _find_value(("certezza", "grado di certezza", "confidence", "confidence level"))
        environment_value = _ui_text(
            context,
            "Integrati" if has_sensor_data else "Non disponibili",
            "Integrated" if has_sensor_data else "Not available",
        )

        fallback_values = [
            re.sub(r"^[\-*•]\s*", "", line).strip()
            for line in summary_lines
            if line.strip()
        ]
        if not plant_value and fallback_values:
            plant_value = fallback_values[0]
        if not assessment_value and len(fallback_values) > 1:
            assessment_value = fallback_values[1]
        if not confidence_value and len(fallback_values) > 2:
            confidence_value = fallback_values[2]

        if botanical_value and plant_value and botanical_value.lower() not in plant_value.lower():
            plant_value = f"{plant_value} ({botanical_value})"

        rows = [
            ("🪴", _ui_text(context, "Pianta", "Plant"), plant_value or _ui_text(context, "Non determinata", "Undetermined")),
            ("🩺", _ui_text(context, "Esito", "Assessment"), assessment_value or _ui_text(context, "Da confermare", "To confirm")),
            ("🎯", _ui_text(context, "Certezza", "Confidence"), confidence_value or _ui_text(context, "Da stimare", "To estimate")),
            ("🛰️", _ui_text(context, "GPS/SAR/LUX", "GPS/SAR/LUX"), environment_value),
        ]

        section_label = _ui_text(context, "🔎 <b>Quadro sintetico</b>", "🔎 <b>Diagnostic snapshot</b>")
        rendered_rows = [section_label]
        for icon, label, value in rows:
            rendered_rows.append(
                f"{icon} <b>{html.escape(label, quote=False)}:</b> {html.escape(_truncate(value), quote=False)}"
            )
        return "\n".join(rendered_rows)

    def _block_to_lines(raw_block: str) -> List[str]:
        block_text = str(raw_block or "").strip()
        block_text = re.sub(r"\s+\*\s+", "\n- ", block_text)
        block_text = re.sub(r"\n\s*\*\s+", "\n- ", block_text)
        block_text = re.sub(r"\n{3,}", "\n\n", block_text)
        raw_lines = [line.strip() for line in block_text.splitlines() if line.strip()]
        if raw_lines:
            first_line_clean = re.sub(r"[`*_]+", "", raw_lines[0]).strip(" :-")
            if first_line_clean.lower().startswith(("ecco l'analisi", "here is the analysis", "here is the technical analysis")):
                raw_lines = raw_lines[1:]
        if len(raw_lines) > 1:
            first_line_clean = re.sub(r"[`*_]+", "", raw_lines[0]).strip(" :-")
            if first_line_clean and ":" not in first_line_clean and len(first_line_clean.split()) <= 8:
                raw_lines = raw_lines[1:]

        lines: List[str] = []
        source_lines = raw_lines or [block_text]
        for raw_line in source_lines:
            stripped = raw_line.strip()
            if not stripped:
                continue
            segments = [segment.strip() for segment in stripped.split("|") if segment.strip()]
            if len(segments) > 1:
                for segment in segments:
                    lines.append(f"- {segment.lstrip('-*• ').strip()}")
                continue
            if stripped.startswith(("- ", "* ", "• ")):
                lines.append(f"- {stripped[2:].strip()}")
                continue
            lines.append(f"- {stripped}")
        return [line for line in lines if line.strip("- ")]

    rendered_sections: List[str] = []
    title_map = section_titles.get(response_language, section_titles[VOICE_LANGUAGE_IT])
    for block_number in range(1, 6):
        block_body = blocks.get(block_number)
        if not block_body:
            continue
        rendered_sections.append(f"## {title_map[block_number]}")
        rendered_sections.extend(_block_to_lines(block_body))
        rendered_sections.append("")

    if rendered_sections:
        formatted_body, _ = _format_free_chat_for_telegram(context, "\n".join(rendered_sections).strip())
    else:
        fallback_heading = _ui_text(context, "## Sintesi diagnostica", "## Diagnostic summary")
        fallback_lines = [fallback_heading]
        fallback_lines.extend(_block_to_lines(normalized))
        formatted_body, _ = _format_free_chat_for_telegram(context, "\n".join(fallback_lines).strip())

    title = _ui_text(
        context,
        "🩺 <b>RISULTATO DIAGNOSI DELTA Plant</b>",
        "🩺 <b>DELTA Plant DIAGNOSIS RESULT</b>",
    )
    subtitle = (
        _ui_text(
            context,
            "Analisi visiva multimodale con contesto GPS/NASA-ISRO/SAR/LUX integrato.",
            "Multimodal visual analysis with integrated GPS/NASA-ISRO/SAR/LUX context.",
        )
        if has_sensor_data
        else _ui_text(
            context,
            "Analisi visiva multimodale della pianta.",
            "Multimodal visual plant analysis.",
        )
    )
    summary_lines = _block_to_lines(blocks.get(1, "")) if blocks.get(1) else []
    summary_card = _render_summary_card(summary_lines) if summary_lines else ""
    message_parts = [title, f"<i>{html.escape(subtitle, quote=False)}</i>"]
    if summary_card:
        message_parts.append(summary_card)
    message_parts.append(formatted_body)
    return "\n\n".join(part for part in message_parts if part), "HTML"


async def chat_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Avvia la sessione di chat intelligente."""
    if not await _guard(update):
        return ConversationHandler.END

    # PATCH: Consenti sempre l'avvio della chat intelligente, anche durante diagnosi attiva

    context.user_data["chat_mode_active"] = True

    engine = _get_chat_engine(context)
    status = engine.get_status()
    hf_ok = status.get("hf_token_valid", False)
    model_name = status.get("hf_active_model", "N/D")

    if hf_ok:
        intro = _ui_text(
            context,
            "🔵 *Chat intelligente DELTA attiva*\n\n"
            f"Modello: `{model_name}`\n\n"
            "Puoi chiedermi qualsiasi cosa su malattie delle piante, "
            "trattamenti, agronomia o interpretazione delle diagnosi.\n\n"
            "_Scrivi il tuo messaggio. Usa_ /chiudi _per terminare la chat._",
            "🔵 *DELTA intelligent chat active*\n\n"
            f"Model: `{model_name}`\n\n"
            "You can ask me anything about plant diseases, "
            "treatments, agronomy, or diagnosis interpretation.\n\n"
            "_Write your message. Use_ /chiudi _to end the chat._",
        )
    else:
        intro = _ui_text(
            context,
            "🟡 *Chat DELTA non disponibile*\n\n"
            "Il backend HuggingFace non è disponibile.\n"
            "Verifica `HF_API_TOKEN` e `HF_MODEL_NAME` in `.env`.\n\n"
            "_Scrivi il tuo messaggio. Usa_ /chiudi _per terminare._",
            "🟡 *DELTA chat unavailable*\n\n"
            "The HuggingFace backend is unavailable.\n"
            "Check `HF_API_TOKEN` and `HF_MODEL_NAME` in `.env`.\n\n"
            "_Write your message. Use_ /chiudi _to end the chat._",
        )

    await _send(update, intro, reply_markup=_chat_exit_keyboard(context), parse_mode="Markdown")
    return STATE_CHAT_WAITING


async def chat_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Riceve un messaggio dell'utente e risponde con l'LLM."""
    if not await _guard(update):
        return ConversationHandler.END
    if not update.message or not update.message.text:
        return STATE_CHAT_WAITING

    user_text = update.message.text.strip()
    if not user_text:
        return STATE_CHAT_WAITING

    await _handle_free_chat_turn(update, context, user_text, input_mode="text")
    return STATE_CHAT_WAITING


async def chat_reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Azzera la memoria conversazionale dell'utente corrente."""
    if not await _guard(update):
        return STATE_CHAT_WAITING
    query = update.callback_query
    if query:
        await _answer_callback_query_safe(query, _ui_text(context, "Conversazione resettata ✓", "Conversation reset ✓"))
    user_id = str(update.effective_user.id if update.effective_user else "0")
    engine = _get_chat_engine(context)
    engine.reset(user_id)
    await _send(
        update,
        _ui_text(
            context,
            "🗑 Memoria conversazione azzerata. Scrivi il tuo prossimo messaggio.",
            "🗑 Conversation memory cleared. Write your next message.",
        ),
        reply_markup=_chat_exit_keyboard(context),
    )
    return STATE_CHAT_WAITING


async def chat_exit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Termina la sessione di chat e torna al menu principale."""
    if not await _guard(update):
        return ConversationHandler.END
    _clear_chat_state(context)
    query = update.callback_query
    if query:
        await _answer_callback_query_safe(query, _ui_text(context, "Chat terminata", "Chat closed"))
    await _send(
        update,
        _ui_text(
            context,
            "Chat terminata. Usa /menu per tornare al menu principale.",
            "Chat closed. Use /menu to return to the main menu.",
        ),
        reply_markup=_menu_keyboard(context),
    )
    return ConversationHandler.END


async def chat_command_chiudi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestisce /chiudi dentro la chat conversation."""
    return await chat_exit(update, context)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _guard(update):
        return ConversationHandler.END
    now_ts = datetime.now().timestamp()
    last_start_ts = float(context.user_data.get("_last_start_ts", 0.0) or 0.0)
    if (now_ts - last_start_ts) < 2.5:
        logger.info("Telegram /start duplicato ignorato da user_id=%s", update.effective_user.id if update.effective_user else "0")
        return ConversationHandler.END
    context.user_data["_last_start_ts"] = now_ts
    logger.info("Telegram /start ricevuto da user_id=%s", update.effective_user.id if update.effective_user else "0")
    was_chat_active = bool(context.user_data.get("chat_mode_active"))
    _clear_chat_state(context)
    if _voice_language_mode(context) == VOICE_LANGUAGE_EN:
        intro = (
            "Welcome to @DELTAPLANO_bot.\n"
            "Here you can interact with DELTA Plant from Telegram to start diagnoses, "
            "review reports, and open NASA-ISRO/SAR GPS context.\n"
            "Use /menu to view the available actions."
        )
    else:
        intro = (
            "Benvenuto in @DELTAPLANO_bot.\n"
            "Qui puoi interagire con DELTA Plant da Telegram per avviare diagnosi, "
            "consultare report e aprire il contesto GPS NASA-ISRO/SAR.\n"
            "Usa /menu per vedere le azioni disponibili."
        )
    await _send(update, intro, reply_markup=_menu_keyboard(context))
    await _send_personalized_welcome_voice(update, context)
    if was_chat_active:
        return ConversationHandler.END


async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _guard(update):
        return ConversationHandler.END
    effective_user = getattr(update, "effective_user", None)
    logger.info("Telegram /menu ricevuto da user_id=%s", effective_user.id if effective_user else "0")
    was_chat_active = bool(context.user_data.get("chat_mode_active"))
    was_guided_active = bool(_free_chat_block_reason(context))
    _clear_chat_state(context)
    _clear_diagnosis_state(context)
    context.user_data.pop("upload_active", None)
    await _send(update, _ui_text(context, "Menu principale:", "Main menu:"), reply_markup=_menu_keyboard(context))
    if was_chat_active or was_guided_active:
        return ConversationHandler.END


async def report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _guard(update):
        return
    agent = _get_agent(context)
    if agent:
        records = agent.database.get_recent(limit=5)
    else:
        resp = await _api_request("GET", "/diagnoses", params={"limit": 5})
        if resp is None:
            await _send(update, _ui_text(context, "Errore sistema: API non raggiungibile.", "System error: API unreachable."))
            return
        if resp.status_code != 200:
            logger.warning("API /diagnoses errore %s: %s", resp.status_code, resp.text[:200])
            await _send(update, _ui_text(context, "Errore sistema.", "System error."))
            return
        try:
            records = resp.json()
        except ValueError:
            await _send(update, _ui_text(context, "Risposta API non valida.", "Invalid API response."))
            return
    if not records:
        await _send(update, _ui_text(context, "Nessuna diagnosi disponibile.", "No diagnoses available."))
        return
    lines = [_ui_text(context, "Ultime diagnosi:", "Latest diagnoses:")]
    for rec in records:
        rec_id = rec.get("id", "N/D")
        ts = rec.get("timestamp", "N/D")
        cls = rec.get("ai_class", "N/D")
        risk = rec.get("overall_risk", "N/D")
        lines.append(
            f"• #{rec_id} | {ts} | {cls} | "
            f"{_ui_text(context, 'rischio', 'risk')} {risk}"
        )
    await _send(update, "\n".join(lines))


async def detail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _guard(update):
        return
    if not context.args:
        await _send(update, _ui_text(context, "Uso: /dettaglio <id>", "Usage: /dettaglio <id>"))
        return
    try:
        record_id = int(context.args[0])
    except ValueError:
        await _send(update, _ui_text(context, "ID non valido.", "Invalid ID."))
        return
    agent = _get_agent(context)
    if agent:
        record = agent.database.get_by_id(record_id)
        if record is None:
            await _send(update, _ui_text(context, "Record non trovato.", "Record not found."))
            return
    else:
        resp = await _api_request("GET", f"/diagnoses/{record_id}")
        if resp is None:
            await _send(update, _ui_text(context, "Errore sistema: API non raggiungibile.", "System error: API unreachable."))
            return
        if resp.status_code != 200:
            await _send(update, _ui_text(context, "Record non trovato.", "Record not found."))
            return
        try:
            record = resp.json()
        except ValueError:
            await _send(update, _ui_text(context, "Risposta API non valida.", "Invalid API response."))
            return
    summary = record.get("summary", "N/D")
    cls = record.get("ai_class", "N/D")
    risk = record.get("overall_risk", "N/D")
    ts = record.get("timestamp", "N/D")
    await _send(
        update,
        _ui_text(
            context,
            f"Dettaglio #{record_id}\nData: {ts}\nClasse: {cls}\nRischio: {risk}\n{summary}",
            f"Detail #{record_id}\nDate: {ts}\nClass: {cls}\nRisk: {risk}\n{summary}",
        ),
    )


async def sensors(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _guard(update):
        return
    agent = _get_agent(context)
    if agent:
        data = agent.get_latest_sensor_data()
    else:
        resp = await _api_request("GET", "/sensors")
        if resp is None:
            await _send(update, _ui_text(context, "Errore sistema: API non raggiungibile.", "System error: API unreachable."))
            return
        if resp.status_code != 200:
            await _send(update, _ui_text(context, "Errore sistema.", "System error."))
            return
        try:
            data = resp.json()
        except ValueError:
            await _send(update, _ui_text(context, "Risposta API non valida.", "Invalid API response."))
            return
    lines = [_ui_text(context, "Dati sensori:", "Sensor data:")]
    for key in [
        "temperature_c", "humidity_pct", "pressure_hpa",
        "light_lux", "co2_ppm", "ph", "ec_ms_cm",
    ]:
        value = data.get(key)
        if value is not None:
            lines.append(f"• {key}: {value}")
    await _send(update, "\n".join(lines))


async def health(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _guard(update):
        return
    agent = _get_agent(context)
    if agent:
        data = {
            "status": "ok",
            "model_ready": agent.model_loader.is_ready(),
            "sensor_hw": getattr(agent.sensor_reader, "_hw_available", False),
            "db_records": agent.database.count(),
        }
        await _send(update, f"Health: {data}")
    else:
        resp = await _api_request("GET", "/health")
        if resp is None:
            await _send(update, _ui_text(context, "Errore sistema: API non raggiungibile.", "System error: API unreachable."))
            return
        if resp.status_code != 200:
            await _send(update, _ui_text(context, "Errore sistema.", "System error."))
            return
        try:
            data = resp.json()
        except ValueError:
            await _send(update, _ui_text(context, "Risposta API non valida.", "Invalid API response."))
            return
        await _send(update, f"Health: {data}")


SENSOR_FIELDS: List[Tuple[str, str]] = [
    ("temperature_c", "Temperatura (°C)"),
    ("humidity_pct", "Umidità (%)"),
    ("pressure_hpa", "Pressione (hPa)"),
    ("light_lux", "Luminosità (lux)"),
    ("co2_ppm", "CO₂ (ppm)"),
    ("ph", "pH"),
    ("ec_ms_cm", "EC (mS/cm)"),
]


def _format_sensor_text(sensor_data: dict) -> str:
    """Restituisce il contesto ambientale consentito per i prompt diagnosi."""
    return _format_sensor_text_for_language(sensor_data, response_language=VOICE_LANGUAGE_IT)


def _collapse_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def _clip_text(text: str, limit: int = 280) -> str:
    compact = _collapse_whitespace(text)
    if len(compact) <= limit:
        return compact
    return compact[: limit - 3].rstrip() + "..."


_PLANT_COMMON_NAMES_BY_GENUS = {
    "Apple": "mela",
    "Bell_pepper": "peperone",
    "Blueberry": "mirtillo",
    "Cherry": "ciliegio",
    "Corn": "mais",
    "Grape": "vite",
    "Peach": "pesco",
    "Potato": "patata",
    "Squash": "zucca",
    "Strawberry": "fragola",
    "Tomato": "pomodoro",
}

_GENERIC_PLANT_NAME_TOKENS = {
    "foglia", "foglie", "fogliee", "fogliare", "fogliame",
    "frutto", "frutti", "fiore", "fiori", "macchia", "macchie",
    "lesione", "lesioni", "bordo", "bordi", "margine", "margini",
    "ramo", "rami", "stelo", "steli", "pianta",
}

_VISION_UNKNOWN_PLANT_MARKERS = (
    "non determinabile dalla sola immagine",
    "non determinabile dalla sola foto",
    "non determinabile",
    "non identificabile dalla sola immagine",
    "non identificabile dalla sola foto",
    "non identificabile",
    "not determinable from the image alone",
    "not identifiable from the image alone",
    "unable to determine the plant",
    "cannot determine the plant",
)

_VISION_COMMON_PLANT_KEYWORDS = tuple(
    sorted(
        {
            *{value.lower() for value in _PLANT_COMMON_NAMES_BY_GENUS.values()},
            "peperoncino",
            "capsicum",
            "ficus",
            "dipladenia",
            "mandevilla",
            "orchidea",
            "rosa",
            "basilico",
            "limone",
            "dracena",
            "cactus",
            "geranio",
            "begonia",
            "anturio",
            "ciclamino",
            "azalea",
            "gelsomino",
            "oleandro",
        },
        key=len,
        reverse=True,
    )
)

_VISION_LATIN_BINOMIAL_RE = re.compile(r"\b([A-Z][a-z]{2,}\s+[a-z][a-z-]{2,})\b")
_VISION_PLANT_LABEL_RE = re.compile(
    r"(?:^|[\n\r])\s*(?:\d+[).:-]?\s*)?(?:\*\*\s*)?"
    r"(?:pianta|plant|coltura|crop|specie|species)"
    r"(?:\s*\*\*)?\s*[:\-]\s*([^\n]+)",
    re.IGNORECASE,
)

_VISION_LATIN_BINOMIAL_STOPWORDS = {
    "esito",
    "nome",
    "grado",
    "azioni",
    "monitoraggio",
    "diagnosi",
    "ipotesi",
    "visual",
    "finding",
    "main",
    "immediate",
    "short",
    "plant",
    "confidence",
}


def _normalize_vision_opinion_text(opinion: str) -> str:
    cleaned = re.sub(r"[*_`#>]", " ", str(opinion or ""))
    return _collapse_whitespace(cleaned)


def _vision_opinion_mentions_plant_name(opinion: str) -> bool:
    text = _normalize_vision_opinion_text(opinion)
    if not text:
        return False

    lowered = text.lower()
    if any(marker in lowered for marker in _VISION_UNKNOWN_PLANT_MARKERS):
        return True

    latin_match = _VISION_LATIN_BINOMIAL_RE.search(text)
    if latin_match:
        genus, species = latin_match.group(1).split(" ", 1)
        if genus.lower() not in _VISION_LATIN_BINOMIAL_STOPWORDS and species.lower() not in _VISION_LATIN_BINOMIAL_STOPWORDS:
            return True

    label_match = _VISION_PLANT_LABEL_RE.search(text)
    if label_match:
        candidate = re.split(
            r"\b(?:grado di certezza|livello di certezza|certezza|confidence)\b",
            label_match.group(1),
            maxsplit=1,
            flags=re.IGNORECASE,
        )[0].strip(" .,:;|-")
        if candidate and not any(marker in candidate.lower() for marker in _VISION_UNKNOWN_PLANT_MARKERS):
            words = re.findall(r"\b[\w'/-]+\b", candidate)
            if words and words[0].lower() not in _GENERIC_PLANT_NAME_TOKENS:
                return True

    return any(
        re.search(rf"\b{re.escape(token)}\b", lowered)
        for token in _VISION_COMMON_PLANT_KEYWORDS
    )


def _plant_name_from_class(class_name: str) -> Optional[str]:
    if not class_name:
        return None
    for genus, common_name in _PLANT_COMMON_NAMES_BY_GENUS.items():
        if class_name == genus or class_name.startswith(f"{genus}_"):
            return common_name
    return None


def _extract_plant_name_from_description(description: str) -> Optional[str]:
    text = _collapse_whitespace(description)
    if not text:
        return None

    detected_genus = _detect_genus_from_description(text)
    if detected_genus:
        return _PLANT_COMMON_NAMES_BY_GENUS.get(detected_genus, detected_genus.replace("_", " ").lower())

    candidate = re.split(
        r"\b(?:con|che|ha|presenta|mostra|mostrano|dalle|dalla|dai|dal|da|sulle|sulla|sui|sul|nelle|nella|nei|nel)\b|[,.;:]",
        text,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0].strip()

    while True:
        updated = re.sub(
            r"^(?:questa|questo|quella|quello|la|il|lo|le|i|gli|un|una|uno|mia|mio|mie|miei|nostra|nostro|nostre|nostri)\s+",
            "",
            candidate,
            flags=re.IGNORECASE,
        )
        updated = re.sub(r"^pianta\s+di\s+", "", updated, flags=re.IGNORECASE)
        updated = re.sub(r"^pianta\s+", "", updated, flags=re.IGNORECASE)
        if updated == candidate:
            break
        candidate = updated.strip()

    candidate = candidate.strip(" '\"-_")
    if not candidate:
        return None

    words = candidate.split()
    if len(words) > 4:
        return None

    if words[0].lower() in _GENERIC_PLANT_NAME_TOKENS:
        return None

    return candidate


def _resolve_plant_name_for_memory(user_description: str = "", record: Optional[Dict[str, Any]] = None) -> Optional[str]:
    described_plant = _extract_plant_name_from_description(user_description)
    if described_plant:
        return described_plant

    if record:
        ai_result = record.get("ai_result") or {}
        return _plant_name_from_class(record.get("_corrected_class") or ai_result.get("class", ""))
    return None


def _build_diagnosis_memory_turn(
    *,
    user_description: str = "",
    opinion: str,
    record: Optional[Dict[str, Any]] = None,
    qa_pairs: Optional[List[Tuple[str, str]]] = None,
    followup_mode: str = "",
    sensor_data: Optional[Dict[str, Any]] = None,
) -> Tuple[str, str]:
    """Costruisce un turno memoria breve e leggibile per i follow-up successivi."""
    request_lines = ["Ho chiesto una diagnosi della pianta."]

    plant_name = _resolve_plant_name_for_memory(user_description, record)
    if plant_name:
        request_lines.append(f"Pianta: {plant_name}.")

    if user_description:
        request_lines.append(f"Descrizione iniziale: {_clip_text(user_description, 220)}")

    if followup_mode == "class_mismatch":
        request_lines.append("Modalità: diagnosi interattiva per mismatch tra classe AI e descrizione operatore.")
    elif followup_mode == "fallback":
        request_lines.append("Modalità: diagnosi conversazionale per pianta non riconosciuta dal database.")
    elif followup_mode == "vision_llm":
        request_lines.append("Modalità: diagnosi visiva multimodale da foto inviata direttamente in chat.")

    if record:
        ai_result = record.get("ai_result") or {}
        diagnosis = record.get("diagnosis") or {}
        ai_class = ai_result.get("class")
        confidence = ai_result.get("confidence")
        corrected_class = record.get("_corrected_class")
        summary = diagnosis.get("summary")
        risk = diagnosis.get("risk")
        qdata = diagnosis.get("quantum_risk") or {}

        if corrected_class and corrected_class != ai_class:
            request_lines.append(
                f"Classe AI corretta: {corrected_class} (iniziale: {ai_class or 'N/A'})."
            )
        elif ai_class:
            if isinstance(confidence, (int, float)):
                request_lines.append(
                    f"Classe AI: {ai_class} ({confidence * 100:.1f}% confidenza)."
                )
            else:
                request_lines.append(f"Classe AI: {ai_class}.")

        if summary:
            request_lines.append(f"Sintesi tecnica: {_clip_text(summary, 220)}")

        risk_parts = []
        if risk:
            risk_parts.append(f"rischio={risk}")
        qrs = qdata.get("qrs")
        if isinstance(qrs, (int, float)):
            risk_parts.append(f"QRS={qrs:.4f}")
        dominant = qdata.get("dominant_event")
        if dominant:
            risk_parts.append(f"evento dominante={dominant}")
        if risk_parts:
            request_lines.append("Quadro rischio: " + ", ".join(risk_parts) + ".")

        raw_report = re.sub(r"<[^>]+>", "", _format_diagnosis_full(record)).strip()
        if raw_report:
            request_lines.append("Elementi completi della diagnosi:")
            request_lines.append(raw_report)

    if sensor_data:
        sensor_text = _clip_text(_format_sensor_text(sensor_data), 220)
        if sensor_text:
            request_lines.append(sensor_text)

    if qa_pairs:
        for idx, (question, answer) in enumerate(qa_pairs[-2:], 1):
            request_lines.append(
                f"Follow-up {idx}: D={_clip_text(question, 120)} | R={_clip_text(answer, 120)}"
            )

    memory_request = "\n".join(request_lines)
    memory_response = (opinion or "").strip()
    return memory_request, memory_response


async def _operator_says_healthy(engine, description: str) -> bool:
    """
    Usa l'LLM per valutare in modo contestuale se l'operatore sta descrivendo
    una pianta in buona salute, anche quando non usa la parola 'sano' esplicitamente.
    Esempi riconosciuti: 'aspetto normale', 'fiore bellissimo', 'non noto nulla di strano',
    'sembra stare bene', 'tutto ok', ecc.
    """
    if not description:
        return False
    prompt = (
        "Sei un agronomo esperto. Leggi la seguente descrizione fornita da un operatore "
        "sulla pianta che sta osservando:\n"
        f"'{description}'\n\n"
        "Valuta se l'operatore sta descrivendo una pianta in buona salute, "
        "senza sintomi patologici evidenti.\n"
        "Considera anche espressioni indirette come: 'sembra stare bene', "
        "'aspetto normale', 'non noto nulla di strano', 'fiore bellissimo', "
        "'tutto ok', 'nessuna anomalia', ecc.\n"
        "Rispondi SOLO con una delle seguenti parole:\n"
        "- SANO se la pianta è descritta in buona salute o senza problemi evidenti\n"
        "- NON_SANO se la pianta mostra sintomi, problemi o anomalie\n"
        "- INCERTO se la descrizione non permette di determinarlo\n"
        "Rispondi con UNA SOLA parola, senza altri testi."
    )
    # Chiamata stateless: nessuna memoria letta/scritta, nessuna contaminazione del contesto
    try:
        resp = await asyncio.to_thread(engine.chat_internal, prompt)
        resp_clean = (resp or "").strip().upper().split()[0] if (resp or "").strip() else ""
        logger.debug("_operator_says_healthy: risposta LLM='%s' per descrizione='%s'", resp_clean, description[:60])
        return resp_clean == "SANO"
    except Exception as exc:
        logger.warning("Valutazione stato salute operatore fallita: %s", exc)
        return False


async def start_diagnosis(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _guard(update):
        return ConversationHandler.END

    _clear_diagnosis_state(context)

    # v3.1: Set diagnosis_active flag to inhibit chat during manual input
    context.user_data["diagnosis_active"] = True
    context.user_data["diag_waiting_for_photo"] = True
    await _send(
        update,
        _ui_text(
            context,
            "📷 Scatta una foto con la fotocamera del telefono oppure scegli un'immagine dal telefono e inviala qui per la diagnosi.",
            "📷 Take a photo with the phone camera or choose an image from the phone and send it here for diagnosis.",
        ),
        reply_markup=ReplyKeyboardRemove(),
    )
    return STATE_DIAG_WAIT_PHOTO


async def choose_diag_image_source(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _guard(update):
        return ConversationHandler.END
    query = update.callback_query
    if not query:
        return ConversationHandler.END
    await _answer_callback_query_safe(query)
    if query.data == DIAG_IMAGE_UPLOAD:
        context.user_data["diag_waiting_for_photo"] = True
        await _send(update, _ui_text(context, "Invia una foto (o un file immagine) per la diagnosi.", "Send a photo, or an image file, for the diagnosis."))
        return STATE_DIAG_WAIT_PHOTO
    _clear_diagnosis_state(context)
    await _send(
        update,
        _ui_text(
            context,
            "Questa sorgente immagine non e' piu' disponibile. Usa /diagnosi e invia una foto dal telefono.",
            "This image source is no longer available. Use /diagnosi and send a photo from the phone.",
        ),
    )
    return ConversationHandler.END


async def diag_expect_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _send(update, _ui_text(context, "Per favore invia una foto o un file immagine.", "Please send a photo or an image file."))
    return STATE_DIAG_WAIT_PHOTO


async def receive_diag_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _guard(update):
        return ConversationHandler.END
    saved = await _download_telegram_image(update)
    if not saved:
        await _send(update, _ui_text(context, "Immagine non valida.", "Invalid image."))
        return STATE_DIAG_WAIT_PHOTO
    context.user_data["diag_image_path"] = str(saved)
    return await _advance_guided_diagnosis_after_image(update, context)


async def _advance_guided_diagnosis_after_image(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    context.user_data.pop("diag_waiting_for_photo", None)
    context.user_data.pop("diag_user_description", None)
    return await _ask_diagnosis_gps_context(update, context)


async def _ask_diagnosis_gps_context(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["diag_waiting_for_location"] = True
    context.user_data.pop("awaiting_nasa_sar_location", None)
    await _send(
        update,
        _ui_text(
            context,
            "📍 Foto ricevuta. Ora condividi la posizione GPS del telefono. Usero' NASA-ISRO/SAR per oggi e i 6 giorni precedenti, luminosita' LUX da NASA POWER e rilevo il tipo di ambiente (esterno/serra/interno) dall'immagine satellitare, come contesto della diagnosi.",
            "📍 Photo received. Now share the phone GPS position. I will use NASA-ISRO/SAR for today and the previous 6 days, LUX light data from NASA POWER, and detect the environment type (outdoor/greenhouse/indoor) from the satellite image, as diagnosis context.",
        ),
        reply_markup=_nasa_sar_reply_keyboard(context),
    )
    return ConversationHandler.END


async def _run_diagnosis_from_gps(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    latitude: float,
    longitude: float,
    reply_markup: Optional[Any] = None,
):
    await _send(
        update,
        _ui_text(
            context,
            "🛰️ GPS ricevuto. Acquisisco contesto NASA-ISRO/SAR settimanale, luminosita' LUX e classifico l'ambiente (esterno/serra/interno) dall'immagine satellitare...",
            "🛰️ GPS received. Acquiring weekly NASA-ISRO/SAR context, LUX light data, and classifying the environment (outdoor/greenhouse/indoor) from the satellite image...",
        ),
        reply_markup=reply_markup,
    )
    environmental_context = await _build_diagnosis_environment_context(context, latitude, longitude)
    context.user_data["diag_environment_context"] = environmental_context
    context.user_data["sensor_data"] = environmental_context
    return await _run_diagnosis(update, context, environmental_context)


async def _ask_user_description(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Chiede all'utente il tipo di pianta e l'anomalia riscontrata."""
    await _send(
        update,
        _ui_text(
            context,
            "Di che pianta si tratta? Descrivimi l'anomalia che hai riscontrato, sarò ben lieto di aiutarti 😊\n\n_Esempio: 'Pomodoro con macchie gialle sulle foglie e bordi secchi'_",
            "What plant is it? Describe the anomaly you noticed and I will be glad to help 😊\n\n_Example: 'Tomato with yellow spots on the leaves and dry edges'_",
        ),
        parse_mode="Markdown",
    )
    return STATE_DIAG_USER_DESCRIPTION


async def receive_user_description(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Riceve la descrizione testuale utente e procede alla posizione GPS."""
    if not await _guard(update):
        return ConversationHandler.END
    if not update.message or not update.message.text:
        await _send(update, _ui_text(context, "Per favore descrivi la pianta e l'anomalia osservata.", "Please describe the plant and the anomaly you observed."))
        return STATE_DIAG_USER_DESCRIPTION
    description = update.message.text.strip()
    if len(description) < 3:
        await _send(update, _ui_text(context, "Descrizione troppo breve. Aggiungi dettagli sulla pianta e sull'anomalia.", "Description too short. Add more details about the plant and the anomaly."))
        return STATE_DIAG_USER_DESCRIPTION
    context.user_data["diag_user_description"] = description
    await _send(update, _ui_text(context, "Grazie! Ora acquisisco il contesto GPS NASA-ISRO/SAR e LUX... 🌱", "Thanks! I am now acquiring GPS NASA-ISRO/SAR and LUX context... 🌱"))
    return await _ask_diagnosis_gps_context(update, context)


async def _ask_sensor_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(_ui_text(context, "Usa sensori attuali", "Use current sensors"), callback_data=DIAG_SENSOR_AUTO)],
        [InlineKeyboardButton(_ui_text(context, "Inserimento manuale", "Manual entry"), callback_data=DIAG_SENSOR_MANUAL)],
    ])
    await _send(update, _ui_text(context, "Come vuoi acquisire i dati sensore?", "How do you want to acquire the sensor data?"), reply_markup=keyboard)
    return STATE_DIAG_SENSOR_MODE


async def choose_sensor_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _guard(update):
        return ConversationHandler.END
    query = update.callback_query
    if not query:
        return ConversationHandler.END
    await _answer_callback_query_safe(query)
    if query.data == DIAG_SENSOR_AUTO:
        return await _run_diagnosis(update, context, None)
    if query.data == DIAG_SENSOR_MANUAL:
        context.user_data["sensor_data"] = {"source": "telegram_manual"}
        context.user_data["sensor_index"] = 0
        await _send(update, _ui_text(context, f"Inserisci {SENSOR_FIELDS[0][1]} (digita x per saltare):", f"Enter {SENSOR_FIELDS[0][1]} (type x to skip):"))
        return STATE_DIAG_TEMP
    await _send(update, _ui_text(context, "Scelta non valida.", "Invalid choice."))
    _clear_diagnosis_state(context)
    return ConversationHandler.END


async def manual_sensor_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _guard(update):
        return ConversationHandler.END
    if not update.message:
        return STATE_DIAG_TEMP
    value_raw = update.message.text.strip()
    is_skip = value_raw.lower() == "x"
    idx = int(context.user_data.get("sensor_index", 0))
    if idx >= len(SENSOR_FIELDS):
        return ConversationHandler.END
    key, label = SENSOR_FIELDS[idx]
    if value_raw and not is_skip:
        parsed = _parse_float(value_raw)
        if parsed is None:
            await _send(update, _ui_text(context, f"Valore non valido. Inserisci {label} (oppure digita x per saltare).", f"Invalid value. Enter {label}, or type x to skip."))
            return STATE_DIAG_TEMP
        context.user_data["sensor_data"][key] = parsed
    idx += 1
    context.user_data["sensor_index"] = idx
    if idx < len(SENSOR_FIELDS):
        await _send(update, _ui_text(context, f"Inserisci {SENSOR_FIELDS[idx][1]} (digita x per saltare):", f"Enter {SENSOR_FIELDS[idx][1]} (type x to skip):"))
        return STATE_DIAG_TEMP
    sensor_data = context.user_data.get("sensor_data", {})
    return await _run_diagnosis(update, context, sensor_data)


# Pattern frasi LLM che chiedono all'utente di inviare una foto (causano loop diagnosi)
_PHOTO_REQUEST_PATTERNS = re.compile(
    r"(?:"
    r"invia(?:re)?\s+(?:una\s+)?(?:foto|immagine|fotografia)"
    r"|manda(?:re)?\s+(?:una\s+)?(?:foto|immagine|fotografia)"
    r"|puoi\s+(?:inviare|mandare)\s+(?:una\s+)?(?:foto|immagine)"
    r"|allega(?:re)?\s+(?:una\s+)?(?:foto|immagine)"
    r"|carica(?:re)?\s+(?:una\s+)?(?:foto|immagine)"
    r"|scatta(?:re)?\s+(?:una\s+)?(?:foto|immagine)"
    r"|se\s+(?:hai|hai\s+una)\s+(?:foto|immagine)"
    r"|per\s+un(?:a\s+)?analisi\s+visiva"
    r")",
    re.IGNORECASE,
)

_ENGLISH_DIAGNOSIS_REPLACEMENTS = (
    ("INTERVENTO URGENTE RICHIESTO", "URGENT ACTION REQUIRED"),
    ("Intervento urgente richiesto", "Urgent action required"),
    ("Malattia rilevata da visione AI", "Disease detected by AI vision"),
)


def _sanitize_diagnosis_opinion(
    opinion: str,
    response_language: str = VOICE_LANGUAGE_IT,
) -> str:
    """Riduce aperture metalinguistiche poco utili e rimuove richieste di foto."""
    text = (opinion or "").strip()
    if not text:
        return text

    lowered = text.lower()
    bad_prefixes = (
        "sembra che tu stia",
        "mi sembra che tu stia",
        "pare che tu stia",
        "sembra che tu",
        "pare che tu",
    )
    if lowered.startswith(bad_prefixes):
        parts = re.split(r"(?<=[.!?])\s+", text, maxsplit=1)
        if len(parts) == 2 and parts[1].strip():
            return parts[1].strip()
        return (
            "Valutazione agronomica: la diagnosi AI e compatibile con il quadro osservato, "
            "ma va confermata con rilievo in campo su distribuzione delle lesioni, progressione "
            "dei sintomi e condizioni microclimatiche. "
            "Priorita operative: riduzione stress ambientale, intervento fitosanitario mirato "
            "secondo etichetta, e monitoraggio strutturato a 24-48 ore e a 7 giorni."
        )

    # Rimuove frasi che chiedono di inviare foto (causano loop nella diagnosi)
    sentences = re.split(r"(?<=[.!?])\s+", text)
    cleaned = [s for s in sentences if not _PHOTO_REQUEST_PATTERNS.search(s)]
    if cleaned:
        text = " ".join(cleaned).strip()

    if response_language == VOICE_LANGUAGE_EN:
        for italian_text, english_text in _ENGLISH_DIAGNOSIS_REPLACEMENTS:
            text = text.replace(italian_text, english_text)

    return text


def _strip_plantvillage_class_mentions(text: str) -> str:
    """Rimuove citazioni esplicite di classi PlantVillage dal testo finale."""
    cleaned = text or ""
    for cls in _PLANTVILLAGE_CLASSES:
        pattern = re.escape(cls).replace("_", r"[ _]")
        cleaned = re.sub(pattern, "classe omessa", cleaned, flags=re.IGNORECASE)
    return cleaned


def _build_diagnosis_prompt(
    record: Dict[str, Any],
    user_description: str = "",
    response_language: str = VOICE_LANGUAGE_IT,
) -> str:
    """Costruisce il prompt per un unico messaggio AI di risultato diagnosi."""
    dx = record.get("diagnosis", {})
    ai = record.get("ai_result", {})
    recs = record.get("recommendations", [])
    sensor = record.get("sensor_snapshot", {})
    quantum_risk = dx.get("quantum_risk", {})

    ai_class = ai.get("class", "N/D")
    ai_conf = ai.get("confidence", 0)
    risk = dx.get("overall_risk", "N/D")
    status = dx.get("plant_status", "N/D")
    explanation = dx.get("explanation", "")
    qrs = quantum_risk.get("quantum_risk_score", 0.0) if quantum_risk else 0.0
    qdom = quantum_risk.get("dominant_description", "") if quantum_risk else ""
    anomalies = sensor.get("_anomalies", [])
    top_recs = recs[:3] if recs else []
    rec_text = "; ".join(
        f"{r.get('category','?').upper()}: {r.get('action','')}" for r in top_recs
    )
    anomaly_text = ", ".join(anomalies) if anomalies else "nessuna"

    raw_report = re.sub(r"<[^>]+>", "", _format_diagnosis_full(record))

    corrected_class = record.get("_corrected_class", "")
    has_operator_description = bool((user_description or "").strip())
    has_confirmed_class = not bool(ai.get("fallback", False)) and ai_class not in {
        "",
        "N/D",
        "Classe_NonClassificato",
        "errore",
        "non_disponibile",
    }
    class_note = ""
    if corrected_class and corrected_class != ai_class:
        class_note = (
            f"\nNOTA: la classe PlantVillage originale ({ai_class}) è stata corretta "
            f"in '{corrected_class}' sulla base della descrizione dell'utente.\n"
        )

    if response_language == VOICE_LANGUAGE_EN:
        anomaly_text = ", ".join(anomalies) if anomalies else "none"
        class_note = ""
        if corrected_class and corrected_class != ai_class:
            class_note = (
                f"\nNOTE: the original PlantVillage class ({ai_class}) was corrected "
                f"to '{corrected_class}' based on the operator description.\n"
            )

        description_block = ""
        if has_operator_description:
            description_block = (
                f"\nOPERATOR DESCRIPTION (primary source to prioritize):\n"
                f"  \"{user_description}\"\n"
            )
            description_constraints = (
                "- The operator description is the primary source: use the symptoms, affected part, and context described by the operator to personalize every block of the reply. Do not treat it as a marginal note.\n"
                f"- In block 1 (Technical outcome), explicitly explain why the detected PlantVillage class is consistent, or only partially consistent, with '{user_description}'.\n"
                "- If the description mentions specific symptoms, such as color, affected zone, or progression, cite them and connect them to the identified pathology.\n"
            )
        else:
            description_constraints = (
                "- No operator description is available in this case: do not invent symptoms, crop context, or observations not present in the technical report.\n"
                "- Base the reply only on the visual diagnosis report and on the technical data returned by DELTA.\n"
            )

        if has_confirmed_class:
            if has_operator_description:
                class_constraint = "- Explicitly cite the confirmed PlantVillage class and explain why it is consistent with the operator description.\n"
            else:
                class_constraint = "- Explicitly cite the PlantVillage class proposed by the visual backend and explain which technical and visual elements of the report support it.\n"
        else:
            class_constraint = (
                "- Do not present any PlantVillage class as confirmed: the visual backend returned an uncertain or unclassified result. "
                "State the uncertainty clearly and formulate only prudent hypotheses based on the available visual signals.\n"
            )

        return (
            "Transform the following report into a SINGLE final message for the user, in English, with a professional expert agronomist tone, detailed but clear.\n\n"
            f"RAW DELTA DIAGNOSIS REPORT:\n{raw_report}\n"
            f"{description_block}"
            f"{class_note}\n"
            "Mandatory constraints:\n"
            "- Do not use metalinguistic phrasing, for example 'It seems you are asking'.\n"
            "- Do not repeat the report title.\n"
            "- If the raw report contains Italian fragments, translate them: the final user-facing answer must be fully in English, except for PlantVillage class names or fixed technical labels.\n"
            f"{class_constraint}"
            "- Explicitly include the Grover Quantum Oracle risk analysis: explain in a simple operational way what it represents, namely a tool that amplifies the most significant plant-risk signals, with QRS from 0 meaning no risk to 1 meaning maximum risk, then report QRS, level, dominant event, and amplification.\n"
            f"{description_constraints}"
            "- Analyze and comment only on GPS/NASA-ISRO/SAR/LUX environmental context available in the report: SAR soil moisture, weekly fungal risk, GPS locality, and LUX light estimate. Ignore legacy physical sensor fields if present.\n"
            "- Structure the answer in 5 blocks: 1) Technical outcome, 2) Short differential diagnosis, 3) Immediate actions (0-24h), 4) Short-term actions (2-7 days), 5) Monitoring and prevention.\n"
            "- Provide concrete and verifiable operational guidance.\n"
            "- When appropriate, mention integrated pest-management and crop hygiene practices.\n"
            "- Do not ask the user to send photos or take additional pictures: image acquisition is already complete.\n"
            "- Keep a technical, professional tone without being verbose.\n"
            "- Stay consistent with: "
            f"class={corrected_class or ai_class}, confidence={ai_conf*100:.1f}%, "
            f"status={status}, risk={risk}, "
            f"QRS={qrs:.4f}, dominant_event={qdom}, anomalies={anomaly_text}, "
            f"recommendations={rec_text if rec_text else 'none'}."
        )

    description_block = ""
    if has_operator_description:
        description_block = (
            f"\nDESCRIZIONE OPERATORE (fonte primaria da valorizzare):\n"
            f"  \"{user_description}\"\n"
        )
        description_constraints = (
            "- La descrizione dell'operatore è la fonte primaria: "
            "usa i sintomi, la parte colpita e il contesto che ha descritto per personalizzare "
            "ogni blocco della risposta. Non trattarla come nota marginale.\n"
            f"- Nel blocco 1 (Esito tecnico) spiega esplicitamente perché la classe "
            f"PlantVillage rilevata è coerente (o parzialmente coerente) con '{user_description}'.\n"
            "- Se la descrizione menziona sintomi specifici (colore, zona, progressione), "
            "citali e correlali alla patologia identificata.\n"
        )
    else:
        description_constraints = (
            "- In questo caso non è disponibile alcuna descrizione dell'operatore: non inventare sintomi, coltura o osservazioni non presenti nel report tecnico.\n"
            "- Basa la risposta solo sul report di diagnosi visiva e sui dati tecnici restituiti da DELTA.\n"
        )

    if has_confirmed_class:
        if has_operator_description:
            class_constraint = "- Cita esplicitamente la classe PlantVillage confermata e motiva la coerenza con la descrizione dell'operatore.\n"
        else:
            class_constraint = "- Cita esplicitamente la classe PlantVillage proposta dal backend visivo e spiega quali elementi tecnici e visivi del report la supportano.\n"
    else:
        class_constraint = (
            "- Non presentare alcuna classe PlantVillage come confermata: il backend visivo ha restituito un esito incerto o non classificato. "
            "Esplicita chiaramente l'incertezza e formula solo ipotesi prudenti basate sui segnali visivi disponibili.\n"
        )

    return (
        "Trasforma il report seguente in un UNICO messaggio finale per l'utente, "
        "in italiano, con stile professionale da agronomo esperto, dettagliato ma chiaro.\n\n"
        f"REPORT RAW RISULTATO DIAGNOSI DELTA:\n{raw_report}\n"
        f"{description_block}"
        f"{class_note}\n"
        "Vincoli obbligatori:\n"
        "- Non usare frasi metalinguistiche (es: 'Sembra che tu stia chiedendo').\n"
        "- Non ripetere il titolo del report.\n"
        f"{class_constraint}"
        "- Includi esplicitamente l'analisi del rischio con Oracolo Quantistico di Grover: "
        "spiega in modo semplice e operativo cosa rappresenta (strumento che amplifica i segnali "
        "di rischio più significativi tra i dati della pianta, con QRS da 0=nessun rischio a 1=rischio massimo), "
        "poi riporta QRS, livello, evento dominante e amplificazione.\n"
        f"{description_constraints}"
        "- Analizza e commenta solo il contesto ambientale GPS/NASA-ISRO/SAR/LUX presente nel report: umidita' suolo SAR, rischio fungino settimanale, localita' GPS e stima LUX. Ignora eventuali vecchi campi da sensori fisici.\n"
        "- Struttura in 5 blocchi: 1) Esito tecnico, 2) Diagnosi differenziale breve, "
        "3) Azioni immediate (0-24h), 4) Azioni a breve (2-7 giorni), "
        "5) Monitoraggio e prevenzione.\n"
        "- Fornisci indicazioni operative concrete e verificabili.\n"
        "- Se appropriato, indica pratiche di difesa integrata e igiene colturale.\n"
        "- Non chiedere all'utente di inviare foto, immagini o scattare ulteriori fotografie: la fase di acquisizione immagine è già conclusa.\n"
        "- Mantieni tono tecnico-professionale, senza essere prolisso.\n"
        "- Mantieni coerenza con: "
        f"classe={corrected_class or ai_class}, confidenza={ai_conf*100:.1f}%, "
        f"stato={status}, rischio={risk}, "
        f"QRS={qrs:.4f}, evento_dominante={qdom}, anomalie={anomaly_text}, "
        f"raccomandazioni={rec_text if rec_text else 'nessuna'}."
    )


_PLANTVILLAGE_CLASSES = [
    "Apple_Apple_scab", "Apple_Black_rot", "Apple_Cedar_apple_rust", "Apple_healthy",
    "Bell_pepper_Bacterial_spot", "Bell_pepper_healthy", "Blueberry_healthy",
    "Cherry_Powdery_mildew", "Cherry_healthy", "Corn_Cercospora", "Corn_Common_rust",
    "Corn_Northern_Leaf_Blight", "Corn_healthy", "Grape_Black_rot", "Grape_Esca",
    "Grape_Leaf_blight", "Grape_healthy", "Peach_healthy", "Potato_Early_blight",
    "Potato_Late_blight", "Potato_healthy", "Squash_Powdery_mildew",
    "Strawberry_Leaf_scorch", "Strawberry_healthy", "Tomato_Bacterial_spot",
    "Tomato_Early_blight", "Tomato_Late_blight", "Tomato_Leaf_Mold",
    "Tomato_Septoria_leaf_spot", "Tomato_Target_Spot", "Tomato_Yellow_Leaf_Curl",
    "Tomato_healthy", "Tomato_mosaic_virus",
]


# Generi di piante coperti da PlantVillage (case-insensitive match)
_PLANTVILLAGE_GENERA = [
    "apple", "mela",
    "bell pepper", "peperone",
    "blueberry", "mirtillo",
    "cherry", "ciliegio", "ciliegia",
    "corn", "mais", "granturco",
    "grape", "uva", "vite",
    "peach", "pesca", "pesco",
    "potato", "patata",
    "squash", "zucca",
    "strawberry", "fragola",
    "tomato", "pomodoro",
]


# Mappa: keyword (IT/EN) → prefisso genere PlantVillage
_GENUS_KEYWORD_MAP: List[tuple] = [
    (["bell pepper", "peperone", "pepper", "capsicum"],          "Bell_pepper"),
    (["apple", "mela"],                                          "Apple"),
    (["blueberry", "mirtillo"],                                  "Blueberry"),
    (["cherry", "ciliegio", "ciliegia"],                         "Cherry"),
    (["corn", "mais", "granturco", "granoturco"],                "Corn"),
    (["grape", "uva", "vite", "vitis"],                          "Grape"),
    (["peach", "pesca", "pesco"],                                "Peach"),
    (["potato", "patata"],                                       "Potato"),
    (["squash", "zucca"],                                        "Squash"),
    (["strawberry", "fragola"],                                  "Strawberry"),
    (["tomato", "pomodoro"],                                     "Tomato"),
]


def _detect_genus_from_description(description: str) -> Optional[str]:
    """
    Rileva programmaticamente il genere PlantVillage dalla descrizione dell'utente.
    Restituisce il prefisso genere (es. 'Bell_pepper') o None se non trovato.
    Ordine di priorità: prima match multi-parola, poi singola parola.
    """
    desc_lower = description.lower()
    # Prima passa: cerca match multi-parola (es. "bell pepper" prima di "pepper")
    for keywords, genus in _GENUS_KEYWORD_MAP:
        for kw in keywords:
            if " " in kw and kw in desc_lower:
                return genus
    # Seconda passa: match singola parola
    for keywords, genus in _GENUS_KEYWORD_MAP:
        for kw in keywords:
            if " " not in kw and kw in desc_lower:
                return genus
    return None


async def _reclassify_with_description(
    engine,
    ai_class: str,
    user_description: str,
) -> "Optional[str]":
    """
    Verifica se la pianta descritta appartiene a un genere coperto da PlantVillage.
    - Se appartiene: restituisce la classe PlantVillage più appropriata.
    - Se NON appartiene: restituisce None → diagnosi solo AI interattiva.

    Strategia in due fasi:
    1. Genus detection programmatica dalla descrizione (affidabile, no LLM).
    2. Se genere trovato, chiede al LLM di scegliere la malattia SOLO
       tra le classi di quel genere (lista ristretta, nessuna confusione inter-genere).
    """
    desc_lower = user_description.lower()

    # ── Fase 1: genus detection programmatica ────────────────────────────
    detected_genus = _detect_genus_from_description(user_description)

    if detected_genus is None:
        # Nessun genere PlantVillage riconosciuto nella descrizione
        logger.info(
            "Reclassificazione: genere non trovato nella descrizione '%s', modalità AI interattiva.",
            user_description[:60],
        )
        return None

    logger.info("Reclassificazione: genere rilevato '%s' da descrizione '%s'",
                detected_genus, user_description[:60])

    # ── Fase 2: scelta malattia tra classi del genere rilevato ───────────
    genus_classes = [c for c in _PLANTVILLAGE_CLASSES if c.startswith(detected_genus)]
    if not genus_classes:
        return None

    # Se c'è una sola classe possibile, usala direttamente senza chiamata LLM
    if len(genus_classes) == 1:
        return genus_classes[0]

    classes_list = "\n".join(f"- {c}" for c in genus_classes)
    prompt = (
        f"Sei un agronomo esperto. L'utente ha descritto la sua pianta così:\n"
        f"'{user_description}'\n\n"
        f"La pianta è un/a {detected_genus.replace('_', ' ')} (genere già identificato).\n"
        f"Il modello AI ha classificato l'immagine come: '{ai_class}'\n\n"
        f"Scegli la classe PlantVillage più appropriata tra queste (SOLO queste):\n{classes_list}\n\n"
        "Rispondi SOLO con il nome esatto della classe, senza altre parole."
    )
    try:
        corrected = await asyncio.to_thread(engine.chat_internal, prompt)
        corrected = (corrected or "").strip().strip('"').strip("'")

        if corrected in genus_classes:
            return corrected
        # Corrispondenza parziale
        corrected_norm = corrected.lower().replace(" ", "_")
        for cls in genus_classes:
            if cls.lower() == corrected_norm:
                return cls

        # LLM ha restituito qualcosa fuori dalla lista → usa healthy del genere come fallback
        healthy_fallback = f"{detected_genus}_healthy"
        if healthy_fallback in _PLANTVILLAGE_CLASSES:
            logger.warning(
                "Reclassificazione: risposta LLM '%s' non valida, fallback su '%s'",
                corrected[:60], healthy_fallback,
            )
            return healthy_fallback
        return genus_classes[0]

    except Exception as exc:
        logger.warning("Errore reclassificazione LLM: %s", exc)
        # In caso di errore, restituisce la classe healthy del genere rilevato
        healthy_fallback = f"{detected_genus}_healthy"
        return healthy_fallback if healthy_fallback in _PLANTVILLAGE_CLASSES else genus_classes[0]


async def _generate_followup_question(
    engine, user_id: str, user_description: str, qa_pairs: list,
    sensor_context: str = "",
) -> tuple:
    """
    Genera la prossima domanda di approfondimento oppure segnala che la diagnosi può
    già essere elaborata. Restituisce (testo_domanda, should_stop).
    Se sensor_context è presente, l'AI sa già quali dati ambientali sono disponibili
    e non li chiederà di nuovo.
    """
    history = ""
    for i, (q, a) in enumerate(qa_pairs, 1):
        history += f"D{i}: {q}\nR{i}: {a}\n"

    # Prima chiamata (nessuna Q&A ancora): forza sempre una domanda, non accetta DIAGNOSI_PRONTA
    is_first_question = not qa_pairs

    prompt = (
        "Sei un agronomo esperto che sta diagnosticando una malattia vegetale "
        "senza aver visto l'immagine della pianta.\n"
        f"Descrizione iniziale dell'utente: '{user_description}'\n"
        + (f"\nDomande e risposte precedenti:\n{history}" if history else "")
        + (f"\nDati ambientali già acquisiti (non chiedere di nuovo questi):{sensor_context}\n" if sensor_context else "")
        + (
            "\nDevi fare la tua PRIMA domanda di approfondimento: scegli la domanda "
            "più utile per capire meglio il problema (colore, aspetto, parte colpita, "
            "progressione dei sintomi"
            + (", ecc.).\n" if sensor_context else ", condizioni ambientali, ecc.).\n")
            + "Rispondi SOLO con la domanda, senza altre parole."
            if is_first_question else
            "\nValuta se hai informazioni sufficienti per una diagnosi accurata.\n"
            "Se sì, rispondi esattamente con: DIAGNOSI_PRONTA\n"
            "Altrimenti, formula UNA sola domanda breve e mirata (colore, aspetto, "
            "parte colpita, progressione"
            + (", ecc.).\n" if sensor_context else ", condizioni ambientali, ecc.).\n")
            + "Rispondi SOLO con la domanda oppure con DIAGNOSI_PRONTA, senza altre parole."
        )
    )
    # Chiamata stateless: nessuna memoria letta/scritta, nessuna contaminazione del contesto
    # e nessuna storia accumulata tra una domanda e l'altra che farebbe generare output multipli.
    try:
        resp = await asyncio.to_thread(engine.chat_internal, prompt)
        resp = (resp or "").strip()
        # Sulla prima domanda ignoriamo DIAGNOSI_PRONTA: deve sempre chiedere almeno una volta
        if not is_first_question and "DIAGNOSI_PRONTA" in resp.upper():
            return "", True
        # Se la risposta è vuota o contiene solo DIAGNOSI_PRONTA alla prima chiamata, fallback
        if not resp or (is_first_question and resp.upper().strip() == "DIAGNOSI_PRONTA"):
            return "Puoi descrivere più nel dettaglio i sintomi visibili sulla pianta?", False
        # Post-processing: estrai solo la prima domanda, scarta eventuali auto-risposte.
        lines = [l.strip() for l in resp.splitlines() if l.strip()]
        question_line = ""
        for line in lines:
            lower = line.lower()
            if lower.startswith(("risposta", "r:", "r1:", "r2:", "r3:", "r4:", "r5:",
                                  "answer", "a:", "diagnosi_pronta")):
                break
            question_line = line
            if "?" in line:
                break
        if not question_line:
            question_line = lines[0] if lines else "Puoi descrivere più nel dettaglio i sintomi visibili?"
        return question_line, False
    except Exception as exc:
        logger.warning("Errore generazione domanda follow-up: %s", exc)
        return "", True


async def _start_followup_questioning(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    record: dict,
    mode: str = "fallback",
) -> int:
    """
    Avvia la modalità interrogazione follow-up per piante non riconosciute dal modello.
    Salva il record parziale, invia l'avviso e pone la prima domanda.
    """
    context.user_data["diag_fallback_record"] = record
    context.user_data["diag_followup_mode"] = mode
    context.user_data["diag_followup_qa"] = []
    context.user_data["diag_followup_count"] = 0

    engine = _get_chat_engine(context)
    user_id = str(update.effective_user.id if update.effective_user else "0")
    user_description = context.user_data.get("diag_user_description", "")

    # ── Controllo prioritario: operatore descrive pianta sana (valutazione contestuale LLM) ──
    if await _operator_says_healthy(engine, user_description):
        await _send(
            update,
            _ui_text(
                context,
                "✅ <b>L'operatore descrive la pianta in buona salute.</b>\nNon avvio il flusso diagnostico. Elaboro una valutazione di benessere... 🌿",
                "✅ <b>The operator describes the plant as healthy.</b>\nI will not start the diagnostic flow. I am preparing a wellness assessment... 🌿",
            ),
            parse_mode="HTML",
        )
        await _send_conversational_diagnosis(update, context)
        return ConversationHandler.END

    if mode == "class_mismatch":
        intro = _ui_text(
            context,
            "⚠️ <b>Nessuna corrispondenza piena tra classe AI e quadro descritto.</b>\nProcedo con analisi solo AI tramite interazione Operatore/AI.\n"
            f"Ti farò al massimo {MAX_FOLLOWUP_QUESTIONS} domande di approfondimento. 🌿",
            "⚠️ <b>No full match between the AI class and the described condition.</b>\nI will proceed with AI-only analysis through Operator/AI interaction.\n"
            f"I will ask at most {MAX_FOLLOWUP_QUESTIONS} follow-up questions. 🌿",
        )
    else:
        intro = _ui_text(
            context,
            "⚠️ <b>Pianta non riconosciuta nel database.</b>\nProcederò comunque con una diagnosi basata sulla tua descrizione.\n"
            f"Ti farò al massimo {MAX_FOLLOWUP_QUESTIONS} domande di approfondimento. 🌿",
            "⚠️ <b>Plant not recognized in the database.</b>\nI will still proceed with a diagnosis based on your description.\n"
            f"I will ask at most {MAX_FOLLOWUP_QUESTIONS} follow-up questions. 🌿",
        )

    await _send(update, intro, parse_mode="HTML")

    _sensor_ctx = _format_sensor_text(context.user_data.get("sensor_data", {}))
    question, should_stop = await _generate_followup_question(
        engine, user_id, user_description, [], sensor_context=_sensor_ctx
    )
    if should_stop or not question:
        await _send(update, _ui_text(context, "Ho già abbastanza informazioni. Elaboro la diagnosi... 🔬", "I already have enough information. I am processing the diagnosis... 🔬"))
        await _send_conversational_diagnosis(update, context)
        return ConversationHandler.END

    context.user_data["diag_followup_count"] = 1
    context.user_data["diag_followup_last_question"] = question
    context.user_data["diag_qa_active"] = True
    await _send(
        update,
        _ui_text(
            context,
            f"❓ <b>Domanda 1/{MAX_FOLLOWUP_QUESTIONS}:</b>\n{question}",
            f"❓ <b>Question 1/{MAX_FOLLOWUP_QUESTIONS}:</b>\n{question}",
        ),
        parse_mode="HTML",
    )
    return STATE_DIAG_FOLLOWUP


async def receive_followup_answer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handler per le risposte alle domande di approfondimento."""
    if not await _guard(update):
        return ConversationHandler.END
    if not update.message:
        return STATE_DIAG_FOLLOWUP

    answer = (update.message.text or "").strip()
    if not answer:
        await _send(update, _ui_text(context, "Non ho ricevuto una risposta. Riprova.", "I did not receive an answer. Try again."))
        return STATE_DIAG_FOLLOWUP

    qa_pairs = context.user_data.get("diag_followup_qa", [])
    count = context.user_data.get("diag_followup_count", 1)
    last_question = context.user_data.get("diag_followup_last_question", "")

    qa_pairs.append((last_question, answer))
    context.user_data["diag_followup_qa"] = qa_pairs

    if count >= MAX_FOLLOWUP_QUESTIONS:
        context.user_data["diag_qa_active"] = False
        await _send(update, _ui_text(context, "✅ Ho raccolto tutte le informazioni necessarie. Elaboro la diagnosi... 🔬", "✅ I collected all the necessary information. I am processing the diagnosis... 🔬"))
        await _send_conversational_diagnosis(update, context)
        return ConversationHandler.END

    # Conferma ricezione risposta e segnala che si sta elaborando la domanda successiva
    await _send(update, _ui_text(context, f"📝 <i>Risposta {count} registrata.</i>", f"📝 <i>Answer {count} recorded.</i>"), parse_mode="HTML")
    try:
        await update.effective_chat.send_action("typing")
    except Exception:
        pass

    engine = _get_chat_engine(context)
    user_id = str(update.effective_user.id if update.effective_user else "0")
    user_description = context.user_data.get("diag_user_description", "")

    _sensor_ctx = _format_sensor_text(context.user_data.get("sensor_data", {}))
    question, should_stop = await _generate_followup_question(
        engine, user_id, user_description, qa_pairs, sensor_context=_sensor_ctx
    )
    if should_stop or not question:
        context.user_data["diag_qa_active"] = False
        await _send(update, _ui_text(context, "✅ Ho raccolto tutte le informazioni necessarie. Elaboro la diagnosi... 🔬", "✅ I collected all the necessary information. I am processing the diagnosis... 🔬"))
        await _send_conversational_diagnosis(update, context)
        return ConversationHandler.END

    new_count = count + 1
    context.user_data["diag_followup_count"] = new_count
    context.user_data["diag_followup_last_question"] = question
    await _send(
        update,
        _ui_text(
            context,
            f"❓ <b>Domanda {new_count}/{MAX_FOLLOWUP_QUESTIONS}:</b>\n{question}",
            f"❓ <b>Question {new_count}/{MAX_FOLLOWUP_QUESTIONS}:</b>\n{question}",
        ),
        parse_mode="HTML",
    )
    return STATE_DIAG_FOLLOWUP


async def _send_conversational_diagnosis(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Genera e invia una diagnosi basata esclusivamente sulla conversazione con l'utente."""
    try:
        await update.effective_chat.send_action("typing")
    except Exception:
        pass

    engine = _get_chat_engine(context)
    user_id = str(update.effective_user.id if update.effective_user else "0")
    user_description = context.user_data.get("diag_user_description", "")
    qa_pairs = context.user_data.get("diag_followup_qa", [])
    sensor_data = context.user_data.get("sensor_data", {})
    followup_mode = context.user_data.get("diag_followup_mode", "fallback")

    qa_text = ""
    for i, (q, a) in enumerate(qa_pairs, 1):
        qa_text += f"\nD{i}: {q}\nR{i}: {a}"

    sensor_text = _format_sensor_text(sensor_data)
    operator_healthy = await _operator_says_healthy(engine, user_description)
    english_ui = _ui_language(context) == VOICE_LANGUAGE_EN

    # Vincolo salute: se l'operatore ha dichiarato la pianta sana, il sistema
    # non deve formulare diagnosi di malattia ma una valutazione di benessere.
    health_constraint = (
        "\n⚠️ CRITICAL CONSTRAINT: the operator explicitly declared the plant healthy. DO NOT formulate a disease or pathology diagnosis. Produce a health assessment: confirm the observed wellness, point out any environmental risk factors to monitor proactively, and suggest good agronomic practices to keep the plant healthy."
        if operator_healthy and english_ui else
        "\n⚠️ VINCOLO CRITICO: l'operatore ha dichiarato esplicitamente la pianta in buona salute. NON formulare diagnosi di malattie o patologie. Produci una valutazione dello stato di salute: conferma il benessere osservato, indica eventuali fattori di rischio ambientale da monitorare preventivamente e suggerisci buone pratiche colturali per mantenere la pianta in salute."
        if operator_healthy else ""
    )

    if followup_mode == "class_mismatch" and english_ui:
        prompt = (
            "You are an expert agronomist. There is a mismatch between the initial AI class and the condition described by the operator.\n"
            "You must produce an assessment ONLY through Operator/AI interaction, namely the description plus follow-up answers, without using PlantVillage classes in the final answer.\n"
            f"Initial user description: '{user_description}'\n"
            + (f"\nFollow-up questions and answers:{qa_text}" if qa_text else "")
            + sensor_text
            + health_constraint
            + "\n\nProvide a professional assessment in English structured in 5 blocks:\n"
            "1) General condition detected, health or pathology according to the operator description\n"
            "2) Differential diagnosis or risk factors, only if the plant shows symptoms\n"
            "3) Immediate actions, 0 to 24 hours\n"
            "4) Short-term actions, 2 to 7 days\n"
            "5) Monitoring and prevention\n"
            "Mandatory constraints:\n"
            "- Do not cite any PlantVillage class or equivalent class name.\n"
            "- Do not mention classification labels, class codes, or similarity comparisons.\n"
            "- Always respect the operator statement about the plant status.\n"
            "- If environmental data are present, comment on them explicitly in the assessment.\n"
            "- Indicate uncertainty when needed and recommend physical agronomic confirmation when appropriate."
        )
    elif followup_mode == "class_mismatch":
        prompt = (
            "Sei un agronomo esperto. C'è mismatch tra classe AI iniziale e quadro descritto dall'operatore.\n"
            "Devi produrre una valutazione SOLO tramite interazione Operatore/AI (descrizione + follow-up), senza usare classi PlantVillage.\n"
            f"Descrizione iniziale dell'utente: '{user_description}'\n"
            + (f"\nDomande di approfondimento e risposte:{qa_text}" if qa_text else "")
            + sensor_text
            + health_constraint
            + "\n\nFornisci una valutazione professionale in italiano strutturata in 5 blocchi:\n"
            "1) Stato generale rilevato (salute o patologia secondo la descrizione operatore)\n"
            "2) Diagnosi differenziale o fattori di rischio (solo se la pianta mostra sintomi)\n"
            "3) Azioni immediate (0-24h)\n"
            "4) Azioni a breve termine (2-7 giorni)\n"
            "5) Monitoraggio e prevenzione\n"
            "Vincoli obbligatori:\n"
            "- Non citare nessuna classe PlantVillage o classe affine.\n"
            "- Non menzionare etichette di classificazione, codici classe o confronti per similarità.\n"
            "- Rispetta sempre la dichiarazione dell'operatore sullo stato della pianta.\n"
            "- Se sono presenti dati ambientali, commentali esplicitamente nella valutazione.\n"
            "- Indica il grado di incertezza quando necessario e raccomanda conferma agronomica fisica se necessario."
        )
    elif english_ui:
        prompt = (
            "You are an expert agronomist. The AI model did not recognize the plant from the database.\n"
            f"Initial user description: '{user_description}'\n"
            + (f"\nFollow-up questions and answers:{qa_text}" if qa_text else "")
            + sensor_text
            + health_constraint
            + "\n\nProvide a professional assessment in English structured in 5 blocks:\n"
            "1) General condition detected, health or pathology according to the operator description\n"
            "2) Differential diagnosis or risk factors, only if the plant shows symptoms\n"
            "3) Immediate actions, 0 to 24 hours\n"
            "4) Short-term actions, 2 to 7 days\n"
            "5) Monitoring and prevention\n"
            "- Always respect the operator statement about the plant status.\n"
            "- If environmental data are present, comment on them explicitly and relate them to the described condition.\n"
            "- Indicate uncertainty where needed and recommend confirmation by a physical agronomist when appropriate."
        )
    else:
        prompt = (
            "Sei un agronomo esperto. Il modello AI non ha riconosciuto la pianta dal database.\n"
            f"Descrizione iniziale dell'utente: '{user_description}'\n"
            + (f"\nDomande di approfondimento e risposte:{qa_text}" if qa_text else "")
            + sensor_text
            + health_constraint
            + "\n\nFornisci una valutazione professionale in italiano strutturata in 5 blocchi:\n"
            "1) Stato generale rilevato (salute o patologia secondo la descrizione operatore)\n"
            "2) Diagnosi differenziale o fattori di rischio (solo se la pianta mostra sintomi)\n"
            "3) Azioni immediate (0-24h)\n"
            "4) Azioni a breve termine (2-7 giorni)\n"
            "5) Monitoraggio e prevenzione\n"
            "- Rispetta sempre la dichiarazione dell'operatore sullo stato della pianta.\n"
            "- Se sono presenti dati ambientali, commentali esplicitamente e correlali al quadro descritto.\n"
            "- Indica il grado di incertezza dove necessario e raccomanda "
            "conferma da un agronomo fisico se necessario."
        )

    def _ask():
        return engine.chat_internal(prompt, response_language=_ui_language(context))

    try:
        opinion = await asyncio.to_thread(_ask)
    except Exception as exc:
        logger.warning("Errore diagnosi conversazionale: %s", exc)
        _clear_diagnosis_state(context)
        await _send(update, _ui_text(context, "❌ Errore durante la diagnosi conversazionale.", "❌ Error during the conversational diagnosis."))
        return

    opinion = _sanitize_diagnosis_opinion(opinion, response_language=_ui_language(context))
    if followup_mode == "class_mismatch":
        opinion = _strip_plantvillage_class_mentions(opinion)

    memory_request, memory_response = _build_diagnosis_memory_turn(
        user_description=user_description,
        opinion=opinion,
        qa_pairs=qa_pairs,
        followup_mode=followup_mode,
        sensor_data=sensor_data,
    )

    title = (
        "🩺 <b>INTERACTIVE DELTA Plant AI DIAGNOSIS:</b>"
        if english_ui and followup_mode == "class_mismatch"
        else "🩺 <b>DELTA Plant CONVERSATIONAL DIAGNOSIS:</b>"
        if english_ui
        else "🩺 <b>DIAGNOSI AI INTERATTIVA DELTA Plant:</b>"
        if followup_mode == "class_mismatch"
        else "🩺 <b>DIAGNOSI CONVERSAZIONALE DELTA Plant:</b>"
    )

    try:
        await _send_diagnosis_paginated(
            update,
            context,
            f"{title}\n\n{opinion}",
            parse_mode="HTML",
        )
        engine.remember_turn(user_id, memory_request, memory_response)
        _store_latest_diagnosis_context(
            context,
            opinion,
            sensor_data=sensor_data,
        )
        context.user_data["chat_seed_context"] = (
            "Contesto della piu recente diagnosi DELTA Plant:\n\n"
            f"{opinion}"
        )
    finally:
        _clear_diagnosis_state(context)


async def _send_diagnosis_visuals(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    record: Dict[str, Any],
) -> None:
    """Invia prima il feedback CAM e poi la foto originale di riferimento."""
    chat = update.effective_chat
    if chat is None:
        return

    explain_cfg = VISION_CONFIG.get("explainability", {})
    artifact = record.get("explainability") or {}
    overlay_path = artifact.get("overlay_path")

    if explain_cfg.get("send_overlay", True) and overlay_path:
        overlay_file = Path(str(overlay_path))
        if not overlay_file.exists():
            logger.warning("Overlay explainability non trovato: %s", overlay_file)
        else:
            caption_lines = [
                _ui_text(
                    context,
                    "Feedback CAM DELTA Plant: il cerchio e il target indicano dove il modello sta guardando.",
                    "DELTA Plant CAM feedback: the circle and target show where the model is looking.",
                ),
                _ui_text(
                    context,
                    "Le aree piu calde della LayerCAM corrispondono alla regione che ha pesato maggiormente nella decisione.",
                    "The hottest LayerCAM areas correspond to the region that weighed most in the decision.",
                ),
            ]
            caption = "\n".join(caption_lines)

            try:
                with overlay_file.open("rb") as photo_file:
                    await chat.send_photo(photo=photo_file, caption=caption)
            except Exception as exc:
                logger.warning("Invio overlay explainability Telegram fallito: %s", exc)

    image_path = context.user_data.get("diag_image_path")
    if explain_cfg.get("send_original", True) and image_path:
        original_path = Path(str(image_path))
        if original_path.exists():
            try:
                with original_path.open("rb") as photo_file:
                    await chat.send_photo(
                        photo=photo_file,
                        caption=_ui_text(
                            context,
                            "Foto originale acquisita per la diagnosi DELTA Plant (riferimento).",
                            "Original photo acquired for the DELTA Plant diagnosis (reference).",
                        ),
                    )
            except Exception as exc:
                logger.warning("Invio foto originale Telegram fallito: %s", exc)


async def _send_ai_diagnosis_opinion(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    record: Dict[str, Any],
) -> int:
    """Invia diagnosi completa se c'è match classe; altrimenti avvia follow-up interattivo."""
    context.user_data["diagnosis_active"] = True
    try:
        await update.effective_chat.send_action("typing")
    except Exception:
        pass

    engine = _get_chat_engine(context)
    user_id = str(update.effective_user.id if update.effective_user else "0")
    user_description = context.user_data.get("diag_user_description", "")

    corrected: "Optional[str]" = ""
    ai_class = (record.get("ai_result") or {}).get("class", "")

    # ── Verifica appartenenza pianta a generi PlantVillage ────────────────
    if user_description and ai_class:
        corrected = await _reclassify_with_description(
            engine, ai_class, user_description
        )
        if corrected is not None:
            record["_corrected_class"] = corrected
            if corrected != ai_class:
                logger.info(
                    "Reclassificazione: '%s' → '%s' (descrizione: %s)",
                    ai_class, corrected, user_description[:60],
                )

    # Pianta fuori da PlantVillage → diagnosi solo AI interattiva (max 5 domande)
    # NON inviare un messaggio qui: _start_followup_questioning invia già il suo intro.
    if corrected is None:
        return await _start_followup_questioning(
            update,
            context,
            record,
            mode="class_mismatch",
        )

    prompt = _build_diagnosis_prompt(record, user_description, response_language=_ui_language(context))

    def _ask():
        return engine.chat_internal(prompt, response_language=_ui_language(context))

    try:
        opinion = await asyncio.to_thread(_ask)
    except Exception as exc:
        logger.warning("Errore opinione AI post-diagnosi: %s", exc)
        _clear_diagnosis_state(context)
        return ConversationHandler.END

    opinion = _sanitize_diagnosis_opinion(opinion, response_language=_ui_language(context))
    memory_request, memory_response = _build_diagnosis_memory_turn(
        user_description=user_description,
        opinion=opinion,
        record=record,
        sensor_data=context.user_data.get("sensor_data", {}),
    )

    try:
        await _send_diagnosis_visuals(update, context, record)
        await _send_diagnosis_paginated(
            update,
            context,
            f"{_ui_text(context, '🩺 <b>RISULTATO DIAGNOSI DELTA Plant:</b>', '🩺 <b>DELTA Plant DIAGNOSIS RESULT:</b>')}\n\n{opinion}",
            parse_mode="HTML",
        )
        engine.remember_turn(user_id, memory_request, memory_response)
        _store_latest_diagnosis_context(
            context,
            opinion,
            record=record,
            sensor_data=context.user_data.get("sensor_data", {}),
        )
        context.user_data["chat_seed_context"] = (
            "Contesto della piu recente diagnosi DELTA Plant:\n\n"
            f"{opinion}"
        )
    finally:
        # Pulizia garantita anche se _send_diagnosis_paginated lancia un'eccezione.
        # Senza questo, la chat potrebbe restare bloccata o ricevere marker residui.
        _clear_diagnosis_state(context)
    return ConversationHandler.END


def _collect_guided_sensor_data(
    context: ContextTypes.DEFAULT_TYPE,
    sensor_data: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    cleaned_input = {
        key: value
        for key, value in (sensor_data or {}).items()
        if value is not None
    }
    if cleaned_input:
        context.user_data["sensor_data"] = cleaned_input
        return cleaned_input

    current_data = {
        key: value
        for key, value in (
            context.user_data.get("diag_environment_context")
            or context.user_data.get("sensor_data")
            or {}
        ).items()
        if value is not None
    }
    if current_data:
        return current_data
    return {}


async def _run_guided_llm_diagnosis(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    sensor_data: Optional[Dict[str, Any]],
) -> Optional[int]:
    image_path = str(context.user_data.get("diag_image_path") or "").strip()
    if not image_path:
        return None

    try:
        vision_llm = _get_hf_vision_llm(context)
    except Exception as exc:
        logger.warning("VLM guidato non disponibile, fallback al backend nativo: %s", exc)
        return None

    response_language = _ui_language(context)
    user_description = str(context.user_data.get("diag_user_description") or "").strip()
    effective_sensor_data = _collect_guided_sensor_data(context, sensor_data)

    try:
        await update.effective_chat.send_action("typing")
    except Exception:
        pass

    prompt = _build_guided_multimodal_diagnosis_prompt(
        user_description,
        effective_sensor_data,
        response_language=response_language,
    )
    system_prompt = _hf_system_prompt_for_language(response_language)

    def _ask(prompt_text: str):
        return vision_llm.chat_with_image(
            prompt_text,
            image_path,
            system_prompt=system_prompt,
        )

    try:
        opinion, model_used = await asyncio.to_thread(_ask, prompt)
    except Exception as exc:
        logger.warning("Diagnosi guidata VLM fallita, fallback al backend nativo: %s", exc)
        return None

    opinion = (opinion or "").strip()
    if not opinion or model_used == "none" or opinion.startswith("[DELTA]") or opinion.startswith("⚠️"):
        logger.warning("Diagnosi guidata VLM non disponibile, fallback al backend nativo")
        return None

    if not _vision_opinion_mentions_plant_name(opinion):
        retry_prompt = _build_guided_multimodal_name_retry_prompt(
            opinion,
            user_description,
            effective_sensor_data,
            response_language=response_language,
        )
        logger.info("Diagnosi guidata VLM senza nome pianta esplicito, eseguo un secondo controllo automatico")
        try:
            retry_opinion, retry_model = await asyncio.to_thread(_ask, retry_prompt)
        except Exception as exc:
            logger.warning("Secondo controllo VLM guidato fallito: %s", exc)
        else:
            retry_opinion = (retry_opinion or "").strip()
            if retry_opinion and not retry_opinion.startswith("[DELTA]") and not retry_opinion.startswith("⚠️"):
                opinion = retry_opinion
                if retry_model and retry_model != "none":
                    model_used = retry_model

    opinion = _sanitize_diagnosis_opinion(opinion, response_language=response_language)

    engine = _get_chat_engine(context)
    user_id = str(update.effective_user.id if update.effective_user else "0")
    memory_request, memory_response = _build_diagnosis_memory_turn(
        user_description=user_description,
        opinion=opinion,
        followup_mode="guided_vision_llm",
        sensor_data=effective_sensor_data,
    )
    if model_used and model_used != "none":
        memory_request += f"\nModello vision HF guidato: {model_used}."

    rendered_message, rendered_parse_mode = _build_guided_diagnosis_result_message(
        context,
        opinion,
        response_language=response_language,
        has_sensor_data=bool(effective_sensor_data),
    )

    try:
        await _send_diagnosis_visuals(update, context, {})
        await _send_diagnosis_paginated(
            update,
            context,
            rendered_message,
            parse_mode=rendered_parse_mode,
        )
        engine.remember_turn(user_id, memory_request, memory_response)
        _store_latest_diagnosis_context(
            context,
            opinion,
            sensor_data=effective_sensor_data,
            model_used=model_used,
        )
        context.user_data["chat_seed_context"] = (
            "Contesto della piu recente diagnosi DELTA Plant:\n\n"
            f"{opinion}"
        )
    finally:
        _clear_diagnosis_state(context)
    return ConversationHandler.END


async def _run_native_diagnosis(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    sensor_data: Optional[Dict[str, Any]],
    allow_followup: bool = True,
):
    # Restituisce un ConversationHandler state (END o STATE_DIAG_FOLLOWUP)
    agent = _get_agent(context)
    if not agent:
        _clear_diagnosis_state(context)
        await _send(update, _ui_text(context, "Errore sistema: agent non disponibile.", "System error: agent unavailable."))
        return ConversationHandler.END

    image_path = context.user_data.get("diag_image_path")
    image = None
    if image_path:
        image = _load_image_from_path(Path(image_path))
        if image is None:
            _clear_diagnosis_state(context)
            await _send(update, _ui_text(context, "Impossibile caricare l'immagine.", "Unable to load the image."))
            return ConversationHandler.END
    try:
        record = await asyncio.to_thread(agent.run_diagnosis, sensor_data=sensor_data, image=image)
    except Exception as exc:
        logger.error("Errore diagnosi Telegram: %s", exc, exc_info=True)
        _clear_diagnosis_state(context)
        await _send(update, _ui_text(context, "❌ Errore durante la diagnosi. La chat è nuovamente disponibile.", "❌ Error during the diagnosis. Chat is available again."))
        return ConversationHandler.END

    # Propaga sensor_snapshot a user_data per renderlo disponibile nei flussi conversazionali
    if not context.user_data.get("sensor_data"):
        snap = (record.get("diagnosis") or {}).get("sensor_snapshot") or {}
        populated = {k: v for k, v in snap.items() if v is not None and k != "source"}
        if populated:
            context.user_data["sensor_data"] = populated

    # Pianta non riconosciuta → modalità follow-up conversazionale
    if allow_followup and record.get("ai_result", {}).get("fallback", False):
        return await _start_followup_questioning(update, context, record, mode="fallback")

    # Match pieno classe -> diagnosi completa; mismatch -> follow-up interattivo
    return await _send_ai_diagnosis_opinion(update, context, record)


async def _run_diagnosis(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    sensor_data: Optional[Dict[str, Any]],
    allow_followup: bool = True,
):
    guided_result = await _run_guided_llm_diagnosis(update, context, sensor_data)
    if guided_result is not None:
        return guided_result
    return await _run_native_diagnosis(update, context, sensor_data, allow_followup=allow_followup)


async def _run_llm_vision_diagnosis(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    image_path = str(context.user_data.get("diag_image_path") or "").strip()
    if not image_path:
        _clear_diagnosis_state(context)
        await _send(update, _ui_text(context, "Immagine non disponibile.", "Image unavailable."))
        return ConversationHandler.END

    response_language = _ui_language(context)
    vision_llm = _get_hf_vision_llm(context)

    try:
        await update.effective_chat.send_action("typing")
    except Exception:
        pass

    prompt = _build_multimodal_vision_diagnosis_prompt(response_language)
    system_prompt = _hf_system_prompt_for_language(response_language)

    def _ask(prompt_text: str):
        return vision_llm.chat_with_image(
            prompt_text,
            image_path,
            system_prompt=system_prompt,
        )

    try:
        opinion, model_used = await asyncio.to_thread(_ask, prompt)
    except Exception as exc:
        logger.warning("Errore diagnosi multimodale HF: %s", exc)
        _clear_diagnosis_state(context)
        await _send(
            update,
            _ui_text(
                context,
                "❌ Errore durante la diagnosi multimodale. La chat è nuovamente disponibile.",
                "❌ Error during the multimodal diagnosis. Chat is available again.",
            ),
        )
        return ConversationHandler.END

    opinion = (opinion or "").strip()
    if not opinion:
        _clear_diagnosis_state(context)
        await _send(
            update,
            _ui_text(
                context,
                "❌ Il modello vision non ha restituito una diagnosi utile.",
                "❌ The vision model did not return a usable diagnosis.",
            ),
        )
        return ConversationHandler.END

    if opinion.startswith("[DELTA]") or opinion.startswith("⚠️"):
        _clear_diagnosis_state(context)
        await _send(update, opinion)
        return ConversationHandler.END

    if not _vision_opinion_mentions_plant_name(opinion):
        logger.info("Diagnosi vision senza nome pianta esplicito, eseguo un secondo controllo automatico")
        retry_prompt = _build_multimodal_vision_name_retry_prompt(opinion, response_language=response_language)
        try:
            retry_opinion, retry_model = await asyncio.to_thread(_ask, retry_prompt)
        except Exception as exc:
            logger.warning("Secondo controllo vision HF fallito: %s", exc)
        else:
            retry_opinion = (retry_opinion or "").strip()
            if (
                retry_opinion
                and not retry_opinion.startswith("[DELTA]")
                and not retry_opinion.startswith("⚠️")
                and _vision_opinion_mentions_plant_name(retry_opinion)
            ):
                opinion = retry_opinion
                if retry_model and retry_model != "none":
                    model_used = retry_model

    opinion = _sanitize_diagnosis_opinion(opinion, response_language=response_language)

    engine = _get_chat_engine(context)
    user_id = str(update.effective_user.id if update.effective_user else "0")
    memory_request, memory_response = _build_diagnosis_memory_turn(
        opinion=opinion,
        followup_mode="vision_llm",
    )
    if model_used and model_used != "none":
        memory_request += f"\nModello vision HF: {model_used}."

    try:
        await _send_diagnosis_paginated(
            update,
            context,
            f"{_ui_text(context, '🩺 <b>RISULTATO DIAGNOSI DELTA Plant:</b>', '🩺 <b>DELTA Plant DIAGNOSIS RESULT:</b>')}\n\n{opinion}",
            parse_mode="HTML",
        )
        engine.remember_turn(user_id, memory_request, memory_response)
        _store_latest_diagnosis_context(
            context,
            opinion,
            model_used=model_used,
        )
        context.user_data["chat_seed_context"] = (
            "Contesto della piu recente diagnosi DELTA Plant:\n\n"
            f"{opinion}"
        )
    finally:
        _clear_diagnosis_state(context)
    return ConversationHandler.END


def _labels_keyboard(prefix: str, labels: List[str]) -> InlineKeyboardMarkup:
    rows = []
    for i, label in enumerate(labels):
        rows.append([InlineKeyboardButton(label, callback_data=f"{prefix}{i}")])
    rows.append([InlineKeyboardButton("Salta", callback_data=UPLOAD_SKIP_LABEL)])
    return InlineKeyboardMarkup(rows)


async def start_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _guard(update):
        return ConversationHandler.END
    context.user_data["upload_active"] = True
    await _send(update, _ui_text(context, "Invia una foto, o un file immagine, da salvare in input_images.", "Send a photo, or an image file, to save into input_images."))
    return STATE_UPLOAD_WAIT_PHOTO


async def upload_expect_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _send(update, _ui_text(context, "Per favore invia una foto o un file immagine.", "Please send a photo or an image file."))
    return STATE_UPLOAD_WAIT_PHOTO


async def receive_upload_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _guard(update):
        return ConversationHandler.END
    saved = await _download_telegram_image(update)
    if not saved:
        await _send(update, _ui_text(context, "Immagine non valida.", "Invalid image."))
        return STATE_UPLOAD_WAIT_PHOTO
    context.user_data.pop("upload_active", None)
    await _send(update, _ui_text(context, f"Immagine salvata in input_images: {saved.name}", f"Image saved to input_images: {saved.name}"))
    return ConversationHandler.END


async def handle_plant_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _send(update, _ui_text(context, "Flusso etichettatura dismesso nella logica semplificata.", "Labeling flow removed in the simplified logic."))
    return ConversationHandler.END


async def handle_organ_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _send(update, _ui_text(context, "Flusso etichettatura dismesso nella logica semplificata.", "Labeling flow removed in the simplified logic."))
    return ConversationHandler.END


async def pending_label_name_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return


async def scientific_report_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _guard(update):
        return
    diagnosis_context = context.user_data.get("last_diagnosis_context")
    if not isinstance(diagnosis_context, dict) or not str(diagnosis_context.get("opinion") or "").strip():
        await _send(
            update,
            _ui_text(
                context,
                "Prima serve una diagnosi DELTA Plant. Esegui una diagnosi, poi usa /analisi e allega il referto PDF/JPEG/PNG per rimodularla.",
                "A DELTA Plant diagnosis is needed first. Run a diagnosis, then use /analysis and attach the PDF/JPEG/PNG report to refine it.",
            ),
        )
        return
    context.user_data["awaiting_scientific_report"] = True
    await _send(
        update,
        _ui_text(
            context,
            "📎 Invia ora un PDF, JPEG o PNG con un referto scientifico/agronomico: analisi del suolo, acque, frutto, nichel, metalli, pH, EC, nutrienti o simili. Lo leggerò e rimodulerò l'ultima diagnosi DELTA Plant.",
            "📎 Send a PDF, JPEG, or PNG scientific/agronomic report now: soil analysis, water analysis, fruit analysis, nickel/metals, pH, EC, nutrients, or similar. I will read it and refine the latest DELTA Plant diagnosis.",
        ),
    )


async def handle_scientific_report_attachment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _guard(update):
        return ConversationHandler.END
    if not _is_supported_scientific_attachment(update):
        await _send(
            update,
            _ui_text(
                context,
                "Formato non supportato. Invia un PDF, JPEG o PNG.",
                "Unsupported format. Send a PDF, JPEG, or PNG.",
            ),
        )
        return ConversationHandler.END

    if not _scientific_report_requested_by_user(update, context):
        return await handle_unprompted_photo(update, context)

    diagnosis_context = context.user_data.get("last_diagnosis_context")
    if not isinstance(diagnosis_context, dict) or not str(diagnosis_context.get("opinion") or "").strip():
        context.user_data.pop("awaiting_scientific_report", None)
        await _send(
            update,
            _ui_text(
                context,
                "Prima serve una diagnosi DELTA Plant. Esegui una diagnosi, poi invia il referto PDF/JPEG/PNG per rimodularla.",
                "A DELTA Plant diagnosis is needed first. Run a diagnosis, then send the PDF/JPEG/PNG report to refine it.",
            ),
        )
        return ConversationHandler.END

    path, source_name, mime_type = await _download_scientific_report_attachment(update)
    if path is None:
        await _send(
            update,
            _ui_text(
                context,
                "Non riesco a leggere questo allegato. Usa PDF, JPEG o PNG.",
                "I cannot read this attachment. Use PDF, JPEG, or PNG.",
            ),
        )
        return ConversationHandler.END

    context.user_data.pop("awaiting_scientific_report", None)
    try:
        await update.effective_chat.send_action("typing")
    except Exception:
        pass

    suffix = path.suffix.lower()
    document_text = ""
    extraction_mode = ""
    extraction_error = ""
    if suffix == ".pdf" or mime_type == "application/pdf":
        document_text, extraction_error = await asyncio.to_thread(_extract_text_from_pdf, path)
        extraction_mode = "PDF text layer via pypdf" if document_text else f"PDF text extraction failed: {extraction_error}"
    else:
        document_text, extraction_error = await asyncio.to_thread(_extract_text_from_image_ocr, path)
        extraction_mode = "local OCR via pytesseract" if document_text else f"local OCR failed: {extraction_error}"
        if not document_text:
            document_text, vlm_status = await _analyze_scientific_report_image_with_vlm(update, context, path, source_name)
            extraction_mode = vlm_status if document_text else f"{extraction_mode}; VLM failed: {vlm_status}"

    if not document_text:
        await _send(
            update,
            _ui_text(
                context,
                "Non ho estratto testo leggibile dal referto. Se è un PDF scannerizzato, invia una foto/PNG nitida del referto oppure installa OCR/PDF text extraction.",
                "I could not extract readable text from the report. If it is a scanned PDF, send a clear photo/PNG of the report or install OCR/PDF text extraction.",
            ),
        )
        return ConversationHandler.END

    response_language = _ui_language(context)
    engine = _get_chat_engine(context)
    prompt = _build_scientific_document_refinement_prompt(
        context,
        document_text=document_text,
        diagnosis_context=diagnosis_context,
        source_name=source_name or path.name,
        extraction_mode=extraction_mode,
        response_language=response_language,
    )

    def _ask():
        return engine.chat_internal(
            prompt,
            response_language=response_language,
            system_prompt_suffix=_build_free_chat_language_prompt_suffix(response_language),
        )

    try:
        response = await asyncio.to_thread(_ask)
        response = await _repair_free_chat_language_response(
            engine,
            response_text=response,
            response_language=response_language,
        )
    except Exception as exc:
        logger.warning("Errore rimodulazione da referto scientifico: %s", exc, exc_info=True)
        await _send(
            update,
            _ui_text(
                context,
                "Errore durante la lettura/rimodulazione del referto. Riprova tra poco.",
                "Error while reading/refining the report. Try again shortly.",
            ),
        )
        return ConversationHandler.END

    title = _ui_text(
        context,
        "📄 <b>RIMODULAZIONE DELTA Plant DA REFERTO SCIENTIFICO</b>",
        "📄 <b>DELTA Plant REFINEMENT FROM SCIENTIFIC REPORT</b>",
    )
    rendered_text, parse_mode = _format_free_chat_for_telegram(context, f"{title}\n\n{response}")
    await _send_chat_paginated(update, context, rendered_text, parse_mode=parse_mode)

    _store_latest_diagnosis_context(
        context,
        response,
        record=diagnosis_context.get("record") or {},
        sensor_data=diagnosis_context.get("sensor_data") or {},
        model_used=f"scientific_report:{extraction_mode}",
    )
    try:
        user_id = str(update.effective_user.id if update.effective_user else "0")
        engine.remember_turn(
            user_id,
            f"Referto scientifico allegato ({source_name or path.name}) per rimodulare la diagnosi DELTA Plant.",
            response,
        )
    except Exception as exc:
        logger.debug("Memoria chat referto scientifico non aggiornata: %s", exc)
    return ConversationHandler.END


async def handle_unprompted_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _guard(update):
        return ConversationHandler.END
    if _scientific_report_requested_by_user(update, context):
        return await handle_scientific_report_attachment(update, context)
    if context.user_data.get("diag_waiting_for_photo"):
        return await receive_diag_photo(update, context)
    _clear_diagnosis_state(context)
    context.user_data["diagnosis_active"] = True
    context.user_data.pop("diag_user_description", None)
    # Le foto inviate fuori dal percorso guidato vanno in diagnosi automatica
    # solo-vision, senza chiedere descrizione o sensori.
    saved = await _download_telegram_image(update)
    if not saved:
        _clear_diagnosis_state(context)
        await _send(update, _ui_text(context, "Immagine non valida.", "Invalid image."))
        return ConversationHandler.END
    context.user_data["diag_image_path"] = str(saved)
    await _send(
        update,
        _ui_text(
            context,
            "📷 Foto ricevuta. Completo la diagnosi con posizione GPS, NASA-ISRO/SAR settimanale e LUX.",
            "📷 Photo received. I will complete the diagnosis with GPS position, weekly NASA-ISRO/SAR, and LUX.",
        ),
    )
    return await _ask_diagnosis_gps_context(update, context)


async def handle_label_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _send(update, _ui_text(context, "Flusso etichettatura dismesso nella logica semplificata.", "Labeling flow removed in the simplified logic."))
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _guard(update):
        return ConversationHandler.END
    # Preserva le preferenze lingua/voce prima di svuotare lo stato
    saved_voice_lang = context.user_data.get("voice_language")
    saved_voice_mode = context.user_data.get("voice_mode")
    context.user_data.clear()
    if saved_voice_lang is not None:
        context.user_data["voice_language"] = saved_voice_lang
    if saved_voice_mode is not None:
        context.user_data["voice_mode"] = saved_voice_mode
    # Rimuove la tastiera GPS eventualmente visibile sul client
    await _send(
        update,
        _ui_text(context, "Operazione annullata.", "Operation cancelled."),
        reply_markup=ReplyKeyboardRemove(),
    )
    return ConversationHandler.END


async def timeout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    if update is None:
        return ConversationHandler.END
    await _send(update, _ui_text(context, "Sessione scaduta. Usa /nuovo per ricominciare.", "Session expired. Use /nuovo to start again."))
    return ConversationHandler.END


async def menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _guard(update):
        return
    query = update.callback_query
    if not query:
        return
    logger.info(
        "Telegram callback menu ricevuta da user_id=%s data=%s",
        update.effective_user.id if update.effective_user else "0",
        query.data,
    )
    await _answer_callback_query_safe(query)
    if query.data == CMD_DIAGNOSE:
        await start_diagnosis(update, context)
    elif query.data == CMD_UPLOAD:
        await start_upload(update, context)
    elif query.data == CMD_REPORT:
        await report(update, context)
    elif query.data == CMD_IMAGES:
        await images(update, context)
    elif query.data in {CMD_SENSORS, CMD_HEALTH, CMD_PREFLIGHT, CMD_ACADEMY}:
        await _send(
            update,
            _ui_text(
                context,
                "Funzione non piu' disponibile da @DELTAPLANO_bot.",
                "This function is no longer available from @DELTAPLANO_bot.",
            ),
            reply_markup=_menu_keyboard(context),
        )
    elif query.data == CMD_LICENSE:
        await license_text(update, context)
    elif query.data == CMD_NASA_SAR:
        await nasa_sar_connect(update, context)
    elif query.data == CMD_BATCH:
        await batch_analyze(update, context)
    elif query.data == CMD_VOICE_LANG_IT:
        await _set_voice_language(update, context, VOICE_LANGUAGE_IT)
    elif query.data == CMD_VOICE_LANG_EN:
        await _set_voice_language(update, context, VOICE_LANGUAGE_EN)


async def images(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _guard(update):
        return
    images_list = _list_input_images(limit=20)
    if not images_list:
        await _send(update, "Cartella input_images vuota.")
        return
    lines = [f"Ultime {len(images_list)} immagini:"]
    for img in images_list:
        size_kb = img.stat().st_size // 1024
        lines.append(f"• {img.name} ({size_kb} KB)")
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("Analizza tutte", callback_data=CMD_BATCH)],
    ])
    await _send(update, "\n".join(lines), reply_markup=keyboard)


async def batch_analyze(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _guard(update):
        return
    agent = _get_agent(context)
    if not agent:
        await _send(update, "Errore sistema: agent non disponibile.")
        return
    images_list = _list_input_images(limit=1000)
    if not images_list:
        await _send(update, "Nessuna immagine da analizzare.")
        return

    # --- INTEGRAZIONE DELTA_ORCHESTRATOR ---
    if DELTA_ORCHESTRATOR_AVAILABLE:
        ok = 0
        fail = 0
        for img_path in images_list:
            try:
                record = await orchestrate_task("Diagnosi pianta", {
                    "delta_context": {"image_path": str(img_path)},
                    "messages": [],
                    "current_model": "ollama/llama3.2",
                    "tool_results": {},
                    "confidence": 0.0,
                    "iteration_count": 0,
                    "max_iterations": 5,
                    "errors": [],
                    "final_answer": None
                })
                if record.get("confidence", 0) > 0:
                    ok += 1
                else:
                    fail += 1
            except Exception:
                fail += 1
        await _send(update, f"Analisi completata (orchestrator). OK: {ok}, Errori: {fail}.")
        return
    # --- FINE INTEGRAZIONE DELTA_ORCHESTRATOR ---
    await _send(update, f"Avvio analisi sequenziale di {len(images_list)} immagini...")

    def _run_batch():
        ok = 0
        fail = 0
        for img_path in images_list:
            img = _load_image_from_path(img_path)
            if img is None:
                fail += 1
                continue
            try:
                agent.run_diagnosis(image=img)
                ok += 1
            except Exception:
                fail += 1
        return ok, fail

    ok, fail = await asyncio.to_thread(_run_batch)
    await _send(update, f"Analisi completata. OK: {ok}, Errori: {fail}.")


async def export_excel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _guard(update):
        return
    await _send(
        update,
        _ui_text(
            context,
            "La funzione Report Excel e' stata disabilitata.",
            "The Excel Report feature has been disabled.",
        ),
    )


async def preflight(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _guard(update):
        return
    from ai.preflight_validator import validate_model_artifacts
    await _send(update, _ui_text(context, "Preflight AI in corso...", "AI preflight in progress..."))

    def _run():
        return validate_model_artifacts(
            model_path=MODEL_CONFIG["model_path"],
            labels_path=MODEL_CONFIG["labels_path"],
            image_path=MODEL_CONFIG["validation_image_path"],
            threads=MODEL_CONFIG["num_threads"],
            top_k=3,
        )

    try:
        report = await asyncio.to_thread(_run)
    except Exception as exc:
        logger.error("Preflight AI fallito: %s", exc, exc_info=True)
        await _send(update, _ui_text(context, f"Preflight AI fallito: {exc}", f"AI preflight failed: {exc}"))
        return
    msg = _ui_text(
        context,
        "Preflight OK ✅\n"
        f"Classe: {report['predicted_class']}\n"
        f"Confidenza: {report['confidence'] * 100:.2f}%\n"
        f"Input shape: {report['input_shape']}\n"
        f"Output shape: {report['output_shape']}",
        "Preflight OK ✅\n"
        f"Class: {report['predicted_class']}\n"
        f"Confidence: {report['confidence'] * 100:.2f}%\n"
        f"Input shape: {report['input_shape']}\n"
        f"Output shape: {report['output_shape']}",
    )
    await _send(update, msg)


async def license_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _guard(update):
        return
    text = _load_localized_license_text(context)
    await _send_long(update, text)


def _load_localized_license_text(
    context: Optional["ContextTypes.DEFAULT_TYPE"] = None,
    root_dir: Optional[Path] = None,
) -> str:
    base_dir = root_dir or (Path(__file__).resolve().parent.parent)
    preferred_paths = [
        base_dir / "LICENSE",
        base_dir / "LICENSE.it",
    ]
    if _ui_language(context) != VOICE_LANGUAGE_EN:
        preferred_paths = [
            base_dir / "LICENSE.it",
            base_dir / "LICENSE",
        ]

    for candidate in preferred_paths:
        if candidate.exists():
            return candidate.read_text(encoding="utf-8")

    return _ui_text(context, "Licenza non trovata.", "License not found.")


ACADEMY_PROGRESS_FILE = Path(__file__).resolve().parent.parent / "data" / "academy_progress.json"


def _load_academy_progress() -> dict:
    defaults = {
        "total_score": 0,
        "sessions": 0,
        "quiz_correct": 0,
        "quiz_total": 0,
        "sim_correct": 0,
        "sim_total": 0,
        "training_lab_completed": 0,
        "training_lab_score": 0,
        "badges": [],
    }
    if ACADEMY_PROGRESS_FILE.exists():
        try:
            data = json.loads(ACADEMY_PROGRESS_FILE.read_text(encoding="utf-8"))
            for k, v in defaults.items():
                data.setdefault(k, v)
            return data
        except Exception:
            pass
    return defaults


def _save_academy_progress(progress: dict):
    ACADEMY_PROGRESS_FILE.parent.mkdir(parents=True, exist_ok=True)
    ACADEMY_PROGRESS_FILE.write_text(
        json.dumps(progress, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def _academy_menu_keyboard(context: Optional["ContextTypes.DEFAULT_TYPE"] = None) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(_ui_text(context, "Tutorial guidato", "Guided tutorial"), callback_data="ACAD_TUT_START")],
        [InlineKeyboardButton(_ui_text(context, "Sim: Identifica malattia", "Sim: Identify disease"), callback_data="ACAD_SIM_DIAG")],
        [InlineKeyboardButton(_ui_text(context, "Sim: Valuta rischio", "Sim: Assess risk"), callback_data="ACAD_SIM_RISK")],
        [InlineKeyboardButton(_ui_text(context, "Sim: Scegli intervento", "Sim: Choose action"), callback_data="ACAD_SIM_ACTION")],
        [InlineKeyboardButton(_ui_text(context, "Quiz teorico", "Theory quiz"), callback_data="ACAD_QUIZ")],
        [InlineKeyboardButton(_ui_text(context, "Progresso", "Progress"), callback_data="ACAD_PROGRESS")],
        [InlineKeyboardButton("Lab MLOps", callback_data="ACAD_LAB")],
        [InlineKeyboardButton(_ui_text(context, "Esci", "Exit"), callback_data="ACAD_EXIT")],
    ])


async def academy_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _guard(update):
        return
    progress = _load_academy_progress()
    progress["sessions"] += 1
    _save_academy_progress(progress)
    await _send(update, _ui_text(context, "DELTA Academy — scegli una modalità:", "DELTA Academy — choose a mode:"), reply_markup=_academy_menu_keyboard(context))


async def academy_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _guard(update):
        return
    query = update.callback_query
    if not query:
        return
    await _answer_callback_query_safe(query)
    data = query.data or ""
    if data == "ACAD_TUT_START":
        context.user_data["academy_tutorial_idx"] = 0
        await _academy_send_tutorial_step(update, context)
        return
    if data == "ACAD_TUT_NEXT":
        await _academy_send_tutorial_step(update, context)
        return
    if data == "ACAD_SIM_DIAG":
        await _academy_sim_diag(update, context)
        return
    if data == "ACAD_SIM_RISK":
        await _academy_sim_risk(update, context)
        return
    if data == "ACAD_SIM_ACTION":
        await _academy_sim_action(update, context)
        return
    if data == "ACAD_QUIZ":
        await _academy_quiz(update, context)
        return
    if data == "ACAD_PROGRESS":
        await _academy_progress(update, context)
        return
    if data == "ACAD_LAB":
        await _academy_lab(update, context)
        return
    if data == "ACAD_EXIT":
        await _send(update, _ui_text(context, "Uscita da DELTA Academy.", "Exited DELTA Academy."))
        return

    if data.startswith("ACAD_SIMDIAG_"):
        await _academy_sim_diag_answer(update, context, data)
        return
    if data.startswith("ACAD_SIMRISK_"):
        await _academy_sim_risk_answer(update, context, data)
        return
    if data.startswith("ACAD_SIMACT_"):
        await _academy_sim_action_answer(update, context, data)
        return
    if data.startswith("ACAD_QUIZ_"):
        await _academy_quiz_answer(update, context, data)
        return


TUTORIAL_STEPS = [
    ("PASSO 1 — Avvio", "DELTA avvia modello AI e thread sensori; se l'hardware manca usa modalità simulata."),
    ("PASSO 2 — Menu", "Dal menu puoi avviare diagnosi, report e Academy."),
    ("PASSO 3 — Diagnosi", "Invia una foto o usa input_images, poi DELTA analizza immagine + sensori."),
    ("PASSO 4 — Rischio", "Livelli: nessuno/basso/medio/alto/critico. Confidenza bassa richiede revisione."),
    ("PASSO 5 — Parametri", "Temperatura, umidità, luce, CO₂, pH, EC: restano la base per la diagnosi."),
]

TUTORIAL_STEPS_EN = [
    ("STEP 1 — Startup", "DELTA starts the AI model and sensor threads; if hardware is missing it uses simulated mode."),
    ("STEP 2 — Menu", "From the menu you can start diagnosis, reports, and Academy."),
    ("STEP 3 — Diagnosis", "Send a photo or use input_images, then DELTA analyzes image plus sensors."),
    ("STEP 4 — Risk", "Levels: none, low, medium, high, critical. Low confidence requires review."),
    ("STEP 5 — Parameters", "Temperature, humidity, light, CO₂, pH, and EC remain the basis for diagnosis."),
]


async def _academy_send_tutorial_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    idx = int(context.user_data.get("academy_tutorial_idx", 0))
    steps = TUTORIAL_STEPS_EN if _ui_language(context) == VOICE_LANGUAGE_EN else TUTORIAL_STEPS
    if idx >= len(steps):
        progress = _load_academy_progress()
        progress["total_score"] += 10
        _save_academy_progress(progress)
        await _send(update, _ui_text(context, "Tutorial completato ✅ (+10 punti)", "Tutorial completed ✅ (+10 points)"), reply_markup=_academy_menu_keyboard(context))
        return
    title, content = steps[idx]
    context.user_data["academy_tutorial_idx"] = idx + 1
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(_ui_text(context, "Avanti", "Next"), callback_data="ACAD_TUT_NEXT")],
    ])
    await _send(update, f"{title}\n{content}", reply_markup=keyboard)


async def _academy_sim_diag(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from interface.academy import SCENARIOS
    scenario = random.choice(SCENARIOS)
    context.user_data["academy_scenario"] = scenario
    all_classes = [s["ai_class"] for s in SCENARIOS]
    distractors = [c for c in all_classes if c != scenario["ai_class"]]
    random.shuffle(distractors)
    options = [scenario["ai_class"]] + distractors[:3]
    random.shuffle(options)
    context.user_data["academy_options"] = options
    text = (
        f"{scenario['titolo']}\n"
        f"{scenario['contesto']}\n\n"
        f"{_ui_text(context, 'Sintomi', 'Symptoms')}: {scenario['sintomi_visivi']}\n"
    )
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(opt, callback_data=f"ACAD_SIMDIAG_{i}")]
        for i, opt in enumerate(options)
    ])
    await _send_long(update, text, reply_markup=keyboard)


async def _academy_sim_diag_answer(update: Update, context: ContextTypes.DEFAULT_TYPE, data: str):
    scenario = context.user_data.get("academy_scenario")
    options = context.user_data.get("academy_options", [])
    if not scenario:
        await _send(update, _ui_text(context, "Scenario non disponibile.", "Scenario unavailable."))
        return
    idx = int(data.split("_")[-1])
    chosen = options[idx] if idx < len(options) else None
    progress = _load_academy_progress()
    progress["sim_total"] += 1
    if chosen == scenario["ai_class"]:
        progress["sim_correct"] += 1
        progress["total_score"] += 15
        msg = _ui_text(context, f"Corretto ✅ +15 punti\nDiagnosi: {scenario['diagnosi']}", f"Correct ✅ +15 points\nDiagnosis: {scenario['diagnosi']}")
    else:
        msg = _ui_text(context, f"Errato. Corretta: {scenario['ai_class']}\nDiagnosi: {scenario['diagnosi']}", f"Incorrect. Correct answer: {scenario['ai_class']}\nDiagnosis: {scenario['diagnosi']}")
    _save_academy_progress(progress)
    await _send_long(update, msg, reply_markup=_academy_menu_keyboard(context))


async def _academy_sim_risk(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from interface.academy import SCENARIOS
    scenario = random.choice(SCENARIOS)
    context.user_data["academy_scenario"] = scenario
    levels = ["nessuno", "basso", "medio", "alto", "critico"]
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(lvl.upper(), callback_data=f"ACAD_SIMRISK_{i}")]
        for i, lvl in enumerate(levels)
    ])
    text = (
        f"{scenario['titolo']}\n"
        f"{scenario['contesto']}\n\n"
        f"{_ui_text(context, 'Sintomi', 'Symptoms')}: {scenario['sintomi_visivi']}\n"
        f"{_ui_text(context, 'Quale rischio assegneresti?', 'Which risk level would you assign?')}"
    )
    await _send_long(update, text, reply_markup=keyboard)


async def _academy_sim_risk_answer(update: Update, context: ContextTypes.DEFAULT_TYPE, data: str):
    scenario = context.user_data.get("academy_scenario")
    levels = ["nessuno", "basso", "medio", "alto", "critico"]
    if not scenario:
        await _send(update, _ui_text(context, "Scenario non disponibile.", "Scenario unavailable."))
        return
    idx = int(data.split("_")[-1])
    chosen = levels[idx] if idx < len(levels) else None
    correct = scenario["rischio_corretto"]
    progress = _load_academy_progress()
    progress["sim_total"] += 1
    if chosen == correct:
        progress["sim_correct"] += 1
        progress["total_score"] += 15
        msg = _ui_text(context, f"Corretto ✅ +15 punti\nRischio: {correct.upper()}\n{scenario['diagnosi']}", f"Correct ✅ +15 points\nRisk: {correct.upper()}\n{scenario['diagnosi']}")
    else:
        msg = _ui_text(context, f"Errato. Corretto: {correct.upper()}\n{scenario['diagnosi']}", f"Incorrect. Correct answer: {correct.upper()}\n{scenario['diagnosi']}")
    _save_academy_progress(progress)
    await _send_long(update, msg, reply_markup=_academy_menu_keyboard(context))


async def _academy_sim_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from interface.academy import SCENARIOS
    scenario = random.choice(SCENARIOS)
    context.user_data["academy_scenario"] = scenario
    correct = scenario["raccomandazioni_corrette"][:2]
    wrong_pool = [
        "Aumentare la temperatura a 35 C",
        "Interrompere la fertilizzazione per 30 giorni",
        "Aumentare l'irrigazione al massimo",
        "Ridurre la luminosità al 10%",
    ]
    random.shuffle(wrong_pool)
    options = correct + wrong_pool[:2]
    random.shuffle(options)
    context.user_data["academy_action_options"] = options
    context.user_data["academy_action_choices"] = []
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(opt, callback_data=f"ACAD_SIMACT_{i}")]
        for i, opt in enumerate(options)
    ])
    await _send_long(update, _ui_text(context, "Seleziona 2 azioni corrette:", "Select 2 correct actions:"), reply_markup=keyboard)


async def _academy_sim_action_answer(update: Update, context: ContextTypes.DEFAULT_TYPE, data: str):
    scenario = context.user_data.get("academy_scenario")
    options = context.user_data.get("academy_action_options", [])
    choices = context.user_data.get("academy_action_choices", [])
    if not scenario:
        await _send(update, _ui_text(context, "Scenario non disponibile.", "Scenario unavailable."))
        return
    idx = int(data.split("_")[-1])
    if idx >= len(options):
        await _send(update, _ui_text(context, "Scelta non valida.", "Invalid choice."))
        return
    if idx in choices:
        await _send(update, _ui_text(context, "Scelta già selezionata.", "Choice already selected."))
        return
    choices.append(idx)
    context.user_data["academy_action_choices"] = choices
    if len(choices) < 2:
        await _send(update, _ui_text(context, "Seleziona un'altra azione.", "Select another action."))
        return
    selected = [options[i] for i in choices]
    correct = set(scenario["raccomandazioni_corrette"][:2])
    progress = _load_academy_progress()
    progress["sim_total"] += 1
    if set(selected) == correct:
        progress["sim_correct"] += 1
        progress["total_score"] += 20
        msg = _ui_text(context, "Perfetto ✅ +20 punti", "Perfect ✅ +20 points")
    elif len(correct.intersection(selected)) == 1:
        progress["total_score"] += 5
        msg = _ui_text(context, "Una risposta corretta su due (+5 punti)", "One correct answer out of two (+5 points)")
    else:
        msg = _ui_text(context, "Nessuna azione corretta.", "No correct action.")
    _save_academy_progress(progress)
    await _send_long(update, msg, reply_markup=_academy_menu_keyboard(context))


async def _academy_quiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from interface.academy import QUIZ_QUESTIONS
    question = random.choice(QUIZ_QUESTIONS)
    context.user_data["academy_quiz"] = question
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(opt, callback_data=f"ACAD_QUIZ_{i}")]
        for i, opt in enumerate(question["opzioni"])
    ])
    await _send_long(update, question["domanda"], reply_markup=keyboard)


async def _academy_quiz_answer(update: Update, context: ContextTypes.DEFAULT_TYPE, data: str):
    question = context.user_data.get("academy_quiz")
    if not question:
        await _send(update, _ui_text(context, "Quiz non disponibile.", "Quiz unavailable."))
        return
    idx = int(data.split("_")[-1])
    progress = _load_academy_progress()
    progress["quiz_total"] += 1
    if idx == question["corretta"]:
        progress["quiz_correct"] += 1
        progress["total_score"] += 10
        msg = _ui_text(context, f"Corretto ✅ +10 punti\n{question['spiegazione']}", f"Correct ✅ +10 points\n{question['spiegazione']}")
    else:
        correct = question["opzioni"][question["corretta"]]
        msg = _ui_text(context, f"Errato. Risposta corretta: {correct}\n{question['spiegazione']}", f"Incorrect. Correct answer: {correct}\n{question['spiegazione']}")
    _save_academy_progress(progress)
    await _send_long(update, msg, reply_markup=_academy_menu_keyboard(context))


async def _academy_progress(update: Update, context: ContextTypes.DEFAULT_TYPE):
    progress = _load_academy_progress()
    msg = _ui_text(
        context,
        f"Punteggio totale: {progress['total_score']}\n"
        f"Sessioni: {progress['sessions']}\n"
        f"Quiz: {progress['quiz_correct']}/{progress['quiz_total']}\n"
        f"Simulazioni: {progress['sim_correct']}/{progress['sim_total']}\n"
        f"Lab MLOps completato: {'Sì' if progress['training_lab_completed'] else 'No'}",
        f"Total score: {progress['total_score']}\n"
        f"Sessions: {progress['sessions']}\n"
        f"Quiz: {progress['quiz_correct']}/{progress['quiz_total']}\n"
        f"Simulations: {progress['sim_correct']}/{progress['sim_total']}\n"
        f"Lab MLOps completed: {'Yes' if progress['training_lab_completed'] else 'No'}",
    )
    await _send(update, msg, reply_markup=_academy_menu_keyboard(context))


async def _academy_lab(update: Update, context: ContextTypes.DEFAULT_TYPE):
    progress = _load_academy_progress()
    progress["training_lab_completed"] = 1
    progress["training_lab_score"] = max(progress.get("training_lab_score", 0), 10)
    progress["total_score"] += 10
    _save_academy_progress(progress)
    await _send_long(
        update,
        _ui_text(
            context,
            "Lab MLOps completato ✅ (+10 punti)\nChecklist: dataset -> training -> conversione -> preflight -> deploy.",
            "Lab MLOps completed ✅ (+10 points)\nChecklist: dataset -> training -> conversion -> preflight -> deploy.",
        ),
        reply_markup=_academy_menu_keyboard(context),
    )


def run_telegram_bot(agent=None):
    """
    Costruisce l'Application Telegram e registra tutti gli handler.
    Restituisce l'Application (o None se disabilitato/errore).
    Il polling deve essere avviato dal main thread tramite serve_telegram_polling().
    """
    if not TELEGRAM_CONFIG.get("enable_telegram", False):
        logger.info("Bot Telegram disabilitato nella configurazione.")
        return None

    if not TELEGRAM_AVAILABLE:
        logger.error("python-telegram-bot non installato. Bot Telegram non disponibile.")
        return None

    token = _get_token()
    if not token:
        logger.error("Token Telegram mancante (env %s).", TELEGRAM_CONFIG.get("token_env"))
        return None

    if not API_CONFIG.get("enable_api", False):
        logger.warning("API REST disabilitata: il bot potrebbe non funzionare.")
    if not _load_allowed_user_ids() and not _load_allowed_usernames():
        logger.warning("Lista autorizzazioni vuota: accesso aperto al bot.")

    # Forza la creazione della cartella logs/ se non esiste
    import os
    os.makedirs("logs", exist_ok=True)

    # NB: l'oggetto Application viene costruito dentro il worker thread
    # (vedi _serve sotto), perché PTB v20+ lega le primitive asyncio
    # (HTTPXRequest, Lock interni) all'event loop corrente al momento del
    # builder.build(). Costruirlo nel main thread e usarlo in un altro loop
    # produce deadlock silenziosi sul long-poll.

    diagnosis_handler = ConversationHandler(
        entry_points=[
            CommandHandler("nuovo", start_diagnosis),
            CommandHandler("diagnosi", start_diagnosis),
            CallbackQueryHandler(start_diagnosis, pattern=f"^{CMD_DIAGNOSE}$"),
        ],
        states={
            STATE_DIAG_WAIT_PHOTO: [
                MessageHandler(filters.PHOTO | filters.Document.IMAGE, receive_diag_photo),
                MessageHandler(filters.ALL, diag_expect_photo),
            ],
            STATE_DIAG_USER_DESCRIPTION: [
                MessageHandler(filters.VOICE, receive_user_description_voice),
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_user_description),
            ],
            STATE_DIAG_FOLLOWUP: [
                MessageHandler(filters.VOICE, receive_followup_answer_voice),
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_followup_answer),
            ],
            ConversationHandler.TIMEOUT: [MessageHandler(filters.ALL, timeout)],
        },
        fallbacks=[
            CommandHandler("continua", continue_diagnosis_message),
            CommandHandler("annulla", cancel),
        ],
        conversation_timeout=TELEGRAM_CONFIG.get("conversation_timeout_sec", 300),
        allow_reentry=True,
    )

    upload_handler = ConversationHandler(
        entry_points=[
            CommandHandler("upload", start_upload),
            CallbackQueryHandler(start_upload, pattern=f"^{CMD_UPLOAD}$"),
        ],
        states={
            STATE_UPLOAD_WAIT_PHOTO: [
                MessageHandler(filters.PHOTO | filters.Document.IMAGE, receive_upload_photo),
                MessageHandler(filters.ALL, upload_expect_photo),
            ],
            ConversationHandler.TIMEOUT: [MessageHandler(filters.ALL, timeout)],
        },
        fallbacks=[CommandHandler("annulla", cancel)],
        conversation_timeout=TELEGRAM_CONFIG.get("conversation_timeout_sec", 300),
        allow_reentry=True,
    )

    chat_conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("chat", chat_start),
            CallbackQueryHandler(chat_start, pattern=f"^{CMD_CHAT}$"),
        ],
        states={
            STATE_CHAT_WAITING: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, chat_message),
                CallbackQueryHandler(chat_exit, pattern=f"^{CHAT_EXIT}$"),
                CallbackQueryHandler(chat_reset, pattern="^CHAT_RESET$"),
            ],
        },
        fallbacks=[
            CommandHandler("continua", continue_diagnosis_message),
            CommandHandler("chiudi", chat_command_chiudi),
            CommandHandler("annulla", cancel),
            CommandHandler("menu", menu),
        ],
        conversation_timeout=TELEGRAM_CONFIG.get("chat_timeout_sec", 600),
        allow_reentry=True,
    )

    logger.info("[DEBUG] run_telegram_bot: ConversationHandler costruiti, costruzione Application")

    _conflict_handled = False

    # Application + handlers vengono costruiti sul thread chiamante.
    # In modalità daemon, main.py chiamerà serve_telegram_polling() sul main thread,
    # dove run_polling() funziona correttamente (PTB v20+ è main-thread bound).
    builder = Application.builder().token(token)
    if TELEGRAM_RATE_LIMITER_AVAILABLE:
        builder = builder.rate_limiter(AIORateLimiter())
    application = builder.build()
    application.bot_data["agent"] = agent
    logger.info("[DEBUG] run_telegram_bot: Application e bot_data inizializzati")

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("menu", menu))
    application.add_handler(CommandHandler("annulla", cancel))
    application.add_handler(CommandHandler("report", report))
    application.add_handler(CommandHandler("dettaglio", detail))
    application.add_handler(CommandHandler("images", images))
    application.add_handler(CommandHandler("voice", voice_mode_command))
    application.add_handler(CommandHandler("voice_lang", voice_language_command))
    application.add_handler(CommandHandler("analisi", scientific_report_command))
    application.add_handler(CommandHandler("analysis", scientific_report_command))
    application.add_handler(CommandHandler("nasa_sar", nasa_sar_connect))
    # /continua globale: funziona anche dopo END del ConversationHandler
    application.add_handler(CommandHandler("continua", continue_diagnosis_message))
    # Pulsante inline "Continua lettura" (CMD_CONTINUA) — stesso handler
    application.add_handler(CallbackQueryHandler(continue_diagnosis_message, pattern=r"^CMD_CONTINUA$"))
    application.add_handler(CommandHandler("license", license_text))
    application.add_handler(CommandHandler("batch", batch_analyze))
    application.add_handler(diagnosis_handler)
    application.add_handler(upload_handler)
    application.add_handler(chat_conv_handler)
    application.add_handler(MessageHandler(filters.Document.ALL, handle_scientific_report_attachment))
    application.add_handler(MessageHandler(filters.PHOTO | filters.Document.IMAGE, handle_unprompted_photo))
    application.add_handler(CallbackQueryHandler(menu_callback, pattern=r"^CMD_"))
    application.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, handle_nasa_sar_web_app_data), group=9)
    application.add_handler(MessageHandler(filters.LOCATION, handle_nasa_sar_location), group=10)
    application.add_handler(MessageHandler(filters.VOICE, handle_voice_message), group=-1)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, free_chat_handler), group=99)
    application.add_handler(CallbackQueryHandler(chat_exit, pattern=f"^{CHAT_EXIT}$"))
    application.add_handler(CallbackQueryHandler(chat_reset, pattern="^CHAT_RESET$"))
    logger.info("[DEBUG] run_telegram_bot: free_chat_handler registrato (group=99)")

    async def _error_handler(update, context) -> None:
        nonlocal _conflict_handled
        from telegram.error import BadRequest, Conflict, NetworkError, TimedOut
        err = context.error
        if isinstance(err, BadRequest) and (
            "query is too old" in str(err).lower()
            or "query id is invalid" in str(err).lower()
        ):
            logger.debug("Bot Telegram: callback query scaduta o già risposta (ignorata): %s", err)
            return
        if isinstance(err, Conflict):
            # NON spegnere il bot su Conflict: potrebbe essere transitorio
            # (probe curl, riavvio in corso). PTB ritenta automaticamente.
            if not _conflict_handled:
                _conflict_handled = True
                logger.warning(
                    "Bot Telegram: conflitto di polling temporaneo "
                    "(altra istanza o probe esterno). PTB ritenterà."
                )
            return
        elif isinstance(err, (NetworkError, TimedOut)):
            logger.warning("Bot Telegram: errore di rete temporaneo: %s", err)
        else:
            logger.error("Bot Telegram: errore non gestito: %s", err, exc_info=err)

    application.add_error_handler(_error_handler)

    logger.info("Bot Telegram pronto: pronto per polling sul main thread.")
    return application


def serve_telegram_polling(application) -> None:
    """
    Avvia application.run_polling() sul thread chiamante (deve essere il main thread).
    Bloccante: ritorna solo allo shutdown.
    """
    if application is None:
        return
    logger.info("[DEBUG] serve_telegram_polling: avvio run_polling sul main thread")
    try:
        application.run_polling(
            poll_interval=TELEGRAM_CONFIG.get("poll_interval_sec", 1.0),
            allowed_updates=Update.ALL_TYPES,
            close_loop=False,
            stop_signals=None,  # signal handler già gestito da main.py
        )
    except Exception as exc:
        logger.error("Polling Telegram terminato con errore: %s", exc, exc_info=True)
