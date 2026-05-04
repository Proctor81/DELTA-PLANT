"""
DELTA - interface/telegram_bot.py
Bot Telegram interattivo per accesso conversazionale alle API DELTA.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import shutil
import random
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Set, List, Tuple

import requests

from core.config import (
    TELEGRAM_CONFIG,
    API_CONFIG,
    INPUT_IMAGES_DIR,
    FINETUNING_CONFIG,
    FINETUNING_FLOWER_CONFIG,
    FINETUNING_FRUIT_CONFIG,
    MODEL_CONFIG,
    VISION_CONFIG,
    FLOWER_LABELS,
    FRUIT_LABELS,
    DATASETS_DIR,
    LEARNING_BY_DOING_DIR,
)

try:
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
    from telegram.ext import (
        Application,
        CallbackQueryHandler,
        CommandHandler,
        ConversationHandler,
        ContextTypes,
        MessageHandler,
        filters,
    )
    TELEGRAM_AVAILABLE = True
except ImportError:
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
    # Inibisci la chat libera durante una diagnosi attiva (es. inserimento manuale sensori).
    # I valori dei sensori non devono essere instradati all'LLM.
    if context.user_data.get("diagnosis_active"):
        logger.debug("free_chat_handler: diagnosi in corso, chat libera inibita")
        return
    user_text = update.message.text.strip()
    user_id = update.effective_user.id if update.effective_user else None
    logger.info(f"free_chat_handler: Ricevuto da {user_id}: {user_text}")
    # Se il testo è un comando, instrada a DELTAPLANOBot.handle_command
    if user_text.startswith("/"):
        from bot.deltaplano_bot import DELTAPLANOBot
        deltachat_bot = context.application.bot_data.get("deltaplano_bot")
        if not deltachat_bot:
            deltachat_bot = DELTAPLANOBot("models/tinyllama-1.1b-chat-v1.0-q4_K_M.gguf")
            context.application.bot_data["deltaplano_bot"] = deltachat_bot
        logger.info(f"Instrado comando a DELTAPLANOBot: {user_text}")
        response = await asyncio.to_thread(deltachat_bot.handle_command, user_id, user_text)
        logger.info(f"Risposta DELTAPLANOBot: {response}")
        await _send(update, response)
        return
    # Altrimenti, instrada a DELTAPLANOBot.handle_message
    from bot.deltaplano_bot import DELTAPLANOBot
    deltachat_bot = context.application.bot_data.get("deltaplano_bot")
    if not deltachat_bot:
        deltachat_bot = DELTAPLANOBot("models/tinyllama-1.1b-chat-v1.0-q4_K_M.gguf")
        context.application.bot_data["deltaplano_bot"] = deltachat_bot
    logger.info(f"Instrado messaggio a DELTAPLANOBot: {user_text}")
    response = await asyncio.to_thread(deltachat_bot.handle_message, user_id, user_text)
    logger.info(f"Risposta DELTAPLANOBot: {response}")
    await _send(update, response)

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
CMD_FINETUNE = "CMD_FINETUNE"
CMD_ACADEMY = "CMD_ACADEMY"
CMD_LICENSE = "CMD_LICENSE"
CMD_BATCH = "CMD_BATCH"
CMD_CHAT = "CMD_CHAT"
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
    allowed_ids = set(TELEGRAM_CONFIG.get("authorized_users", []))
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


def _menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🆕 Diagnosi", callback_data=CMD_DIAGNOSE),
        ],
        [
            InlineKeyboardButton("🌡 Sensori", callback_data=CMD_SENSORS),
            InlineKeyboardButton("📤 Export Excel", callback_data=CMD_EXPORT),
        ],
        [
            InlineKeyboardButton("🧪 Preflight", callback_data=CMD_PREFLIGHT),
        ],
        [
            InlineKeyboardButton("🎓 Academy", callback_data=CMD_ACADEMY),
            InlineKeyboardButton("📄 Licenza", callback_data=CMD_LICENSE),
        ],
        [
            InlineKeyboardButton("✅ Health", callback_data=CMD_HEALTH),
        ],
    ])


async def _send(update: Update, text: str, reply_markup: Optional[InlineKeyboardMarkup] = None, parse_mode: str = None):
    # parse_mode è opzionale e passato come keyword argument
    import inspect
    frame = inspect.currentframe()
    args, _, _, values = inspect.getargvalues(frame)
    parse_mode = values.get('parse_mode', None)
    reply_args = {"reply_markup": reply_markup}
    if parse_mode is not None:
        reply_args["parse_mode"] = parse_mode
    if update.message:
        await update.message.reply_text(text, **reply_args)
        return
    if update.callback_query:
        # Non richiamare answer() qui: ogni handler che genera una callback_query
        # deve già aver chiamato query.answer() prima di invocare _send(),
        # altrimenti si ottiene un doppio answer che causa "query id is invalid".
        await update.callback_query.message.reply_text(text, **reply_args)


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
    """Invia la diagnosi in pagine: usa /continua se il testo e lungo."""
    chunks = _split_message(text)
    closing = "Posso fare qualcos'altro per te? Sono a tua disposizione 🙂"

    # Sovrascrive eventuale coda precedente per evitare pagine stale.
    context.user_data.pop("diag_pending_chunks", None)
    context.user_data.pop("diag_pending_parse_mode", None)
    context.user_data.pop("diag_pending_closing", None)

    if len(chunks) == 1:
        await _send(update, chunks[0], parse_mode=parse_mode)
        await _send(update, closing)
        return

    context.user_data["diag_pending_chunks"] = chunks[1:]
    context.user_data["diag_pending_parse_mode"] = parse_mode
    context.user_data["diag_pending_closing"] = closing

    await _send(update, chunks[0], parse_mode=parse_mode)
    await _send(update, "Messaggio lungo. Per continuare digita /continua.")


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
            await _send(update, prompt_text)
        return True

    context.user_data.pop(chunks_key, None)
    context.user_data.pop(parse_mode_key, None)
    if closing_key:
        closing = context.user_data.pop(closing_key, "")
        if closing:
            await _send(update, closing)
    return True


async def continue_diagnosis_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Invia la pagina successiva di un messaggio lungo su richiesta /continua."""
    if not await _guard(update):
        return

    progressed = await _continue_pending(
        update,
        context,
        chunks_key="diag_pending_chunks",
        parse_mode_key="diag_pending_parse_mode",
        prompt_text="Per continuare digita /continua.",
        closing_key="diag_pending_closing",
    )
    if progressed:
        return

    progressed = await _continue_pending(
        update,
        context,
        chunks_key="chat_pending_chunks",
        parse_mode_key="chat_pending_parse_mode",
        prompt_text="Per continuare digita /continua.",
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


def _finetune_target(label: str) -> dict:
    organ = _resolve_organ(label)
    if organ == "flower":
        return FINETUNING_FLOWER_CONFIG
    if organ == "fruit":
        return FINETUNING_FRUIT_CONFIG
    return FINETUNING_CONFIG


def _finetune_target_by_organ(organ: str) -> dict:
    if organ == "flower":
        return FINETUNING_FLOWER_CONFIG
    if organ == "fruit":
        return FINETUNING_FRUIT_CONFIG
    return FINETUNING_CONFIG


def _finetune_configs() -> Dict[str, dict]:
    return {
        "leaf": FINETUNING_CONFIG,
        "flower": FINETUNING_FLOWER_CONFIG,
        "fruit": FINETUNING_FRUIT_CONFIG,
    }


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
    return True


def _api_url(path: str) -> str:
    base = TELEGRAM_CONFIG.get("api_base_url", "http://localhost:5000").rstrip("/")
    return f"{base}/{path.lstrip('/')}"


async def _api_request(
    method: str,
    path: str,
    json_body: Optional[Dict[str, Any]] = None,
    params: Optional[Dict[str, Any]] = None,
):
    url = _api_url(path)
    timeout = TELEGRAM_CONFIG.get("request_timeout_sec", 5)

    def _do_request():
        return requests.request(method, url, json=json_body, params=params, timeout=timeout)

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


def _format_diagnosis(record: Dict[str, Any]) -> str:
    pass
def _format_diagnosis_full(record: Dict[str, Any]) -> str:
    dx = record.get("diagnosis", {})
    ai = record.get("ai_result", {})
    recs = record.get("recommendations", [])
    organ_results = record.get("organ_results", {})
    organ_analyses = dx.get("organ_analyses", {})
    quantum_risk = dx.get("quantum_risk", {})
    sensor = record.get("sensor_snapshot", {})
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
        logger.info("ChatEngine inizializzato (HF LLM + TinyLlama fallback)")
    return engine


async def chat_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Avvia la sessione di chat intelligente."""
    if not await _guard(update):
        return ConversationHandler.END

    # v3.0: Prevent chat during active diagnosis (manual sensor input phase)
    if context.user_data.get("diagnosis_active"):
        await _send(update,
            "⏳ Una diagnosi è in corso. Completa prima con /annulla oppure attendi il termine.\n\n"
            "La chat è disabilitata durante l'acquisizione dati sensori per evitare interferenze.")
        return ConversationHandler.END

    engine = _get_chat_engine(context)
    status = engine.get_status()
    hf_ok = status.get("hf_token_valid", False)
    model_name = status.get("hf_active_model", "TinyLlama locale")

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
            "🟡 *Chat DELTA attiva* _(modalità locale — TinyLlama)_\n\n"
            "Il token HuggingFace non è configurato o non è valido.\n"
            "La chat usa il modello locale (risposte più semplici).\n\n"
            "Per abilitare la chat cloud: aggiorna `HF_API_TOKEN` in `.env`\n\n"
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

    user_id = str(update.effective_user.id if update.effective_user else "0")

    # Indicatore di digitazione
    try:
        await update.effective_chat.send_action("typing")
    except Exception:
        pass

    engine = _get_chat_engine(context)

    def _ask():
        return engine.chat(user_id, user_text)

    try:
        response = await asyncio.to_thread(_ask)
    except Exception as exc:
        logger.error("Errore chat LLM: %s", exc, exc_info=True)
        response = "Mi dispiace, si è verificato un errore. Riprova tra qualche secondo."

    await _send_chat_paginated(
        update,
        context,
        response,
        reply_markup=_chat_exit_keyboard(),
    )
    return STATE_CHAT_WAITING


async def chat_reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Azzera la memoria conversazionale dell'utente corrente."""
    if not await _guard(update):
        return STATE_CHAT_WAITING
    query = update.callback_query
    if query:
        await query.answer("Conversazione resettata ✓")
    user_id = str(update.effective_user.id if update.effective_user else "0")
    engine = _get_chat_engine(context)
    engine.reset(user_id)
    await _send(update, "🗑 Memoria conversazione azzerata. Scrivi il tuo prossimo messaggio.", reply_markup=_chat_exit_keyboard())
    return STATE_CHAT_WAITING


async def chat_exit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Termina la sessione di chat e torna al menu principale."""
    if not await _guard(update):
        return ConversationHandler.END
    query = update.callback_query
    if query:
        await query.answer("Chat terminata")
    await _send(update, "Chat terminata. Usa /menu per tornare al menu principale.", reply_markup=_menu_keyboard())
    return ConversationHandler.END


async def chat_command_chiudi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestisce /chiudi dentro la chat conversation."""
    return await chat_exit(update, context)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _guard(update):
        return ConversationHandler.END
    intro = (
        "Benvenuto in @DELTAPLANO_bot.\n"
        "Qui puoi interagire con DELTA Plant da Telegram per avviare diagnosi, "
        "consultare report e leggere i dati sensori.\n"
        "Usa /menu per vedere le azioni disponibili."
    )
    await _send(update, intro, reply_markup=_menu_keyboard())


async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _guard(update):
        return
    await _send(update, "Menu principale:", reply_markup=_menu_keyboard())


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


async def start_diagnosis(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _guard(update):
        return ConversationHandler.END

    # v3.0: Set diagnosis_active flag to inhibit chat during manual input
    context.user_data["diagnosis_active"] = True

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📷 Invia foto", callback_data=DIAG_IMAGE_UPLOAD)],
        [InlineKeyboardButton("🖼 Usa ultima immagine", callback_data=DIAG_IMAGE_LAST)],
        [InlineKeyboardButton("📸 Camera locale", callback_data=DIAG_IMAGE_CAMERA)],
    ])
    await _send(update, "Diagnosi: scegli la fonte immagine.", reply_markup=keyboard)
    return STATE_DIAG_IMAGE_SOURCE


