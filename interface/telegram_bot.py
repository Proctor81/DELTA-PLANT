"""
DELTA - interface/telegram_bot.py
Bot Telegram interattivo per accesso conversazionale alle API DELTA.
"""

from __future__ import annotations

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
from typing import Any, Dict, Optional, Set, List, Tuple

import requests

try:
    from PIL import Image, ImageDraw
    PIL_AVAILABLE = True
except ImportError:
    Image = None
    ImageDraw = None
    PIL_AVAILABLE = False

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
logger = logging.getLogger("delta.interface.telegram")

_FREE_CHAT_TRANSIENT_MARKERS = (
    "sensor_index",
    "diag_image_path",
    "diag_fallback_record",
    "diag_followup_qa",
    "diag_followup_count",
    "diag_followup_last_question",
    "diag_user_description",
    "diag_followup_mode",
    "diag_pending_chunks",
    "awaiting_nasa_sar_location",
)

_DIAG_TRANSIENT_KEYS = (
    *_FREE_CHAT_TRANSIENT_MARKERS,
    "diag_pending_parse_mode",
    "diag_pending_closing",
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

_VOICE_GUIDED_DIAGNOSIS_REJECT = (
    "❌ La modalità vocale non è supportata durante la diagnosi guidata di DELTA Plant.\n"
    "Per favore usa messaggi di testo."
)
_VOICE_FREE_CHAT_ONLY_REJECT = (
    "🎙️ La modalità vocale è disponibile solo in chat libera.\n"
    "In questo flusso usa messaggi di testo."
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


def _free_chat_block_reason(context: "ContextTypes.DEFAULT_TYPE") -> str:
    if context.user_data.get("diagnosis_active"):
        return "diagnosis_active"
    if context.user_data.get("diag_qa_active"):
        return "diag_qa_active"
    if context.user_data.get("chat_mode_active"):
        return "chat_mode_active"
    if context.user_data.get("upload_active"):
        return "upload_active"
    for key in _FREE_CHAT_TRANSIENT_MARKERS:
        if key in context.user_data:
            return key
    return ""


def _free_chat_block_message(block_reason: str) -> str:
    if block_reason == "chat_mode_active":
        return "💬 La chat con DELTAPLANO è già attiva. Scrivi il tuo messaggio in chat oppure usa /chiudi per uscire."
    if block_reason == "upload_active":
        return "📤 È in corso un upload guidato. Invia la foto richiesta oppure usa /annulla per uscire dal flusso."
    return "⏳ È in corso un flusso guidato di DELTA Plant. Completa i passaggi richiesti oppure usa /annulla per tornare al menu."


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


def _spoken_voice_text(text: str) -> str:
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
        return "Non ho contenuti da leggere in questo momento."
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
        "🎙️ Modalità voce disponibile in chat libera. Di default la voce usa italiano (Cris). In automatico vale il mirroring testo→testo e vocale→vocale. Usa /voice on, /voice off o /voice auto per cambiare comportamento. Per forzare la lingua della voce usa /voice_lang it, /voice_lang en o /voice_lang auto.",
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
    if context is None:
        return VOICE_LANGUAGE_DEFAULT
    raw = str(context.user_data.get("voice_language_override", VOICE_LANGUAGE_DEFAULT)).strip().lower()
    return raw if raw in _VOICE_LANGUAGE_ALLOWED else VOICE_LANGUAGE_DEFAULT


def _select_piper_voice_profile(
    text: str,
    context: Optional["ContextTypes.DEFAULT_TYPE"] = None,
) -> str:
    override = _voice_language_mode(context)
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
    if not EDGE_TTS_AVAILABLE:
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
    spoken_text = _spoken_voice_text(text)
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


async def _generate_free_chat_response(
    update: Update,
    context: "ContextTypes.DEFAULT_TYPE",
    user_text: str,
) -> str:
    user_id = str(update.effective_user.id) if update.effective_user else "0"

    try:
        await update.effective_chat.send_action("typing")
    except Exception:
        pass

    engine = _get_chat_engine(context)
    response_language = _voice_language_mode(context)
    chat_seed_context = str(context.user_data.pop("chat_seed_context", "") or "").strip()

    def _ask() -> str:
        prompt = user_text
        if chat_seed_context:
            prompt = (
                "Contesto recente DELTA Plant da usare solo se utile per la prossima risposta. "
                "Non inventare dati oltre questo contesto.\n\n"
                f"{chat_seed_context}\n\n"
                f"Domanda utente: {user_text}"
            )
        return engine.chat(user_id, prompt, response_language=response_language)

    try:
        response = await asyncio.to_thread(_ask)
    except Exception as exc:
        logger.error("Errore chat LLM: %s", exc, exc_info=True)
        response = "Mi dispiace, si è verificato un errore. Riprova tra qualche secondo."

    logger.info("free_chat_response[%s]: %s", user_id, response[:120])
    return response


async def _respond_free_chat_output(
    update: Update,
    context: "ContextTypes.DEFAULT_TYPE",
    response_text: str,
    *,
    input_mode: str,
) -> None:
    reply_markup = _chat_exit_keyboard() if context.user_data.get("chat_mode_active") else None

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
            return
        except Exception as exc:
            logger.warning("Fallback a testo per risposta vocale: %s", exc, exc_info=True)
            await _send(update, "🎙️ Risposta vocale non disponibile in questo momento. Ti rispondo in testo.")

    await _send_chat_paginated(
        update,
        context,
        response_text,
        reply_markup=reply_markup,
    )


async def _handle_free_chat_turn(
    update: Update,
    context: "ContextTypes.DEFAULT_TYPE",
    user_text: str,
    *,
    input_mode: str,
) -> str:
    response = await _generate_free_chat_response(update, context, user_text)
    await _respond_free_chat_output(update, context, response, input_mode=input_mode)
    return response


async def voice_mode_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _guard(update):
        return

    requested = context.args[0].strip().lower() if getattr(context, "args", None) else ""
    if not requested:
        current = _voice_reply_mode(context)
        await _send(
            update,
            "Modalità voce attuale: "
            f"{current.upper()}\n"
            "Usa /voice on, /voice off o /voice auto.\n"
            "Per la lingua usa /voice_lang it, /voice_lang en o /voice_lang auto.",
        )
        return

    if requested not in _VOICE_MODE_ALLOWED:
        await _send(update, "Uso corretto: /voice on | /voice off | /voice auto")
        return

    if requested == VOICE_MODE_AUTO:
        context.user_data.pop("voice_mode_override", None)
        await _send(update, "♻️ Modalità voce automatica attiva: testo→testo, vocale→vocale in chat libera.")
        return

    context.user_data["voice_mode_override"] = requested
    if requested == VOICE_MODE_ON:
        await _send(update, "🎙️ Modalità voce forzata attiva in chat libera: DELTAPLANO proverà a rispondere con un vocale anche ai messaggi testuali.")
        return

    await _send(update, "🔇 Modalità voce disattivata: i vocali saranno trascritti ma la risposta tornerà in testo.")


async def _set_voice_language(update: Update, context: ContextTypes.DEFAULT_TYPE, requested: str) -> None:
    if requested == VOICE_LANGUAGE_AUTO:
        context.user_data.pop("voice_language_override", None)
        await _send(update, "♻️ Lingua voce automatica attiva: DELTAPLANO sceglierà il pack italiano o inglese in base alla risposta.")
        return

    context.user_data["voice_language_override"] = requested
    label = "italiano" if requested == VOICE_LANGUAGE_IT else "inglese"
    await _send(update, f"🗣️ Lingua voce forzata su {label}. In chat libera adeguerò anche le risposte testuali a questa lingua, oltre a usare sempre il pack Piper corrispondente, finché non imposti /voice_lang auto.")


async def voice_language_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _guard(update):
        return

    requested = context.args[0].strip().lower() if getattr(context, "args", None) else ""
    if not requested:
        current = _voice_language_mode(context)
        await _send(
            update,
            "Lingua voce attuale: "
            f"{current.upper()}\n"
            "Usa /voice_lang it, /voice_lang en o /voice_lang auto.",
        )
        return

    if requested not in _VOICE_LANGUAGE_ALLOWED:
        await _send(update, "Uso corretto: /voice_lang it | /voice_lang en | /voice_lang auto")
        return

    await _set_voice_language(update, context, requested)


async def handle_voice_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _guard(update):
        raise ApplicationHandlerStop
    if not update.message or not update.message.voice:
        raise ApplicationHandlerStop

    if is_guided_diagnosis_mode(context):
        await _send(update, _VOICE_GUIDED_DIAGNOSIS_REJECT)
        raise ApplicationHandlerStop

    if not _is_voice_free_chat_context(context):
        await _send(update, _VOICE_FREE_CHAT_ONLY_REJECT)
        raise ApplicationHandlerStop

    await _maybe_send_voice_welcome(update, context)

    try:
        voice_bytes = await _download_voice_message_bytes(update)
        transcript = await transcribe_audio(context, voice_bytes)
    except Exception as exc:
        logger.warning("Trascrizione vocale fallita: %s", exc, exc_info=True)
        await _send(update, "Non riesco a trascrivere il messaggio vocale in questo momento. Puoi riprovare o scrivermi in testo?")
        raise ApplicationHandlerStop

    if not transcript.strip():
        await _send(update, "Non sono riuscito a capire il messaggio vocale. Puoi ripetere?")
        raise ApplicationHandlerStop

    await _handle_free_chat_turn(update, context, transcript, input_mode="voice")
    raise ApplicationHandlerStop

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
    if not await _guard(update):
        logger.debug("free_chat_handler: accesso negato")
        return
    if not update.message or not update.message.text:
        logger.debug("free_chat_handler: messaggio vuoto o non testuale")
        return
    block_reason = _free_chat_block_reason(context)
    if block_reason:
        logger.info("free_chat_handler: flusso strutturato attivo (%s), invio feedback", block_reason)
        await _send(update, _free_chat_block_message(block_reason))
        return
    user_text = update.message.text.strip()
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
    base = TELEGRAM_CONFIG.get("web_app_base_url", "https://deltaplant.ai").rstrip("/")
    return f"{base}/telegram/nasa-sar-locator.html"


def _menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🔵 💬 Chiedi a DELTA Plant", callback_data=CMD_CHAT),
        ],
        [
            InlineKeyboardButton("🆕 Effettua una diagnosi della Pianta", callback_data=CMD_DIAGNOSE),
        ],
        [
            InlineKeyboardButton("🌡 Sensori", callback_data=CMD_SENSORS),
            InlineKeyboardButton("📤 Report Excel", callback_data=CMD_EXPORT),
        ],
        [
            InlineKeyboardButton("🧪 Preflight", callback_data=CMD_PREFLIGHT),
            InlineKeyboardButton("✅ Health", callback_data=CMD_HEALTH),
        ],
        [
            InlineKeyboardButton("🎓 Academy", callback_data=CMD_ACADEMY),
            InlineKeyboardButton("📄 Licenza", callback_data=CMD_LICENSE),
        ],
        [
            InlineKeyboardButton("🛰️ Connettiti a NASA-ISRO/SAR", callback_data=CMD_NASA_SAR),
        ],
        [
            InlineKeyboardButton("👩‍🔬 Cris (IT)", callback_data=CMD_VOICE_LANG_IT),
        ],
        [
            InlineKeyboardButton("👨‍🔬 Ryan (EN)", callback_data=CMD_VOICE_LANG_EN),
        ],
    ])


