"""
DELTA - main.py
Entry point dell'applicazione DELTA Plant - AI & Robotics Orchestrator per la Salute delle Piante.
Inizializza tutti i moduli, avvia i thread e lancia l'interfaccia utente.
"""

import sys
import os

# ── Auto-rilancio con venv se si sta usando il Python di sistema ─
# Usa python3.12 (symlink robusto) se disponibile, altrimenti python
_DELTA_ROOT = os.path.dirname(os.path.abspath(__file__))
_VENV_PYTHON = os.path.join(_DELTA_ROOT, ".venv", "bin", "python3.12")
if not os.path.isfile(_VENV_PYTHON):
    _VENV_PYTHON = os.path.join(_DELTA_ROOT, ".venv", "bin", "python")
# Confronta il percorso reale (risolve symlink) per evitare loop di rilancio
if os.path.isfile(_VENV_PYTHON) and os.path.realpath(sys.executable) != os.path.realpath(_VENV_PYTHON):
    import subprocess
    sys.exit(subprocess.call([_VENV_PYTHON] + sys.argv))

import signal
import logging
import argparse
import time
import atexit
import threading

# ── Carica variabili da .env se presente ─────────────────────
_ENV_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
if os.path.isfile(_ENV_FILE):
    with open(_ENV_FILE) as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _v = _line.split("=", 1)
                os.environ.setdefault(_k.strip(), _v.strip())

# ── Setup logging prima di qualsiasi import interno ──────────
from data.logger import setup_logger
setup_logger("delta")

logger = logging.getLogger("delta.main")

# ── Singleton: impedisce più istanze in parallelo ────────────
_PID_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "delta.pid")


def _acquire_pid_lock() -> None:
    """Scrive il PID corrente su file. Termina se un'altra istanza è attiva."""
    if os.path.isfile(_PID_FILE):
        try:
            with open(_PID_FILE) as _pf:
                old_pid = int(_pf.read().strip())
            # Controlla se il processo è ancora vivo (kill -0 non invia segnale)
            os.kill(old_pid, 0)
            print(
                f"[DELTA] Un'altra istanza è già in esecuzione (PID {old_pid}).\n"
                f"  Terminarla prima di avviare DELTA, oppure eliminare: {_PID_FILE}"
            )
            sys.exit(1)
        except (ValueError, ProcessLookupError, PermissionError):
            # PID file stale o processo già terminato: si sovrascrive
            pass

    with open(_PID_FILE, "w") as _pf:
        _pf.write(str(os.getpid()))

    def _release():
        try:
            if os.path.isfile(_PID_FILE):
                os.remove(_PID_FILE)
        except OSError:
            pass

    atexit.register(_release)

from core.agent import DeltaAgent
from interface.cli import CLI
from interface.api import run_api
from interface.telegram_bot import run_telegram_bot, serve_telegram_polling
from bot.deltaplano_bot import DELTAPLANOBot

# Percorso modello LLM TinyLlama GGUF
LLM_MODEL_PATH = "models/tinyllama-1.1b-chat-v1.0-q4_K_M.gguf"
from core.config import API_CONFIG, MODEL_CONFIG, TELEGRAM_CONFIG
from core.auth import initialize_password
from ai.preflight_validator import validate_model_artifacts, PreflightGateError


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="DELTA Plant - AI & Robotics Orchestrator per la Salute delle Piante")
    parser.add_argument(
        "--preflight",
        action="store_true",
        help="Valida modello + labels + immagine di test prima dell'avvio",
    )
    parser.add_argument(
        "--preflight-only",
        action="store_true",
        help="Esegue solo la validazione e termina",
    )
    parser.add_argument(
        "--validation-image",
        default=MODEL_CONFIG["validation_image_path"],
        help="Path immagine test usata nel preflight",
    )
    parser.add_argument(
        "--preflight-min-confidence",
        type=float,
        default=MODEL_CONFIG.get("preflight_min_confidence", 0.50),
        metavar="SOGLIA",
        help="Confidenza minima richiesta per il gate di deploy (default: %(default).2f)",
    )
    parser.add_argument(
        "--enable-api",
        action="store_true",
        help="Abilita temporaneamente l'API REST senza modificare la config",
    )
    parser.add_argument(
        "--enable-telegram",
        action="store_true",
        help="Abilita temporaneamente il bot Telegram (richiede token)",
    )
    parser.add_argument(
        "--daemon",
        action="store_true",
        help="Modalità daemon: disabilita CLI interattiva anche se stdin è disponibile",
    )
    return parser