async def choose_diag_image_source(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _guard(update):
        return ConversationHandler.END
    query = update.callback_query
    if not query:
        return ConversationHandler.END
    await query.answer()
    if query.data == DIAG_IMAGE_UPLOAD:
        await _send(update, "Invia una foto (o un file immagine) per la diagnosi.")
        return STATE_DIAG_WAIT_PHOTO
    if query.data == DIAG_IMAGE_LAST:
        latest = _get_latest_input_image()
        if not latest:
            context.user_data["diagnosis_active"] = False
            await _send(update, "Nessuna immagine in input_images. Usa 'Invia foto'.")
            return ConversationHandler.END
        context.user_data["diag_image_path"] = str(latest)
        return await _ask_user_description(update, context)
    if query.data == DIAG_IMAGE_CAMERA:
        agent = _get_agent(context)
        if not agent or agent.camera._backend is None:
            context.user_data["diagnosis_active"] = False
            await _send(update, "Camera locale non disponibile. Usa 'Invia foto'.")
            return ConversationHandler.END
        context.user_data["diag_image_path"] = ""
        return await _ask_user_description(update, context)
    context.user_data["diagnosis_active"] = False
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
    await query.answer()
    if query.data == DIAG_SENSOR_AUTO:
        return await _run_diagnosis(update, context, None)
    if query.data == DIAG_SENSOR_MANUAL:
        context.user_data["sensor_data"] = {"source": "telegram_manual"}
        context.user_data["sensor_index"] = 0
        await _send(update, f"Inserisci {SENSOR_FIELDS[0][1]} (digita x per saltare):")
        return STATE_DIAG_TEMP
    await _send(update, "Scelta non valida.")
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


def _sanitize_diagnosis_opinion(opinion: str) -> str:
    """Riduce aperture metalinguistiche poco utili nelle opinioni post-diagnosi."""
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
        # Rimuove la prima frase metalinguistica e conserva la parte tecnica.
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

    return text


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
    if user_description:
        description_block = f"\nDESCRIZIONE UTENTE: {user_description}\n"

    return (
        "Trasforma il report seguente in un UNICO messaggio finale per l'utente, "
        "in italiano, con stile professionale da agronomo esperto, dettagliato ma chiaro.\n\n"
        f"REPORT RAW RISULTATO DIAGNOSI DELTA:\n{raw_report}\n"
        f"{description_block}"
        f"{class_note}\n"
        "Vincoli obbligatori:\n"
        "- Non usare frasi metalinguistiche (es: 'Sembra che tu stia chiedendo').\n"
        "- Non ripetere il titolo del report.\n"
        "- Tieni conto della descrizione dell'utente per arricchire e personalizzare la diagnosi.\n"
        "- Struttura in 5 blocchi: 1) Esito tecnico, 2) Diagnosi differenziale breve, "
        "3) Azioni immediate (0-24h), 4) Azioni a breve (2-7 giorni), "
        "5) Monitoraggio e prevenzione.\n"
        "- Fornisci indicazioni operative concrete e verificabili.\n"
        "- Se appropriato, indica pratiche di difesa integrata e igiene colturale.\n"
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


async def _reclassify_with_description(
    engine,
    user_id: str,
    ai_class: str,
    user_description: str,
) -> str:
    """
    Usa il ChatEngine per verificare se la classe PlantVillage rilevata dal modello
    è coerente con la descrizione dell'utente. Se non lo è, restituisce la classe
    più appropriata tra quelle disponibili.
    Restituisce la classe corretta (uguale o diversa da ai_class).
    """
    classes_list = "\n".join(f"- {c}" for c in _PLANTVILLAGE_CLASSES)
    prompt = (
        f"Sei un agronomo esperto. L'utente ha descritto la sua pianta così:\n"
        f"'{user_description}'\n\n"
        f"Il modello AI ha classificato l'immagine come: '{ai_class}'\n\n"
        f"Elenco delle classi PlantVillage disponibili:\n{classes_list}\n\n"
        "Analizza se la classe rilevata è coerente con la descrizione dell'utente.\n"
        "Se la classe è corretta, rispondi SOLO con il nome esatto della classe.\n"
        "Se la classe non è corretta o non è la più appropriata, indica la classe "
        "PlantVillage più adatta tra quelle elencate.\n"
        "Rispondi SOLO con il nome esatto della classe PlantVillage, senza altre parole."
    )
    try:
        corrected = await asyncio.to_thread(engine.chat, user_id, prompt)
        corrected = corrected.strip().strip('"').strip("'")
        # Verifica che la risposta sia una classe valida
        if corrected in _PLANTVILLAGE_CLASSES:
            return corrected
        # Cerca una corrispondenza parziale (l'LLM potrebbe aver aggiunto spazi o underscore diversi)
        corrected_lower = corrected.lower().replace(" ", "_")
        for cls in _PLANTVILLAGE_CLASSES:
            if cls.lower() == corrected_lower:
                return cls
        logger.warning("Reclassificazione: classe non riconosciuta '%s', uso originale '%s'", corrected, ai_class)
    except Exception as exc:
        logger.warning("Reclassificazione fallita: %s", exc)
    return ai_class


async def _generate_followup_question(
    engine, user_id: str, user_description: str, qa_pairs: list
) -> tuple:
    """
    Genera la prossima domanda di approfondimento oppure segnala che la diagnosi può
    già essere elaborata. Restituisce (testo_domanda, should_stop).
    """
    history = ""
    for i, (q, a) in enumerate(qa_pairs, 1):
        history += f"D{i}: {q}\nR{i}: {a}\n"
    prompt = (
        "Sei un agronomo esperto che sta diagnosticando una malattia vegetale "
        "senza aver visto l'immagine della pianta.\n"
        f"Descrizione iniziale dell'utente: '{user_description}'\n"
        + (f"\nDomande e risposte precedenti:\n{history}" if history else "")
        + "\nValuta se hai informazioni sufficienti per una diagnosi accurata.\n"
        "Se sì, rispondi esattamente con: DIAGNOSI_PRONTA\n"
        "Altrimenti, formula UNA sola domanda breve e mirata (colore, aspetto, "
        "parte colpita, progressione, condizioni ambientali, ecc.).\n"
        "Rispondi SOLO con la domanda oppure con DIAGNOSI_PRONTA, senza altre parole."
    )
    try:
        resp = await asyncio.to_thread(engine.chat, user_id, prompt)
        resp = (resp or "").strip()
        if "DIAGNOSI_PRONTA" in resp.upper():
            return "", True
        return resp, False
    except Exception as exc:
        logger.warning("Errore generazione domanda follow-up: %s", exc)
        return "", True


async def _start_followup_questioning(
    update: Update, context: ContextTypes.DEFAULT_TYPE, record: dict
) -> int:
    """
    Avvia la modalità interrogazione follow-up per piante non riconosciute dal modello.
    Salva il record parziale, invia l'avviso e pone la prima domanda.
    """
    context.user_data["diag_fallback_record"] = record
    context.user_data["diag_followup_qa"] = []
    context.user_data["diag_followup_count"] = 0

    engine = _get_chat_engine(context)
    user_id = str(update.effective_user.id if update.effective_user else "0")
    user_description = context.user_data.get("diag_user_description", "")

    await _send(
        update,
        "⚠️ <b>Pianta non riconosciuta nel database.</b>\n"
        "Procederò comunque con una diagnosi basata sulla tua descrizione.\n"
        f"Ti farò al massimo {MAX_FOLLOWUP_QUESTIONS} domande di approfondimento. 🌿",
        parse_mode="HTML",
    )

    question, should_stop = await _generate_followup_question(engine, user_id, user_description, [])
    if should_stop or not question:
        await _send(update, "Ho già abbastanza informazioni. Elaboro la diagnosi... 🔬")
        await _send_conversational_diagnosis(update, context)
        return ConversationHandler.END

    context.user_data["diag_followup_count"] = 1
    context.user_data["diag_followup_last_question"] = question
    await _send(update, f"❓ (1/{MAX_FOLLOWUP_QUESTIONS}) {question}")
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
        await _send(update, "✅ Ho raccolto abbastanza informazioni. Elaboro la diagnosi... 🔬")
        await _send_conversational_diagnosis(update, context)
        return ConversationHandler.END

    engine = _get_chat_engine(context)
    user_id = str(update.effective_user.id if update.effective_user else "0")
    user_description = context.user_data.get("diag_user_description", "")

    question, should_stop = await _generate_followup_question(engine, user_id, user_description, qa_pairs)
    if should_stop or not question:
        await _send(update, "✅ Ho raccolto abbastanza informazioni. Elaboro la diagnosi... 🔬")
        await _send_conversational_diagnosis(update, context)
        return ConversationHandler.END

    new_count = count + 1
    context.user_data["diag_followup_count"] = new_count
    context.user_data["diag_followup_last_question"] = question
    await _send(update, f"❓ ({new_count}/{MAX_FOLLOWUP_QUESTIONS}) {question}")
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

    qa_text = ""
    for i, (q, a) in enumerate(qa_pairs, 1):
        qa_text += f"\nD{i}: {q}\nR{i}: {a}"

    sensor_text = ""
    if sensor_data:
        sensor_text = "\nDati ambientali rilevati:\n" + "\n".join(
            f"  {k}: {v}" for k, v in sensor_data.items() if k != "source"
        )

    prompt = (
        "Sei un agronomo esperto. Il modello AI non ha riconosciuto la pianta dal database.\n"
        f"Descrizione iniziale dell'utente: '{user_description}'\n"
        + (f"\nDomande di approfondimento e risposte:{qa_text}" if qa_text else "")
        + sensor_text
        + "\n\nFornisci una diagnosi professionale in italiano strutturata in 5 blocchi:\n"
        "1) Ipotesi diagnostica (patologia o parassita più probabile)\n"
        "2) Diagnosi differenziale (alternative possibili)\n"
        "3) Azioni immediate (0-24h)\n"
        "4) Azioni a breve termine (2-7 giorni)\n"
        "5) Monitoraggio e prevenzione\n"
        "⚠️ La diagnosi si basa solo sulla descrizione verbale, non su un'immagine classificata. "
        "Indica esplicitamente il grado di incertezza dove necessario e raccomanda "
        "conferma da un agronomo fisico se il caso è grave."
    )

    def _ask():
        return engine.chat(user_id, prompt)

    try:
        opinion = await asyncio.to_thread(_ask)
    except Exception as exc:
        logger.warning("Errore diagnosi conversazionale: %s", exc)
        await _send(update, "❌ Errore durante la diagnosi conversazionale.")
        return

    opinion = _sanitize_diagnosis_opinion(opinion)

    for key in (
        "diag_fallback_record", "diag_followup_qa", "diag_followup_count",
        "diag_followup_last_question", "diag_user_description",
    ):
        context.user_data.pop(key, None)
    context.user_data["diagnosis_active"] = False

    await _send_diagnosis_paginated(
        update,
        context,
        f"🩺 <b>DIAGNOSI CONVERSAZIONALE DELTA Plant:</b>\n\n{opinion}",
        parse_mode="HTML",
    )


async def _send_ai_diagnosis_opinion(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    record: Dict[str, Any],
):
    """Genera e invia il messaggio unico AI di risultato diagnosi."""
    try:
        await update.effective_chat.send_action("typing")
    except Exception:
        pass

    engine = _get_chat_engine(context)
    user_id = str(update.effective_user.id if update.effective_user else "0")
    user_description = context.user_data.get("diag_user_description", "")

    # ── Reclassificazione con descrizione utente ──────────────────────────
    if user_description:
        ai_class = (record.get("ai_result") or {}).get("class", "")
        if ai_class:
            corrected = await _reclassify_with_description(
                engine, user_id, ai_class, user_description
            )
            record["_corrected_class"] = corrected
            if corrected != ai_class:
                logger.info(
                    "Reclassificazione: '%s' → '%s' (descrizione: %s)",
                    ai_class, corrected, user_description[:60],
                )

    prompt = _build_diagnosis_prompt(record, user_description)

    def _ask():
        return engine.chat(user_id, prompt)

    try:
        opinion = await asyncio.to_thread(_ask)
    except Exception as exc:
        logger.warning("Errore opinione AI post-diagnosi: %s", exc)
        return

    opinion = _sanitize_diagnosis_opinion(opinion)

    await _send_diagnosis_paginated(
        update,
        context,
        f"🩺 <b>RISULTATO DIAGNOSI DELTA Plant:</b>\n\n{opinion}",
        parse_mode="HTML",
    )


async def _run_diagnosis(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    sensor_data: Optional[Dict[str, Any]],
):
    # Restituisce un ConversationHandler state (END o STATE_DIAG_FOLLOWUP)
    agent = _get_agent(context)
    if not agent:
        context.user_data["diagnosis_active"] = False
        await _send(update, "Errore sistema: agent non disponibile.")
        return ConversationHandler.END

    image_path = context.user_data.get("diag_image_path")
    image = None
    if image_path:
        image = _load_image_from_path(Path(image_path))
        if image is None:
            context.user_data["diagnosis_active"] = False
            await _send(update, "Impossibile caricare l'immagine.")
            return ConversationHandler.END
    try:
        record = await asyncio.to_thread(agent.run_diagnosis, sensor_data=sensor_data, image=image)
    except Exception as exc:
        logger.error("Errore diagnosi Telegram: %s", exc, exc_info=True)
        context.user_data["diagnosis_active"] = False
        await _send(update, "❌ Errore durante la diagnosi. La chat è nuovamente disponibile.")
        return ConversationHandler.END

    # Riattiva la chat prima di inviare i risultati
    context.user_data["diagnosis_active"] = False

    # Pianta non riconosciuta → modalità follow-up conversazionale
    if record.get("ai_result", {}).get("fallback", False):
        return await _start_followup_questioning(update, context, record)

    if record.get("diagnosis", {}).get("needs_human_review") and image_path:
        await _prompt_label_review(update, context, Path(image_path))

    # Messaggio finale unico (risultato + valutazione tecnica AI)
    await _send_ai_diagnosis_opinion(update, context, record)
    return ConversationHandler.END


def _labels_keyboard(prefix: str, labels: List[str]) -> InlineKeyboardMarkup:
    rows = []
    for i, label in enumerate(labels):
        rows.append([InlineKeyboardButton(label, callback_data=f"{prefix}{i}")])
    rows.append([InlineKeyboardButton("Salta", callback_data=UPLOAD_SKIP_LABEL)])
    return InlineKeyboardMarkup(rows)


async def _prompt_label_review(update: Update, context: ContextTypes.DEFAULT_TYPE, image_path: Path):
    context.user_data["pending_label_path"] = str(image_path)
    context.user_data["pending_label_mode"] = "REVIEW"
    context.user_data["pending_label_need_name"] = True
    await _send(update, "Confidenza bassa: inserisci il nome della pianta per il training.")


async def start_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _guard(update):
        return ConversationHandler.END
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
    await _send(update, f"Immagine salvata in input_images: {saved.name}")
    context.user_data["pending_label_path"] = str(saved)
    context.user_data["pending_label_mode"] = "TRAIN"
    context.user_data["pending_label_need_name"] = True
    context.user_data.pop("pending_label_organ", None)
    await _send(update, "Inserisci il nome della pianta (obbligatorio per training):")
    return STATE_UPLOAD_PLANT


async def handle_plant_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _guard(update):
        return ConversationHandler.END
    if not update.message:
        return STATE_UPLOAD_PLANT
    plant_name = update.message.text.strip()
    if not plant_name:
        await _send(update, "Nome pianta non valido. Inserisci il nome della pianta:")
        return STATE_UPLOAD_PLANT
    context.user_data["pending_label_plant"] = plant_name
    context.user_data["pending_label_need_name"] = False
    mode = context.user_data.get("pending_label_mode")
    if mode == "REVIEW":
        labels = _labels_for_organ(_get_agent(context), "leaf")
        if not labels:
            await _send(update, "Nessuna etichetta disponibile.")
            return ConversationHandler.END
        await _send(
            update,
            "Seleziona la classe corretta (foglia) o salta:",
            reply_markup=_labels_keyboard("LABEL_REVIEW_", labels),
        )
        return STATE_UPLOAD_LABEL

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("Foglia", callback_data=UPLOAD_ORGAN_LEAF)],
        [InlineKeyboardButton("Fiore", callback_data=UPLOAD_ORGAN_FLOWER)],
        [InlineKeyboardButton("Frutto", callback_data=UPLOAD_ORGAN_FRUIT)],
    ])
    await _send(update, "Seleziona l'organo per il training:", reply_markup=keyboard)
    return STATE_UPLOAD_ORGAN