async def _send(update: Update, text: str, reply_markup: Optional[Any] = None, parse_mode: str = None):
    # parse_mode è opzionale e passato come keyword argument
    import inspect
    frame = inspect.currentframe()
    args, _, _, values = inspect.getargvalues(frame)
    parse_mode = values.get('parse_mode', None)
    chat = getattr(update, "effective_chat", None)
    if chat is None:
        raise RuntimeError("Chat Telegram non disponibile per l'invio del messaggio.")
    reply_args = {"reply_markup": reply_markup}
    if parse_mode is not None:
        reply_args["parse_mode"] = parse_mode
    await chat.send_message(text, **reply_args)


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
            "I am ready to help you with plant diagnosis, sensors, reports, and agronomic guidance. "
            "Open the menu and tell me how I can help you."
        )
    return (
        f"Ciao {display_name}, benvenuto in DELTAPLANO. "
        "Sono pronto ad aiutarti con diagnosi delle piante, sensori, report e consigli agronomici. "
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
    closing = "Posso fare qualcos'altro per te? Sono a tua disposizione 🙂"

    # Pulisci eventuale coda residua di vecchie versioni paginate
    context.user_data.pop("diag_pending_chunks", None)
    context.user_data.pop("diag_pending_parse_mode", None)
    context.user_data.pop("diag_pending_closing", None)

    if len(text) > MAX_DIAG_CHARS:
        # Tronca all'ultimo a-capo entro il limite
        cutoff = text.rfind("\n", 0, MAX_DIAG_CHARS)
        if cutoff == -1:
            cutoff = MAX_DIAG_CHARS
        text = text[:cutoff].rstrip() + "\n\n_(sintesi — testo completo disponibile su richiesta)_"

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


def _build_nasa_sar_map_photo_payload(latitude: float, longitude: float) -> Optional[BytesIO]:
    map_url = _build_nasa_sar_map_url(latitude, longitude)

    try:
        response = requests.get(map_url, timeout=10)
        response.raise_for_status()

        if not PIL_AVAILABLE:
            payload = BytesIO(response.content)
            payload.seek(0)
            payload.name = "nasa_sar_dashboard.jpg"
            return payload

        image = Image.open(BytesIO(response.content)).convert("RGBA")
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

        merged = Image.alpha_composite(image, overlay).convert("RGB")
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


def _compute_fungal_risk_value(
    temperature: float,
    humidity: float,
    precipitation: float,
    previous_risk: float,
) -> float:
    humidity_factor = 1.0 if humidity >= 80.0 else humidity / 80.0
    temp_centered = max(0.0, 1.0 - abs(temperature - 20.0) / 10.0)
    rain_factor = min(max(precipitation / 8.0, 0.0), 1.0)
    sustained = previous_risk * 0.45
    return max(min((0.5 * humidity_factor) + (0.35 * temp_centered) + (0.15 * rain_factor) + sustained, 1.0), 0.0)


def _build_weekly_fungal_risk_window(daily_weather: List[Dict[str, Any]]) -> Dict[str, Any]:
    previous_risk = 0.0
    risk_series: List[Dict[str, Any]] = []
    for item in daily_weather[:7]:
        risk_value = _compute_fungal_risk_value(
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


def _build_nasa_sar_scientific_interpretation(
    result: Dict[str, Any],
    weather_reference: Optional[Dict[str, Any]] = None,
) -> str:
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
    sar_source = str(soil_summary.get("sar_source", "Stima climatica NASA POWER"))
    sar_product_name = soil_summary.get("sar_product_name")
    sar_acquired_at = soil_summary.get("sar_acquired_at")

    fungal_mean = float(risk_window.get("mean_value", 0.0) or 0.0)
    fungal_peak = float(risk_window.get("peak_value", 0.0) or 0.0)
    high_fungal_days = int(risk_window.get("high_risk_days", 0) or 0)
    fungal_level = _classify_fungal_risk(fungal_mean, fungal_peak, high_fungal_days).upper()

    mean_humidity = _safe_average([float(item.get("RH2M", 0.0) or 0.0) for item in weather_daily])
    weather_days = len(weather_daily)
    total_precip = sum(float(item.get("PRECTOTCORR", 0.0) or 0.0) for item in weather_daily)
    mean_precip_daily = (total_precip / weather_days) if weather_days else 0.0
    mean_temp = _safe_average([float(item.get("T2M", 0.0) or 0.0) for item in weather_daily])

    locality_label = html.escape(str(geo_summary.get("locality_label") or "Localita' non determinata"), quote=False)
    weather_source = html.escape(str((weather_reference or {}).get("source", "Servizio meteo non disponibile")), quote=False)
    warning = str((weather_reference or {}).get("warning", "") or "").strip()

    if fungal_level == "ALTO":
        simple_message = "La combinazione tra umidita', temperatura e pioggia indica una favorevolezza fungina elevata"
    elif fungal_level == "MEDIO":
        simple_message = "La zona mostra una favorevolezza fungina intermedia e richiede attenzione"
    else:
        simple_message = "Il quadro climatico resta poco favorevole allo sviluppo fungino"

    lines = [
        "Formula del rischio fungino: 50% umidita' relativa, 35% temperatura vicina a 20 C, 15% pioggia giornaliera e 45% di persistenza dal giorno precedente.",
        f"Valore medio settimanale: {fungal_mean:.2f}",
        f"Giudizio di rischio: {fungal_level}",
        f"Lettura semplice: {simple_message}.",
        f"Localita': {locality_label}.",
        f"Umidita' del suolo SAR: {sar_soil:.1f}%.",
        f"Meteo ufficiale Aeronautica: temperatura media {mean_temp:.1f} C, umidita' relativa media {mean_humidity:.1f}%, pioggia cumulata {total_precip:.1f} mm su {weather_days} giorni (media {mean_precip_daily:.1f} mm/giorno).",
        "Fonti dati:",
        f"- Umidita' del suolo: {html.escape(sar_source, quote=False)}" + (f" | scena {html.escape(str(sar_product_name), quote=False)}" if sar_product_name else ""),
        f"- Meteo: {weather_source}",
        "- Mappa: Esri World Imagery",
    ]
    if sar_acquired_at:
        lines.append(f"- Acquisizione SAR: {html.escape(str(sar_acquired_at), quote=False)}")
    if warning:
        lines.append(f"Nota tecnica: feed ufficiale MeteoAM non disponibile in tempo reale, usato fallback {html.escape(warning, quote=False)}.")
    lines.append("Questa non e' una diagnosi di malattia: descrive solo la favorevolezza climatica e il contesto di umidita' del suolo della zona GPS.")
    return "\n".join(lines)


def _nasa_sar_reply_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton("🛰️ Apri NASA-ISRO/SAR GPS", web_app=WebAppInfo(url=_nasa_sar_webapp_url()))],
            [KeyboardButton("📍 Invia GPS manualmente", request_location=True)],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
        input_field_placeholder="Apri il locator automatico oppure condividi manualmente la posizione.",
    )


