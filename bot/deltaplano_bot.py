# Bot Telegram integrato con ChatEngine HuggingFace + Vision
import asyncio
import inspect
import logging
import threading
import bot.nasa_sar_dashboard as nasa_dashboard
from chat.chat_engine import ChatEngine
from vision.mobilenet_service import MobileNetService

logger = logging.getLogger("delta.deltaplano_bot")


def _run_awaitable_sync(awaitable):
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(awaitable)

    result = {}
    errors = []

    def _runner():
        try:
            result["value"] = asyncio.run(awaitable)
        except Exception as exc:
            errors.append(exc)

    worker = threading.Thread(target=_runner, name="delta-deltaplano-await", daemon=True)
    worker.start()
    worker.join()

    if errors:
        raise errors[0]
    return result.get("value")


class DELTAPLANOBot:
    """
    Bot DELTA: instrada messaggi verso ChatEngine (HF LLM)
    o verso MobileNetService (vision), a seconda del contenuto.
    """

    def __init__(self, llm_model_path: str = ""):
        # Parametro mantenuto per compatibilita: il backend LLM e gestito da ChatEngine.
        _ = llm_model_path
        self.chat_engine = ChatEngine()
        self.vision_service = MobileNetService()

    def handle_message(
        self,
        user_id,
        text: str,
        image_path: str = None,
        telegram_bot=None,
        chat_id=None,
        response_language: str = "it",
    ) -> str:
        import logging
        logger = logging.getLogger("deltaplano.bot")
        logger.warning(f"[DEBUG] handle_message chiamato: user_id={user_id}, text={text}")
        english_ui = str(response_language or "").strip().lower() == "en"

        def ui_text(italian_text: str, english_text: str) -> str:
            return english_text if english_ui else italian_text

        """
        Solo logica HERO DEMO: dashboard NASA-ISRO/SAR, nessun altro modello.
        """
        user_id_str = str(user_id)
        lowered = (text or "").lower()
        if "dashboard" in lowered or "riepilogo settimanale" in lowered or "sar" in lowered:
            # Estrai lat/lon da testo o fallback su Roma
            lat, lon = 41.9028, 12.4964
            import re
            m = re.search(r"lat(?:itude)?[:=\s]+([\d\.\-]+)[,;\s]+lon(?:gitude)?[:=\s]+([\d\.\-]+)", text or "", re.I)
            if m:
                try:
                    lat = float(m.group(1))
                    lon = float(m.group(2))
                except Exception:
                    pass
            # Chiama orchestrator Python DEMO HERO
            from nasa_delta_plant.orchestrator_node import NASADeltaPlantOrchestrator
            orchestrator = NASADeltaPlantOrchestrator()
            import datetime
            today = datetime.date.today()
            date_range = {"start": (today - datetime.timedelta(days=6)).strftime("%Y-%m-%d"), "end": today.strftime("%Y-%m-%d")}
            geo_data = {"type": "circle", "center": {"lat": lat, "lng": lon}, "radius": 50}
            result = _run_awaitable_sync(orchestrator.analyze_nasa_only(geo_data, date_range))
            dashboard = result["dashboard"]
            report_text = nasa_dashboard.build_dashboard_plaintext_report(dashboard, language=response_language)
            # --- Genera immagine grafica ---
            img = nasa_dashboard.generate_dashboard_report_image(dashboard, lat, lon, language=response_language)
            import tempfile
            img_path = tempfile.mktemp(suffix="_dashboard.png", prefix="nasa_sar_")
            img.save(img_path)
            # Invio automatico immagine su Telegram se bot e chat_id sono forniti
            if telegram_bot is not None and chat_id is not None:
                try:
                    with open(img_path, "rb") as f:
                        try:
                            send_result = telegram_bot.send_photo(chat_id=chat_id, photo=f, caption=report_text)
                        except TypeError:
                            f.seek(0)
                            send_result = telegram_bot.send_photo(photo=f, caption=report_text)
                        if inspect.isawaitable(send_result):
                            _run_awaitable_sync(send_result)
                    return ui_text("[Immagine dashboard inviata su Telegram]", "[Dashboard image sent on Telegram]")
                except Exception as e:
                    report_text = f"{report_text}\n{ui_text('[ERRORE invio immagine Telegram:', '[Telegram image send error:]')} {e}]"
            return f"{report_text}\n\n{ui_text('[Immagine dashboard salvata:', '[Dashboard image saved:')} {img_path}]"
        # Tutto il resto: nessun altro modello, fallback o simulazione
        return ui_text(
            "Solo la logica HERO DEMO è attiva. Scrivi 'dashboard' per il riepilogo settimanale.",
            "Only the HERO DEMO logic is active. Type 'dashboard' for the weekly summary.",
        )

    def handle_command(self, user_id, command: str) -> str:
        """Gestisce comandi speciali del bot."""
        user_id_str = str(user_id)
        logger.info(f"DELTAPLANOBot.handle_command: user_id={user_id_str}, command={command}")
        if command == "/reset":
            self.chat_engine.reset(user_id_str)
            return "Memoria conversazione resettata."
        elif command == "/status":
            status = self.chat_engine.get_status()
            hf = "\u2705" if status.get("hf_token_valid") else "\u274c"
            model = status.get("hf_active_model", "N/D")
            return f"LLM HuggingFace: {hf} ({model})\nMobileNet: \u2705"
        else:
            return "Comando non riconosciuto."