async def handle_organ_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _guard(update):
        return ConversationHandler.END
    query = update.callback_query
    if not query:
        return ConversationHandler.END
    await query.answer()
    organ = None
    if query.data == UPLOAD_ORGAN_LEAF:
        organ = "leaf"
    elif query.data == UPLOAD_ORGAN_FLOWER:
        organ = "flower"
    elif query.data == UPLOAD_ORGAN_FRUIT:
        organ = "fruit"
    if not organ:
        await _send(update, "Scelta non valida.")
        return ConversationHandler.END
    context.user_data["pending_label_organ"] = organ
    labels = _labels_for_organ(_get_agent(context), organ)
    if not labels:
        await _send(update, "Nessuna etichetta disponibile.")
        return ConversationHandler.END
    await _send(
        update,
        f"Seleziona la classe ({organ}) o salta:",
        reply_markup=_labels_keyboard("LABEL_TRAIN_", labels),
    )
    return STATE_UPLOAD_LABEL


async def pending_label_name_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get("pending_label_need_name"):
        return
    await handle_plant_name(update, context)


async def handle_unprompted_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _guard(update):
        return ConversationHandler.END
    # Se c'è un upload etichettatura in corso, evita collisioni tra flow.
    if context.user_data.get("pending_label_path"):
        await _send(update, "Hai già un'operazione di upload in corso. Completa l'etichettatura o usa /annulla.")
        return ConversationHandler.END
    context.user_data["diagnosis_active"] = True
    context.user_data.pop("diag_user_description", None)
    await _send(update, "📷 Foto ricevuta. Avvio la procedura diagnosi.")
    return await receive_diag_photo(update, context)


