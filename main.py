"""
DELTA - main.py
Entry point dell'applicazione DELTA AI Agent.
Inizializza tutti i moduli, avvia i thread e lancia l'interfaccia utente.
"""

import sys
import os

# ── Auto-rilancio con venv se si sta usando il Python di sistema ─
_VENV_PYTHON = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".venv", "bin", "python")
if os.path.isfile(_VENV_PYTHON) and os.path.abspath(sys.executable) != os.path.abspath(_VENV_PYTHON):
    import subprocess
    sys.exit(subprocess.call([_VENV_PYTHON] + sys.argv))

import signal
import logging
import argparse
import time

# ── Setup logging prima di qualsiasi import interno ──────────
from data.logger import setup_logger
setup_logger("delta")

logger = logging.getLogger("delta.main")

from core.agent import DeltaAgent
from interface.cli import CLI
from interface.api import run_api
from interface.telegram_bot import run_telegram_bot
from core.config import API_CONFIG, MODEL_CONFIG, TELEGRAM_CONFIG
from core.auth import initialize_password
from ai.preflight_validator import validate_model_artifacts, PreflightGateError


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="DELTA AI Agent")
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


def main():
    """Funzione principale di avvio DELTA."""
    args = _build_parser().parse_args()
    logger.info("═══ AVVIO DELTA AI AGENT ═══")

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
    run_telegram_bot(agent)

    # ── Interfaccia CLI ──────────────────────────────────────
    if sys.stdin.isatty():
        cli = CLI(agent)
        try:
            cli.run()
        except KeyboardInterrupt:
            logger.info("Interruzione utente (CTRL+C).")
        except Exception as exc:
            logger.critical("Errore critico non gestito: %s", exc, exc_info=True)
        finally:
            agent.shutdown()
            logger.info("═══ DELTA AI AGENT SPENTO ═══")
    else:
        logger.info("STDIN non interattivo: CLI disabilitata. Processo in attesa.")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("Interruzione utente (CTRL+C).")
        finally:
            agent.shutdown()
            logger.info("═══ DELTA AI AGENT SPENTO ═══")


if __name__ == "__main__":
    main()