def _format_nasa_sar_dashboard(result: Dict[str, Any]) -> str:
    geo_summary = result.get("geo_summary", {}) or {}
    dashboard = result.get("dashboard", {}) or {}
    summary = dashboard.get("summary", {}) or {}
    centroid = geo_summary.get("centroid", {}) or {}
    radius_m = geo_summary.get("radius_m", 50)
    locality_label = html.escape(str(geo_summary.get("locality_label") or "Localita' non determinata"), quote=False)
    sar_source = html.escape(str(summary.get("sar_source", "Stima climatica NASA POWER")), quote=False)
    sar_product_name = summary.get("sar_product_name")
    sar_acquired_at = summary.get("sar_acquired_at")
    weather_start = summary.get("weather_window_start")
    weather_end = summary.get("weather_window_end")

    lines = [
        "<b>🛰️ NASA-ISRO/SAR Dashboard</b>",
        "<b>──────────────</b>",
        "<i>Sintesi semplice SAR/NISAR + meteo ufficiale</i>",
        f"<b>Localita':</b> {locality_label}",
        f"<b>Area:</b> raggio {radius_m:.0f} m",
        f"<b>Centro GPS:</b> {float(centroid.get('lat', 0.0)):.6f}, {float(centroid.get('lon', 0.0)):.6f}",
        f"<b>Umidita' suolo SAR:</b> {float(summary.get('sar_soil_moisture_percent', 0.0)):.1f}%",
        f"<b>Fonte suolo:</b> {sar_source}",
    ]
    if sar_product_name:
        lines.append(f"<b>Scena SAR:</b> {html.escape(str(sar_product_name), quote=False)}")
    if sar_acquired_at:
        lines.append(f"<b>Acquisizione SAR:</b> {html.escape(str(sar_acquired_at), quote=False)}")
    if weather_start and weather_end:
        lines.append(f"<b>Finestra meteo:</b> {html.escape(str(weather_start), quote=False)} → {html.escape(str(weather_end), quote=False)}")
    return "\n".join(lines)


async def _interpret_nasa_sar_dashboard(
    context: "ContextTypes.DEFAULT_TYPE",
    result: Dict[str, Any],
) -> str:
    dashboard = result.get("dashboard", {}) or {}
    if not dashboard.get("summary"):
        return "Non ho trovato abbastanza dati SAR e meteo per produrre una sintesi agronomica." 
    weather_reference = await asyncio.to_thread(_fetch_external_weather_reference, result)
    # Keep numeric weather values deterministic: avoid LLM rewriting for this critical section.
    return _build_nasa_sar_scientific_interpretation(result, weather_reference)