async def handle_label_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _guard(update):
        return ConversationHandler.END
    query = update.callback_query
    if not query:
        return ConversationHandler.END
    await query.answer()
    data = query.data or ""
    if data == UPLOAD_SKIP_LABEL:
        plant_name = context.user_data.get("pending_label_plant", "").strip()
        path_str = context.user_data.get("pending_label_path")
        if plant_name and path_str:
            _store_learning_record(
                Path(path_str),
                plant_name=plant_name,
                label=None,
                organ=context.user_data.get("pending_label_organ"),
                user_info=_user_info(update),
            )
        await _send(update, "Etichettatura saltata.")
        context.user_data.pop("pending_label_path", None)
        context.user_data.pop("pending_label_mode", None)
        context.user_data.pop("pending_label_plant", None)
        context.user_data.pop("pending_label_organ", None)
        context.user_data.pop("pending_label_need_name", None)
        return ConversationHandler.END

    if data.startswith("LABEL_TRAIN_") or data.startswith("LABEL_REVIEW_"):
        mode = "TRAIN" if data.startswith("LABEL_TRAIN_") else "REVIEW"
        idx_str = data.split("_")[-1]
        if not idx_str.isdigit():
            await _send(update, "Scelta non valida.")
            return ConversationHandler.END
        idx = int(idx_str)
        mode = context.user_data.get("pending_label_mode")
        organ = context.user_data.get("pending_label_organ") if mode != "REVIEW" else "leaf"
        labels = _labels_for_organ(_get_agent(context), organ or "leaf")
        if idx >= len(labels):
            await _send(update, "Classe non valida.")
            return ConversationHandler.END
        label = labels[idx]
        path_str = context.user_data.get("pending_label_path")
        plant_name = context.user_data.get("pending_label_plant", "").strip()
        if not path_str:
            await _send(update, "Nessuna immagine in attesa.")
            return ConversationHandler.END
        if not plant_name:
            await _send(update, "Nome pianta mancante.")
            return ConversationHandler.END
        image = _load_image_from_path(Path(path_str))
        if image is None:
            await _send(update, "Impossibile caricare l'immagine.")
            return ConversationHandler.END
        agent = _get_agent(context)
        if not agent:
            await _send(update, "Errore sistema: agent non disponibile.")
            return
        from ai.fine_tuning import FineTuner
        target_cfg = _finetune_target_by_organ(organ or _resolve_organ(label))
        tuner = FineTuner(
            agent.model_loader,
            dataset_dir=target_cfg.get("dataset_dir"),
            save_path=target_cfg.get("model_save_path"),
            min_samples_per_class=target_cfg.get("min_samples_per_class"),
        )
        try:
            saved_path = await asyncio.to_thread(tuner.add_sample, image, label, idx)
        except Exception as exc:
            logger.error("Errore salvataggio training: %s", exc, exc_info=True)
            await _send(update, "Errore durante il salvataggio del campione.")
            return ConversationHandler.END
        _store_learning_record(
            Path(path_str),
            plant_name=plant_name,
            label=label,
            organ=organ or _resolve_organ(label),
            user_info=_user_info(update),
            training_image=Path(saved_path),
        )
        await _send(update, f"Etichetta registrata: {label} ({mode}).")
        context.user_data.pop("pending_label_path", None)
        context.user_data.pop("pending_label_mode", None)
        context.user_data.pop("pending_label_plant", None)
        context.user_data.pop("pending_label_organ", None)
        context.user_data.pop("pending_label_need_name", None)
        return ConversationHandler.END

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
    await query.answer()
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
    elif query.data == CMD_FINETUNE:
        await finetune(update, context)
    elif query.data == CMD_ACADEMY:
        await academy_start(update, context)
    elif query.data == CMD_LICENSE:
        await license_text(update, context)
    elif query.data == CMD_BATCH:
        await batch_analyze(update, context)


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