def _run_preflight(validation_image: str, min_confidence: float = 0.50):
    logger.info("Avvio validazione preflight artefatti AI...")
    report = validate_model_artifacts(
        model_path=MODEL_CONFIG["model_path"],
        labels_path=MODEL_CONFIG["labels_path"],
        image_path=validation_image,
        threads=MODEL_CONFIG["num_threads"],
        top_k=3,
        min_confidence=min_confidence,
    )
    logger.info(
        "Preflight OK | classe=%s | conf=%.2f%% | input=%s | output=%s",
        report["predicted_class"],
        report["confidence"] * 100,
        report["input_shape"],
        report["output_shape"],
    )


def _run_cli(agent: DeltaAgent) -> None:
    print("[DEBUG] Avvio CLI interattiva (menu principale)")
    logger.info("Avvio CLI interattiva (menu principale)")
    cli = CLI(agent)
    try:
        cli.run()
    except KeyboardInterrupt:
        logger.info("Interruzione utente (CTRL+C).")
    except Exception as exc:
        logger.critical("Errore critico non gestito: %s", exc, exc_info=True)


def _run_runtime(agent: DeltaAgent, args: argparse.Namespace, telegram_app) -> None:
    interactive_cli = sys.stdin.isatty() and not args.daemon

    if interactive_cli:
        if telegram_app is None:
            _run_cli(agent)
            return

        logger.info(
            "Bot Telegram attivo: CLI interattiva avviata in background; polling sul main thread."
        )
        cli_thread = threading.Thread(
            target=_run_cli,
            args=(agent,),
            name="delta-cli",
            daemon=True,
        )
        cli_thread.start()
        serve_telegram_polling(telegram_app)
        return

    if args.daemon:
        print("[DEBUG] Modalità daemon: CLI disabilitata.")
        logger.info("Flag --daemon attivo: CLI disabilitata.")
    else:
        print("[DEBUG] STDIN non interattivo: CLI disabilitata.")
        logger.info("STDIN non interattivo: CLI disabilitata.")

    if telegram_app is not None:
        # Polling Telegram sul main thread (PTB v20+ è main-thread bound).
        serve_telegram_polling(telegram_app)
        return

    while True:
        time.sleep(1)


def main():
    """Funzione principale di avvio DELTA."""
    args = _build_parser().parse_args()
    _acquire_pid_lock()
    logger.info("═══ AVVIO DELTA PLANT ORCHESTRATOR ═══")

    if args.preflight or args.preflight_only:
        try:
            _run_preflight(args.validation_image, args.preflight_min_confidence)
            print("Preflight AI completato con successo.")
        except PreflightGateError as exc:
            logger.critical("Gate di deploy non superato: %s", exc)
            print(f"[DEPLOY BLOCCATO] {exc}")
            sys.exit(1)
        except Exception as exc:
            logger.critical("Preflight AI fallito: %s", exc, exc_info=True)
            print(f"Preflight AI fallito: {exc}")
            sys.exit(1)

        if args.preflight_only:
            return

    if args.enable_api:
        API_CONFIG["enable_api"] = True
        logger.info("Flag --enable-api attivo: API REST abilitata.")

    if args.enable_telegram:
        TELEGRAM_CONFIG["enable_telegram"] = True
        logger.info("Flag --enable-telegram attivo: bot Telegram abilitato.")

    # Inizializza il sistema di autenticazione (idempotente)
    initialize_password()

    try:
        agent = DeltaAgent()
    except Exception as exc:
        logger.critical("Avvio DELTA fallito: %s", exc, exc_info=True)
        sys.exit(1)

    # ── Gestione segnali per shutdown pulito ─────────────────
    def _signal_handler(sig, frame):
        logger.info("Segnale %d ricevuto. Shutdown in corso...", sig)
        agent.shutdown()
        sys.exit(0)

    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    # ── Avvio thread sensori in background ───────────────────
    agent.start_sensor_thread()

    # ── Avvio API Flask (opzionale) ──────────────────────────
    run_api(agent)

    # ── Avvio bot Telegram (opzionale) ───────────────────────
    telegram_app = run_telegram_bot(agent)

    # ── DELTAPLANO_bot demo: SKIP (TODO non implementato, MobileNetService blocca all'init).
    # Il bot Telegram completo è già avviato sopra via run_telegram_bot.
    # if TELEGRAM_CONFIG.get("enable_telegram", False):
    #     try:
    #         deltachat_bot = DELTAPLANOBot(LLM_MODEL_PATH)
    #         print("[DELTAPLANO_bot] Avviato (LLM/Vision hybrid)")
    #     except Exception as exc:
    #         logger.error(f"Errore avvio DELTAPLANO_bot: {exc}")

    try:
        _run_runtime(agent, args, telegram_app)
    except KeyboardInterrupt:
        logger.info("Interruzione utente (CTRL+C).")
    finally:
        agent.shutdown()
        logger.info("═══ DELTA PLANT ORCHESTRATOR SPENTO ═══")


if __name__ == "__main__":
    main()