def _build_nasa_sar_followup_context(result: Dict[str, Any], interpretation: str) -> str:
    geo_summary = result.get("geo_summary", {}) or {}
    dashboard = result.get("dashboard", {}) or {}
    summary = dashboard.get("summary", {}) or {}
    locality = str(geo_summary.get("locality_label") or "Localita' non determinata")
    return "\n".join(
        [
            "Contesto della piu recente sintesi SAR/NISAR DELTA Plant:",
            f"Localita': {locality}",
            f"Centro GPS: {float((geo_summary.get('centroid', {}) or {}).get('lat', 0.0)):.6f}, {float((geo_summary.get('centroid', {}) or {}).get('lon', 0.0)):.6f}",
            f"Umidita' suolo SAR: {float(summary.get('sar_soil_moisture_percent', 0.0) or 0.0):.1f}%",
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
) -> None:
    chat = getattr(update, "effective_chat", None)
    if chat is None:
        return
    try:
        photo_payload = await asyncio.to_thread(_build_nasa_sar_map_photo_payload, latitude, longitude)
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

    try:
        result = await orchestrator.analyze_nasa_only(
            geo_data=geo_payload,
            date_range=date_range,
        )
    except Exception as exc:
        logger.warning("Analisi NASA-ISRO/SAR fallita: %s", exc, exc_info=True)
        await _send(
            update,
            "Analisi NASA-ISRO/SAR non disponibile in questo momento.",
            reply_markup=reply_markup or _menu_keyboard(),
        )
        return

    locality_label = await asyncio.to_thread(_reverse_geocode_locality, latitude, longitude)
    if locality_label:
        result.setdefault("geo_summary", {})["locality_label"] = locality_label

    dashboard_text = _format_nasa_sar_dashboard(result)
    interpretation = await _interpret_nasa_sar_dashboard(context, result)
    await _send_nasa_sar_map_snapshot(update, latitude, longitude)
    await _send(
        update,
        dashboard_text,
        reply_markup=reply_markup,
        parse_mode="HTML",
    )
    await _send(
        update,
        "<b>🧠 Sintesi semplice SAR/NISAR + Servizio Meteorologico dell'Aeronautica Militare</b>\n" + interpretation,
        reply_markup=_menu_keyboard(),
        parse_mode="HTML",
    )
    context.user_data["chat_seed_context"] = _build_nasa_sar_followup_context(result, interpretation)
    await _send(
        update,
        "💬 Ora puoi chiedermi approfondimenti sulla diagnosi o altro. Usero' la sintesi SAR appena generata come contesto iniziale della prossima risposta.",
        reply_markup=_menu_keyboard(),
    )


async def nasa_sar_connect(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data["awaiting_nasa_sar_location"] = True
    await _send(
        update,
        "🛰️ <b>NASA-ISRO/SAR pronto</b>\n\n"
        "Tocca <b>Apri NASA-ISRO/SAR GPS</b> per avviare la Mini App Telegram e rilevare automaticamente la posizione del telefono. "
        "Se il client non supporta il passaggio automatico, usa <b>Invia GPS manualmente</b>. "
        "Analizzero' un'area circolare di 50 metri e ti mostrero' la dashboard SAR con mappa, localita' e sintesi semplice basata su umidita' del suolo satellitare e meteo ufficiale Aeronautica.",
        reply_markup=_nasa_sar_reply_keyboard(),
        parse_mode="HTML",
    )


async def handle_nasa_sar_location(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _guard(update):
        return
    location = getattr(getattr(update, "message", None), "location", None)
    if location is None or not context.user_data.get("awaiting_nasa_sar_location"):
        return

    context.user_data.pop("awaiting_nasa_sar_location", None)
    await _run_nasa_sar_analysis(
        update,
        context,
        location.latitude,
        location.longitude,
        reply_markup=ReplyKeyboardRemove(),
    )


async def handle_nasa_sar_web_app_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _guard(update):
        return

    message = getattr(update, "effective_message", None)
    web_app_data = getattr(message, "web_app_data", None)
    if web_app_data is None:
        return

    try:
        payload = json.loads(web_app_data.data)
    except Exception:
        await _send(update, "Dati GPS automatici non validi ricevuti dalla Web App.", reply_markup=_menu_keyboard())
        return

    if payload.get("type") != "nasa_sar_location":
        return

    if payload.get("status") == "error":
        await _send(
            update,
            "La posizione automatica non è disponibile. Consenti l'accesso GPS sul telefono oppure usa /nasa_sar per l'invio manuale.",
            reply_markup=_menu_keyboard(),
        )
        return

    try:
        latitude = float(payload["latitude"])
        longitude = float(payload["longitude"])
    except (KeyError, TypeError, ValueError):
        await _send(update, "Coordinate GPS automatiche non valide.", reply_markup=_menu_keyboard())
        return

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

    # Snapshot sensori
    if sensor:
        msg.append("")
        msg.append("<b>Dati sensori:</b>")
        fields = [
            ("temperature_c",  "Temperatura",    "°C"),
            ("humidity_pct",   "Umidità",         "%"),
            ("pressure_hpa",   "Pressione",       "hPa"),
            ("light_lux",      "Luminosità",      "lux"),
            ("co2_ppm",        "CO₂",             "ppm"),
            ("ph",             "pH",              ""),
            ("ec_ms_cm",       "EC",              "mS/cm"),
        ]
        for key, label, unit in fields:
            val = sensor.get(key)
            val_str = fmt(val, unit)
            msg.append(f"  {label:15s}: {val_str}")
        source = sensor.get("source", "?")
        ts = sensor.get("timestamp", "?")
        msg.append(f"  Fonte: {source} | Timestamp: {ts}")
        if anomalies:
            msg.append(f"  ⚠️ Anomalie: {len(anomalies)}")
            for a in anomalies:
                msg.append(f"    • {a}")

    msg.append("\n<code>──────────────</code>")
    return "\n".join(msg)


# ──────────────────────────────────────────────────────────────────────────────
# CHAT INTELLIGENTE — "Chiedi a DELTA" (HuggingFace LLM via InferenceAPI)
# ──────────────────────────────────────────────────────────────────────────────

def _chat_exit_keyboard() -> InlineKeyboardMarkup:
    """Tastiera con solo il pulsante di uscita dalla chat."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔴 Termina chat", callback_data=CHAT_EXIT)],
        [InlineKeyboardButton("🗑 Reset conversazione", callback_data="CHAT_RESET")],
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


async def chat_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Avvia la sessione di chat intelligente."""
    if not await _guard(update):
        return ConversationHandler.END

    # v3.1: Prevent chat during active diagnosis (manual sensor input phase)
    if context.user_data.get("diagnosis_active"):
        await _send(update,
            "⏳ Una diagnosi è in corso. Completa prima con /annulla oppure attendi il termine.\n\n"
            "La chat è disabilitata durante l'acquisizione dati sensori per evitare interferenze.")
        return ConversationHandler.END

    context.user_data["chat_mode_active"] = True

    engine = _get_chat_engine(context)
    status = engine.get_status()
    hf_ok = status.get("hf_token_valid", False)
    model_name = status.get("hf_active_model", "N/D")

    if hf_ok:
        intro = (
            "🔵 *Chat intelligente DELTA attiva*\n\n"
            f"Modello: `{model_name}`\n\n"
            "Puoi chiedermi qualsiasi cosa su malattie delle piante, "
            "trattamenti, agronomia o interpretazione delle diagnosi.\n\n"
            "_Scrivi il tuo messaggio. Usa_ /chiudi _per terminare la chat._"
        )
    else:
        intro = (
            "🟡 *Chat DELTA non disponibile*\n\n"
            "Il backend HuggingFace non è disponibile.\n"
            "Verifica `HF_API_TOKEN` e `HF_MODEL_NAME` in `.env`.\n\n"
            "_Scrivi il tuo messaggio. Usa_ /chiudi _per terminare._"
        )

    await _send(update, intro, reply_markup=_chat_exit_keyboard(), parse_mode="Markdown")
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
        await _answer_callback_query_safe(query, "Conversazione resettata ✓")
    user_id = str(update.effective_user.id if update.effective_user else "0")
    engine = _get_chat_engine(context)
    engine.reset(user_id)
    await _send(update, "🗑 Memoria conversazione azzerata. Scrivi il tuo prossimo messaggio.", reply_markup=_chat_exit_keyboard())
    return STATE_CHAT_WAITING


async def chat_exit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Termina la sessione di chat e torna al menu principale."""
    if not await _guard(update):
        return ConversationHandler.END
    _clear_chat_state(context)
    query = update.callback_query
    if query:
        await _answer_callback_query_safe(query, "Chat terminata")
    await _send(update, "Chat terminata. Usa /menu per tornare al menu principale.", reply_markup=_menu_keyboard())
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
    intro = (
        "Benvenuto in @DELTAPLANO_bot.\n"
        "Qui puoi interagire con DELTA Plant da Telegram per avviare diagnosi, "
        "consultare report e leggere i dati sensori.\n"
        "Usa /menu per vedere le azioni disponibili."
    )
    await _send(update, intro, reply_markup=_menu_keyboard())
    await _send_personalized_welcome_voice(update, context)
    if was_chat_active:
        return ConversationHandler.END


async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _guard(update):
        return ConversationHandler.END
    effective_user = getattr(update, "effective_user", None)
    logger.info("Telegram /menu ricevuto da user_id=%s", effective_user.id if effective_user else "0")
    was_chat_active = bool(context.user_data.get("chat_mode_active"))
    _clear_chat_state(context)
    await _send(update, "Menu principale:", reply_markup=_menu_keyboard())
    if was_chat_active:
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
            await _send(update, "Errore sistema: API non raggiungibile.")
            return
        if resp.status_code != 200:
            logger.warning("API /diagnoses errore %s: %s", resp.status_code, resp.text[:200])
            await _send(update, "Errore sistema.")
            return
        try:
            records = resp.json()
        except ValueError:
            await _send(update, "Risposta API non valida.")
            return
    if not records:
        await _send(update, "Nessuna diagnosi disponibile.")
        return
    lines = ["Ultime diagnosi:"]
    for rec in records:
        rec_id = rec.get("id", "N/D")
        ts = rec.get("timestamp", "N/D")
        cls = rec.get("ai_class", "N/D")
        risk = rec.get("overall_risk", "N/D")
        lines.append(f"• #{rec_id} | {ts} | {cls} | rischio {risk}")
    await _send(update, "\n".join(lines))


async def detail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _guard(update):
        return
    if not context.args:
        await _send(update, "Uso: /dettaglio <id>")
        return
    try:
        record_id = int(context.args[0])
    except ValueError:
        await _send(update, "ID non valido.")
        return
    agent = _get_agent(context)
    if agent:
        record = agent.database.get_by_id(record_id)
        if record is None:
            await _send(update, "Record non trovato.")
            return
    else:
        resp = await _api_request("GET", f"/diagnoses/{record_id}")
        if resp is None:
            await _send(update, "Errore sistema: API non raggiungibile.")
            return
        if resp.status_code != 200:
            await _send(update, "Record non trovato.")
            return
        try:
            record = resp.json()
        except ValueError:
            await _send(update, "Risposta API non valida.")
            return
    summary = record.get("summary", "N/D")
    cls = record.get("ai_class", "N/D")
    risk = record.get("overall_risk", "N/D")
    ts = record.get("timestamp", "N/D")
    await _send(update, f"Dettaglio #{record_id}\nData: {ts}\nClasse: {cls}\nRischio: {risk}\n{summary}")


async def sensors(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _guard(update):
        return
    agent = _get_agent(context)
    if agent:
        data = agent.get_latest_sensor_data()
    else:
        resp = await _api_request("GET", "/sensors")
        if resp is None:
            await _send(update, "Errore sistema: API non raggiungibile.")
            return
        if resp.status_code != 200:
            await _send(update, "Errore sistema.")
            return
        try:
            data = resp.json()
        except ValueError:
            await _send(update, "Risposta API non valida.")
            return
    lines = ["Dati sensori:"]
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
            await _send(update, "Errore sistema: API non raggiungibile.")
            return
        if resp.status_code != 200:
            await _send(update, "Errore sistema.")
            return
        try:
            data = resp.json()
        except ValueError:
            await _send(update, "Risposta API non valida.")
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
    """Restituisce una stringa leggibile dei dati sensore da iniettare nei prompt."""
    if not sensor_data:
        return ""
    lines = []
    for key, label in SENSOR_FIELDS:
        val = sensor_data.get(key)
        if val is not None:
            lines.append(f"  {label}: {val}")
    if not lines:
        return ""
    return "\nDati ambientali disponibili:\n" + "\n".join(lines)


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

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📷 Invia foto", callback_data=DIAG_IMAGE_UPLOAD)],
        [InlineKeyboardButton(" Camera locale", callback_data=DIAG_IMAGE_CAMERA)],
    ])
    await _send(update, "Diagnosi: scegli la fonte immagine.", reply_markup=keyboard)
    return STATE_DIAG_IMAGE_SOURCE


async def choose_diag_image_source(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _guard(update):
        return ConversationHandler.END
    query = update.callback_query
    if not query:
        return ConversationHandler.END
    await _answer_callback_query_safe(query)
    if query.data == DIAG_IMAGE_UPLOAD:
        await _send(update, "Invia una foto (o un file immagine) per la diagnosi.")
        return STATE_DIAG_WAIT_PHOTO
    if query.data == DIAG_IMAGE_LAST:
        latest = _get_latest_input_image()
        if not latest:
            _clear_diagnosis_state(context)
            await _send(update, "Nessuna immagine in input_images. Usa 'Invia foto'.")
            return ConversationHandler.END
        context.user_data["diag_image_path"] = str(latest)
        return await _ask_user_description(update, context)
    if query.data == DIAG_IMAGE_CAMERA:
        agent = _get_agent(context)
        if not agent or agent.camera._backend is None:
            _clear_diagnosis_state(context)
            await _send(update, "Camera locale non disponibile. Usa 'Invia foto'.")
            return ConversationHandler.END
        context.user_data["diag_image_path"] = ""
        return await _ask_user_description(update, context)
    _clear_diagnosis_state(context)
    await _send(update, "Scelta non valida.")
    return ConversationHandler.END


async def diag_expect_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _send(update, "Per favore invia una foto o un file immagine.")
    return STATE_DIAG_WAIT_PHOTO


async def receive_diag_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _guard(update):
        return ConversationHandler.END
    saved = await _download_telegram_image(update)
    if not saved:
        await _send(update, "Immagine non valida.")
        return STATE_DIAG_WAIT_PHOTO
    context.user_data["diag_image_path"] = str(saved)
    return await _ask_user_description(update, context)


async def _ask_user_description(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Chiede all'utente il tipo di pianta e l'anomalia riscontrata."""
    await _send(
        update,
        "Di che pianta si tratta? Descrivimi l'anomalia che hai riscontrato, "
        "sarò ben lieto di aiutarti 😊\n\n"
        "_Esempio: 'Pomodoro con macchie gialle sulle foglie e bordi secchi'_",
        parse_mode="Markdown",
    )
    return STATE_DIAG_USER_DESCRIPTION


async def receive_user_description(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Riceve la descrizione testuale utente e procede alla scelta sensori."""
    if not await _guard(update):
        return ConversationHandler.END
    if not update.message or not update.message.text:
        await _send(update, "Per favore descrivi la pianta e l'anomalia osservata.")
        return STATE_DIAG_USER_DESCRIPTION
    description = update.message.text.strip()
    if len(description) < 3:
        await _send(update, "Descrizione troppo breve. Aggiungi dettagli sulla pianta e sull'anomalia.")
        return STATE_DIAG_USER_DESCRIPTION
    context.user_data["diag_user_description"] = description
    await _send(update, "Grazie! Ora acquisisco i dati ambientali... 🌱")
    return await _ask_sensor_mode(update, context)


async def _ask_sensor_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("Usa sensori attuali", callback_data=DIAG_SENSOR_AUTO)],
        [InlineKeyboardButton("Inserimento manuale", callback_data=DIAG_SENSOR_MANUAL)],
    ])
    await _send(update, "Come vuoi acquisire i dati sensore?", reply_markup=keyboard)
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
        await _send(update, f"Inserisci {SENSOR_FIELDS[0][1]} (digita x per saltare):")
        return STATE_DIAG_TEMP
    await _send(update, "Scelta non valida.")
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
            await _send(update, f"Valore non valido. Inserisci {label} (oppure digita x per saltare).")
            return STATE_DIAG_TEMP
        context.user_data["sensor_data"][key] = parsed
    idx += 1
    context.user_data["sensor_index"] = idx
    if idx < len(SENSOR_FIELDS):
        await _send(update, f"Inserisci {SENSOR_FIELDS[idx][1]} (digita x per saltare):")
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


def _sanitize_diagnosis_opinion(opinion: str) -> str:
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

    return text


def _strip_plantvillage_class_mentions(text: str) -> str:
    """Rimuove citazioni esplicite di classi PlantVillage dal testo finale."""
    cleaned = text or ""
    for cls in _PLANTVILLAGE_CLASSES:
        pattern = re.escape(cls).replace("_", r"[ _]")
        cleaned = re.sub(pattern, "classe omessa", cleaned, flags=re.IGNORECASE)
    return cleaned


def _build_diagnosis_prompt(record: Dict[str, Any], user_description: str = "") -> str:
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
    class_note = ""
    if corrected_class and corrected_class != ai_class:
        class_note = (
            f"\nNOTA: la classe PlantVillage originale ({ai_class}) è stata corretta "
            f"in '{corrected_class}' sulla base della descrizione dell'utente.\n"
        )

    description_block = ""
    description_constraints = ""
    if user_description:
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

    return (
        "Trasforma il report seguente in un UNICO messaggio finale per l'utente, "
        "in italiano, con stile professionale da agronomo esperto, dettagliato ma chiaro.\n\n"
        f"REPORT RAW RISULTATO DIAGNOSI DELTA:\n{raw_report}\n"
        f"{description_block}"
        f"{class_note}\n"
        "Vincoli obbligatori:\n"
        "- Non usare frasi metalinguistiche (es: 'Sembra che tu stia chiedendo').\n"
        "- Non ripetere il titolo del report.\n"
        "- Cita esplicitamente la classe PlantVillage confermata e motiva la coerenza con la descrizione dell'operatore.\n"
        "- Includi esplicitamente l'analisi del rischio con Oracolo Quantistico di Grover: "
        "spiega in modo semplice e operativo cosa rappresenta (strumento che amplifica i segnali "
        "di rischio più significativi tra i dati della pianta, con QRS da 0=nessun rischio a 1=rischio massimo), "
        "poi riporta QRS, livello, evento dominante e amplificazione.\n"
        f"{description_constraints}"
        "- Analizza e commenta sempre i dati ambientali dei sensori presenti nel report: correla temperatura, umidità, pH, EC, CO₂ e luminosità allo stato patologico rilevato.\n"
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
            "✅ <b>L'operatore descrive la pianta in buona salute.</b>\n"
            "Non avvio il flusso diagnostico. Elaboro una valutazione di benessere... 🌿",
            parse_mode="HTML",
        )
        await _send_conversational_diagnosis(update, context)
        return ConversationHandler.END

    if mode == "class_mismatch":
        intro = (
            "⚠️ <b>Nessuna corrispondenza piena tra classe AI e quadro descritto.</b>\n"
            "Procedo con analisi solo AI tramite interazione Operatore/AI.\n"
            f"Ti farò al massimo {MAX_FOLLOWUP_QUESTIONS} domande di approfondimento. 🌿"
        )
    else:
        intro = (
            "⚠️ <b>Pianta non riconosciuta nel database.</b>\n"
            "Procederò comunque con una diagnosi basata sulla tua descrizione.\n"
            f"Ti farò al massimo {MAX_FOLLOWUP_QUESTIONS} domande di approfondimento. 🌿"
        )

    await _send(update, intro, parse_mode="HTML")

    _sensor_ctx = _format_sensor_text(context.user_data.get("sensor_data", {}))
    question, should_stop = await _generate_followup_question(
        engine, user_id, user_description, [], sensor_context=_sensor_ctx
    )
    if should_stop or not question:
        await _send(update, "Ho già abbastanza informazioni. Elaboro la diagnosi... 🔬")
        await _send_conversational_diagnosis(update, context)
        return ConversationHandler.END

    context.user_data["diag_followup_count"] = 1
    context.user_data["diag_followup_last_question"] = question
    context.user_data["diag_qa_active"] = True
    await _send(
        update,
        f"❓ <b>Domanda 1/{MAX_FOLLOWUP_QUESTIONS}:</b>\n{question}",
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
        await _send(update, "Non ho ricevuto una risposta. Riprova.")
        return STATE_DIAG_FOLLOWUP

    qa_pairs = context.user_data.get("diag_followup_qa", [])
    count = context.user_data.get("diag_followup_count", 1)
    last_question = context.user_data.get("diag_followup_last_question", "")

    qa_pairs.append((last_question, answer))
    context.user_data["diag_followup_qa"] = qa_pairs

    if count >= MAX_FOLLOWUP_QUESTIONS:
        context.user_data["diag_qa_active"] = False
        await _send(update, "✅ Ho raccolto tutte le informazioni necessarie. Elaboro la diagnosi... 🔬")
        await _send_conversational_diagnosis(update, context)
        return ConversationHandler.END

    # Conferma ricezione risposta e segnala che si sta elaborando la domanda successiva
    await _send(update, f"📝 <i>Risposta {count} registrata.</i>", parse_mode="HTML")
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
        await _send(update, "✅ Ho raccolto tutte le informazioni necessarie. Elaboro la diagnosi... 🔬")
        await _send_conversational_diagnosis(update, context)
        return ConversationHandler.END

    new_count = count + 1
    context.user_data["diag_followup_count"] = new_count
    context.user_data["diag_followup_last_question"] = question
    await _send(
        update,
        f"❓ <b>Domanda {new_count}/{MAX_FOLLOWUP_QUESTIONS}:</b>\n{question}",
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

    # Vincolo salute: se l'operatore ha dichiarato la pianta sana, il sistema
    # non deve formulare diagnosi di malattia ma una valutazione di benessere.
    health_constraint = (
        "\n⚠️ VINCOLO CRITICO: l'operatore ha dichiarato esplicitamente la pianta in buona salute. "
        "NON formulare diagnosi di malattie o patologie. "
        "Produci una valutazione dello stato di salute: conferma il benessere osservato, "
        "indica eventuali fattori di rischio ambientale da monitorare preventivamente "
        "e suggerisci buone pratiche colturali per mantenere la pianta in salute."
        if operator_healthy else ""
    )

    if followup_mode == "class_mismatch":
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
        return engine.chat_internal(prompt)

    try:
        opinion = await asyncio.to_thread(_ask)
    except Exception as exc:
        logger.warning("Errore diagnosi conversazionale: %s", exc)
        _clear_diagnosis_state(context)
        await _send(update, "❌ Errore durante la diagnosi conversazionale.")
        return

    opinion = _sanitize_diagnosis_opinion(opinion)
    if followup_mode == "class_mismatch":
        opinion = _strip_plantvillage_class_mentions(opinion)

    memory_request, memory_response = _build_diagnosis_memory_turn(
        user_description=user_description,
        opinion=opinion,
        qa_pairs=qa_pairs,
        followup_mode=followup_mode,
        sensor_data=sensor_data,
    )

    title = "🩺 <b>DIAGNOSI AI INTERATTIVA DELTA Plant:</b>" if followup_mode == "class_mismatch" else "🩺 <b>DIAGNOSI CONVERSAZIONALE DELTA Plant:</b>"

    try:
        await _send_diagnosis_paginated(
            update,
            context,
            f"{title}\n\n{opinion}",
            parse_mode="HTML",
        )
        engine.remember_turn(user_id, memory_request, memory_response)
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
                "Feedback CAM DELTA Plant: il cerchio e il target indicano dove il modello sta guardando.",
                "Le aree piu calde della LayerCAM corrispondono alla regione che ha pesato maggiormente nella decisione.",
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
                        caption="Foto originale acquisita per la diagnosi DELTA Plant (riferimento).",
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

    prompt = _build_diagnosis_prompt(record, user_description)

    def _ask():
        return engine.chat_internal(prompt)

    try:
        opinion = await asyncio.to_thread(_ask)
    except Exception as exc:
        logger.warning("Errore opinione AI post-diagnosi: %s", exc)
        _clear_diagnosis_state(context)
        return ConversationHandler.END

    opinion = _sanitize_diagnosis_opinion(opinion)
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
            f"🩺 <b>RISULTATO DIAGNOSI DELTA Plant:</b>\n\n{opinion}",
            parse_mode="HTML",
        )
        engine.remember_turn(user_id, memory_request, memory_response)
        context.user_data["chat_seed_context"] = (
            "Contesto della piu recente diagnosi DELTA Plant:\n\n"
            f"{opinion}"
        )
    finally:
        # Pulizia garantita anche se _send_diagnosis_paginated lancia un'eccezione.
        # Senza questo, la chat potrebbe restare bloccata o ricevere marker residui.
        _clear_diagnosis_state(context)
    return ConversationHandler.END


async def _run_diagnosis(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    sensor_data: Optional[Dict[str, Any]],
):
    # Restituisce un ConversationHandler state (END o STATE_DIAG_FOLLOWUP)
    agent = _get_agent(context)
    if not agent:
        _clear_diagnosis_state(context)
        await _send(update, "Errore sistema: agent non disponibile.")
        return ConversationHandler.END

    image_path = context.user_data.get("diag_image_path")
    image = None
    if image_path:
        image = _load_image_from_path(Path(image_path))
        if image is None:
            _clear_diagnosis_state(context)
            await _send(update, "Impossibile caricare l'immagine.")
            return ConversationHandler.END
    try:
        record = await asyncio.to_thread(agent.run_diagnosis, sensor_data=sensor_data, image=image)
    except Exception as exc:
        logger.error("Errore diagnosi Telegram: %s", exc, exc_info=True)
        _clear_diagnosis_state(context)
        await _send(update, "❌ Errore durante la diagnosi. La chat è nuovamente disponibile.")
        return ConversationHandler.END

    # Propaga sensor_snapshot a user_data per renderlo disponibile nei flussi conversazionali
    if not context.user_data.get("sensor_data"):
        snap = (record.get("diagnosis") or {}).get("sensor_snapshot") or {}
        populated = {k: v for k, v in snap.items() if v is not None and k != "source"}
        if populated:
            context.user_data["sensor_data"] = populated

    # Pianta non riconosciuta → modalità follow-up conversazionale
    if record.get("ai_result", {}).get("fallback", False):
        return await _start_followup_questioning(update, context, record, mode="fallback")

    # Match pieno classe -> diagnosi completa; mismatch -> follow-up interattivo
    return await _send_ai_diagnosis_opinion(update, context, record)


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
    await _send(update, "Invia una foto (o file immagine) da salvare in input_images.")
    return STATE_UPLOAD_WAIT_PHOTO


async def upload_expect_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _send(update, "Per favore invia una foto o un file immagine.")
    return STATE_UPLOAD_WAIT_PHOTO


async def receive_upload_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _guard(update):
        return ConversationHandler.END
    saved = await _download_telegram_image(update)
    if not saved:
        await _send(update, "Immagine non valida.")
        return STATE_UPLOAD_WAIT_PHOTO
    context.user_data.pop("upload_active", None)
    await _send(update, f"Immagine salvata in input_images: {saved.name}")
    return ConversationHandler.END


async def handle_plant_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _send(update, "Flusso etichettatura dismesso nella logica semplificata.")
    return ConversationHandler.END


async def handle_organ_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _send(update, "Flusso etichettatura dismesso nella logica semplificata.")
    return ConversationHandler.END


async def pending_label_name_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return


async def handle_unprompted_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _guard(update):
        return ConversationHandler.END
    _clear_diagnosis_state(context)
    context.user_data["diagnosis_active"] = True
    context.user_data.pop("diag_user_description", None)
    # Salva la foto e poi chiede la descrizione utente (stesso flusso della diagnosi guidata)
    saved = await _download_telegram_image(update)
    if not saved:
        _clear_diagnosis_state(context)
        await _send(update, "Immagine non valida.")
        return ConversationHandler.END
    context.user_data["diag_image_path"] = str(saved)
    await _send(update, "📷 Foto ricevuta.")
    return await _ask_user_description(update, context)


async def handle_label_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _send(update, "Flusso etichettatura dismesso nella logica semplificata.")
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _guard(update):
        return ConversationHandler.END
    context.user_data.clear()
    await _send(update, "Operazione annullata.")
    return ConversationHandler.END


async def timeout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    if update is None:
        return ConversationHandler.END
    await _send(update, "Sessione scaduta. Usa /nuovo per ricominciare.")
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
    elif query.data == CMD_SENSORS:
        await sensors(update, context)
    elif query.data == CMD_EXPORT:
        await export_excel(update, context)
    elif query.data == CMD_IMAGES:
        await images(update, context)
    elif query.data == CMD_HEALTH:
        await health(update, context)
    elif query.data == CMD_PREFLIGHT:
        await preflight(update, context)
    elif query.data == CMD_ACADEMY:
        await academy_start(update, context)
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
    agent = _get_agent(context)
    if not agent:
        await _send(update, "Errore sistema: agent non disponibile.")
        return
    records_db = agent.database.get_recent(limit=10000)
    if not records_db:
        await _send(update, "Nessun dato da esportare.")
        return

    def _convert_records():
        converted = []
        import json as _json
        for r in records_db:
            converted.append({
                "timestamp": r.get("timestamp"),
                "sensor_data": {"source": r.get("sensor_source")},
                "ai_result": {
                    "class": r.get("ai_class"),
                    "confidence": r.get("ai_confidence", 0) / 100,
                    "simulated": bool(r.get("ai_simulated")),
                    "top3": _json.loads(r.get("ai_top3_json") or "[]"),
                },
                "diagnosis": {
                    "plant_status": r.get("plant_status"),
                    "overall_risk": r.get("overall_risk"),
                    "needs_human_review": bool(r.get("needs_review")),
                    "summary": r.get("summary"),
                    "explanation": r.get("explanation"),
                    "activated_rules": _json.loads(r.get("activated_rules") or "[]"),
                    "sensor_snapshot": {
                        "temperature_c": r.get("temperature_c"),
                        "humidity_pct":  r.get("humidity_pct"),
                        "pressure_hpa":  r.get("pressure_hpa"),
                        "light_lux":     r.get("light_lux"),
                        "co2_ppm":       r.get("co2_ppm"),
                        "ph":            r.get("ph"),
                        "ec_ms_cm":      r.get("ec_ms_cm"),
                        "source":        r.get("sensor_source"),
                    },
                },
                "recommendations": _json.loads(r.get("recommendations") or "[]"),
            })
        return converted

    converted = await asyncio.to_thread(_convert_records)
    ok = await asyncio.to_thread(agent.exporter.export_all, converted)
    if not ok:
        await _send(update, "Errore durante l'esportazione Excel.")
        return
    from data.excel_export import EXPORT_PATH
    if not EXPORT_PATH.exists():
        await _send(update, "File Excel non trovato.")
        return
    with open(EXPORT_PATH, "rb") as f:
        await update.effective_chat.send_document(document=f, filename=EXPORT_PATH.name)


async def preflight(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _guard(update):
        return
    from ai.preflight_validator import validate_model_artifacts
    await _send(update, "Preflight AI in corso...")

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
        await _send(update, f"Preflight AI fallito: {exc}")
        return
    msg = (
        "Preflight OK ✅\n"
        f"Classe: {report['predicted_class']}\n"
        f"Confidenza: {report['confidence'] * 100:.2f}%\n"
        f"Input shape: {report['input_shape']}\n"
        f"Output shape: {report['output_shape']}"
    )
    await _send(update, msg)


async def license_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _guard(update):
        return
    license_path = Path(__file__).resolve().parent.parent / "LICENSE"
    text = license_path.read_text(encoding="utf-8") if license_path.exists() else "Licenza non trovata."
    await _send_long(update, text)


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


def _academy_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Tutorial guidato", callback_data="ACAD_TUT_START")],
        [InlineKeyboardButton("Sim: Identifica malattia", callback_data="ACAD_SIM_DIAG")],
        [InlineKeyboardButton("Sim: Valuta rischio", callback_data="ACAD_SIM_RISK")],
        [InlineKeyboardButton("Sim: Scegli intervento", callback_data="ACAD_SIM_ACTION")],
        [InlineKeyboardButton("Quiz teorico", callback_data="ACAD_QUIZ")],
        [InlineKeyboardButton("Progresso", callback_data="ACAD_PROGRESS")],
        [InlineKeyboardButton("Lab MLOps", callback_data="ACAD_LAB")],
        [InlineKeyboardButton("Esci", callback_data="ACAD_EXIT")],
    ])


async def academy_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _guard(update):
        return
    progress = _load_academy_progress()
    progress["sessions"] += 1
    _save_academy_progress(progress)
    await _send(update, "DELTA Academy — scegli una modalità:", reply_markup=_academy_menu_keyboard())


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
        await _send(update, "Uscita da DELTA Academy.")
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
    ("PASSO 2 — Menu", "Dal menu puoi avviare diagnosi, sensori, report, export Excel e Academy."),
    ("PASSO 3 — Diagnosi", "Invia una foto o usa input_images, poi DELTA analizza immagine + sensori."),
    ("PASSO 4 — Rischio", "Livelli: nessuno/basso/medio/alto/critico. Confidenza bassa richiede revisione."),
    ("PASSO 5 — Parametri", "Temperatura, umidità, luce, CO₂, pH, EC: restano la base per la diagnosi."),
]


async def _academy_send_tutorial_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    idx = int(context.user_data.get("academy_tutorial_idx", 0))
    if idx >= len(TUTORIAL_STEPS):
        progress = _load_academy_progress()
        progress["total_score"] += 10
        _save_academy_progress(progress)
        await _send(update, "Tutorial completato ✅ (+10 punti)", reply_markup=_academy_menu_keyboard())
        return
    title, content = TUTORIAL_STEPS[idx]
    context.user_data["academy_tutorial_idx"] = idx + 1
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("Avanti", callback_data="ACAD_TUT_NEXT")],
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
        f"Sintomi: {scenario['sintomi_visivi']}\n"
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
        await _send(update, "Scenario non disponibile.")
        return
    idx = int(data.split("_")[-1])
    chosen = options[idx] if idx < len(options) else None
    progress = _load_academy_progress()
    progress["sim_total"] += 1
    if chosen == scenario["ai_class"]:
        progress["sim_correct"] += 1
        progress["total_score"] += 15
        msg = f"Corretto ✅ +15 punti\nDiagnosi: {scenario['diagnosi']}"
    else:
        msg = f"Errato. Corretta: {scenario['ai_class']}\nDiagnosi: {scenario['diagnosi']}"
    _save_academy_progress(progress)
    await _send_long(update, msg, reply_markup=_academy_menu_keyboard())


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
        f"Sintomi: {scenario['sintomi_visivi']}\n"
        f"Quale rischio assegneresti?"
    )
    await _send_long(update, text, reply_markup=keyboard)


async def _academy_sim_risk_answer(update: Update, context: ContextTypes.DEFAULT_TYPE, data: str):
    scenario = context.user_data.get("academy_scenario")
    levels = ["nessuno", "basso", "medio", "alto", "critico"]
    if not scenario:
        await _send(update, "Scenario non disponibile.")
        return
    idx = int(data.split("_")[-1])
    chosen = levels[idx] if idx < len(levels) else None
    correct = scenario["rischio_corretto"]
    progress = _load_academy_progress()
    progress["sim_total"] += 1
    if chosen == correct:
        progress["sim_correct"] += 1
        progress["total_score"] += 15
        msg = f"Corretto ✅ +15 punti\nRischio: {correct.upper()}\n{scenario['diagnosi']}"
    else:
        msg = f"Errato. Corretto: {correct.upper()}\n{scenario['diagnosi']}"
    _save_academy_progress(progress)
    await _send_long(update, msg, reply_markup=_academy_menu_keyboard())


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
    await _send_long(update, "Seleziona 2 azioni corrette:", reply_markup=keyboard)


async def _academy_sim_action_answer(update: Update, context: ContextTypes.DEFAULT_TYPE, data: str):
    scenario = context.user_data.get("academy_scenario")
    options = context.user_data.get("academy_action_options", [])
    choices = context.user_data.get("academy_action_choices", [])
    if not scenario:
        await _send(update, "Scenario non disponibile.")
        return
    idx = int(data.split("_")[-1])
    if idx >= len(options):
        await _send(update, "Scelta non valida.")
        return
    if idx in choices:
        await _send(update, "Scelta già selezionata.")
        return
    choices.append(idx)
    context.user_data["academy_action_choices"] = choices
    if len(choices) < 2:
        await _send(update, "Seleziona un'altra azione.")
        return
    selected = [options[i] for i in choices]
    correct = set(scenario["raccomandazioni_corrette"][:2])
    progress = _load_academy_progress()
    progress["sim_total"] += 1
    if set(selected) == correct:
        progress["sim_correct"] += 1
        progress["total_score"] += 20
        msg = "Perfetto ✅ +20 punti"
    elif len(correct.intersection(selected)) == 1:
        progress["total_score"] += 5
        msg = "Una risposta corretta su due (+5 punti)"
    else:
        msg = "Nessuna azione corretta."
    _save_academy_progress(progress)
    await _send_long(update, msg, reply_markup=_academy_menu_keyboard())


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
        await _send(update, "Quiz non disponibile.")
        return
    idx = int(data.split("_")[-1])
    progress = _load_academy_progress()
    progress["quiz_total"] += 1
    if idx == question["corretta"]:
        progress["quiz_correct"] += 1
        progress["total_score"] += 10
        msg = f"Corretto ✅ +10 punti\n{question['spiegazione']}"
    else:
        correct = question["opzioni"][question["corretta"]]
        msg = f"Errato. Risposta corretta: {correct}\n{question['spiegazione']}"
    _save_academy_progress(progress)
    await _send_long(update, msg, reply_markup=_academy_menu_keyboard())


async def _academy_progress(update: Update, context: ContextTypes.DEFAULT_TYPE):
    progress = _load_academy_progress()
    msg = (
        f"Punteggio totale: {progress['total_score']}\n"
        f"Sessioni: {progress['sessions']}\n"
        f"Quiz: {progress['quiz_correct']}/{progress['quiz_total']}\n"
        f"Simulazioni: {progress['sim_correct']}/{progress['sim_total']}\n"
        f"Lab MLOps completato: {'Sì' if progress['training_lab_completed'] else 'No'}"
    )
    await _send(update, msg, reply_markup=_academy_menu_keyboard())


async def _academy_lab(update: Update, context: ContextTypes.DEFAULT_TYPE):
    progress = _load_academy_progress()
    progress["training_lab_completed"] = 1
    progress["training_lab_score"] = max(progress.get("training_lab_score", 0), 10)
    progress["total_score"] += 10
    _save_academy_progress(progress)
    await _send_long(
        update,
        "Lab MLOps completato ✅ (+10 punti)\n"
        "Checklist: dataset -> training -> conversione -> preflight -> deploy.",
        reply_markup=_academy_menu_keyboard(),
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
            MessageHandler(filters.PHOTO | filters.Document.IMAGE, handle_unprompted_photo),
        ],
        states={
            STATE_DIAG_IMAGE_SOURCE: [
                CallbackQueryHandler(choose_diag_image_source, pattern=f"^{DIAG_IMAGE_UPLOAD}$"),
                CallbackQueryHandler(choose_diag_image_source, pattern=f"^{DIAG_IMAGE_LAST}$"),
                CallbackQueryHandler(choose_diag_image_source, pattern=f"^{DIAG_IMAGE_CAMERA}$"),
            ],
            STATE_DIAG_WAIT_PHOTO: [
                MessageHandler(filters.PHOTO | filters.Document.IMAGE, receive_diag_photo),
                MessageHandler(filters.ALL, diag_expect_photo),
            ],
            STATE_DIAG_USER_DESCRIPTION: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_user_description),
            ],
            STATE_DIAG_SENSOR_MODE: [
                CallbackQueryHandler(
                    choose_sensor_mode,
                    pattern=f"^({DIAG_SENSOR_AUTO}|{DIAG_SENSOR_MANUAL})$",
                )
            ],
            STATE_DIAG_TEMP: [MessageHandler(filters.TEXT & ~filters.COMMAND, manual_sensor_input)],
            STATE_DIAG_FOLLOWUP: [
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
    application.add_handler(CommandHandler("report", report))
    application.add_handler(CommandHandler("dettaglio", detail))
    application.add_handler(CommandHandler("sensori", sensors))
    application.add_handler(CommandHandler("health", health))
    application.add_handler(CommandHandler("export", export_excel))
    application.add_handler(CommandHandler("images", images))
    application.add_handler(CommandHandler("preflight", preflight))
    application.add_handler(CommandHandler("voice", voice_mode_command))
    application.add_handler(CommandHandler("voice_lang", voice_language_command))
    application.add_handler(CommandHandler("nasa_sar", nasa_sar_connect))
    # /continua globale: funziona anche dopo END del ConversationHandler
    application.add_handler(CommandHandler("continua", continue_diagnosis_message))
    # Pulsante inline "Continua lettura" (CMD_CONTINUA) — stesso handler
    application.add_handler(CallbackQueryHandler(continue_diagnosis_message, pattern=r"^CMD_CONTINUA$"))
    application.add_handler(CommandHandler("academy", academy_start))
    application.add_handler(CommandHandler("license", license_text))
    application.add_handler(CommandHandler("batch", batch_analyze))
    application.add_handler(diagnosis_handler)
    application.add_handler(upload_handler)
    application.add_handler(chat_conv_handler)
    application.add_handler(CallbackQueryHandler(menu_callback, pattern=r"^CMD_"))
    application.add_handler(CallbackQueryHandler(academy_callback, pattern=r"^ACAD_"))
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