async def finetune(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _guard(update):
        return
    agent = _get_agent(context)
    if not agent:
        await _send(update, "Errore sistema: agent non disponibile.")
        return
    from ai.fine_tuning import FineTuner
    lines = ["Seleziona il dataset per il fine-tuning:"]
    configs = _finetune_configs()
    for key, cfg in configs.items():
        tuner = FineTuner(
            agent.model_loader,
            dataset_dir=cfg.get("dataset_dir"),
            save_path=cfg.get("model_save_path"),
            min_samples_per_class=cfg.get("min_samples_per_class"),
        )
        stats = tuner.get_dataset_stats()
        lines.append(f"- {key}: {stats['total']} campioni ({len(stats['classes'])} classi)")
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("Avvia foglia", callback_data="FINETUNE_RUN_LEAF")],
        [InlineKeyboardButton("Avvia fiore", callback_data="FINETUNE_RUN_FLOWER")],
        [InlineKeyboardButton("Avvia frutto", callback_data="FINETUNE_RUN_FRUIT")],
    ])
    await _send(update, "\n".join(lines), reply_markup=keyboard)


async def finetune_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _guard(update):
        return
    query = update.callback_query
    if not query:
        return
    await query.answer()
    agent = _get_agent(context)
    if not agent:
        await _send(update, "Errore sistema: agent non disponibile.")
        return
    data = query.data or ""
    if not data.startswith("FINETUNE_RUN_"):
        return
    target_key = data.replace("FINETUNE_RUN_", "").lower()
    cfg = _finetune_configs().get(target_key)
    if not cfg:
        await _send(update, "Target fine-tuning non valido.")
        return
    from ai.fine_tuning import FineTuner
    tuner = FineTuner(
        agent.model_loader,
        dataset_dir=cfg.get("dataset_dir"),
        save_path=cfg.get("model_save_path"),
        min_samples_per_class=cfg.get("min_samples_per_class"),
    )
    await _send(update, "Fine-tuning in corso (potrebbero servire minuti)...")
    success = await asyncio.to_thread(tuner.run_finetuning)
    if not success:
        await _send(update, "Fine-tuning fallito. Controllare i log.")
        return
    if target_key == "leaf":
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("Carica nuovo modello", callback_data="FINETUNE_LOAD_LEAF")],
        ])
        await _send(update, "Fine-tuning completato ✅", reply_markup=keyboard)
    else:
        await _send(
            update,
            f"Fine-tuning {target_key} completato ✅\nModello salvato in {cfg.get('model_save_path')}",
        )


async def finetune_load_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _guard(update):
        return
    query = update.callback_query
    if not query:
        return
    await query.answer()
    agent = _get_agent(context)
    if not agent:
        await _send(update, "Errore sistema: agent non disponibile.")
        return
    try:
        agent.model_loader.reload(FINETUNING_CONFIG["model_save_path"])
        await _send(update, "Nuovo modello caricato.")
    except Exception as exc:
        logger.error("Errore reload modello: %s", exc, exc_info=True)
        await _send(update, f"Errore caricamento modello: {exc}")


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
    await query.answer()
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
    if not TELEGRAM_CONFIG.get("authorized_users") and not _load_allowed_usernames():
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
            STATE_UPLOAD_PLANT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_plant_name),
            ],
            STATE_UPLOAD_ORGAN: [
                CallbackQueryHandler(
                    handle_organ_selection,
                    pattern=f"^({UPLOAD_ORGAN_LEAF}|{UPLOAD_ORGAN_FLOWER}|{UPLOAD_ORGAN_FRUIT})$",
                )
            ],
            STATE_UPLOAD_LABEL: [
                CallbackQueryHandler(handle_label_callback, pattern=r"^(LABEL_TRAIN_|LABEL_REVIEW_|UPLOAD_SKIP_LABEL)"),
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
    application = Application.builder().token(token).build()
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
    application.add_handler(CommandHandler("finetune", finetune))
    application.add_handler(CommandHandler("academy", academy_start))
    application.add_handler(CommandHandler("license", license_text))
    application.add_handler(CommandHandler("batch", batch_analyze))
    application.add_handler(diagnosis_handler)
    application.add_handler(upload_handler)
    application.add_handler(chat_conv_handler)
    application.add_handler(CallbackQueryHandler(menu_callback, pattern=r"^CMD_"))
    application.add_handler(
        CallbackQueryHandler(handle_label_callback, pattern=r"^(LABEL_TRAIN_|LABEL_REVIEW_|UPLOAD_SKIP_LABEL)")
    )
    application.add_handler(CallbackQueryHandler(finetune_callback, pattern=r"^FINETUNE_RUN_"))
    application.add_handler(CallbackQueryHandler(finetune_load_callback, pattern=r"^FINETUNE_LOAD_LEAF$"))
    application.add_handler(CallbackQueryHandler(academy_callback, pattern=r"^ACAD_"))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, pending_label_name_router), group=2)
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
