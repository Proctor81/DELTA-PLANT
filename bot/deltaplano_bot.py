# Bot Telegram integrato con ChatEngine HuggingFace + Vision
import asyncio
import inspect
import logging
import threading
from chat.chat_engine import ChatEngine
from vision.mobilenet_service import MobileNetService

# HERO DEMO LOGIC: dashboard NASA-ISRO/SAR
from bot.nasa_sar_dashboard import generate_dashboard

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

    def handle_message(self, user_id, text: str, image_path: str = None, telegram_bot=None, chat_id=None) -> str:
        import logging
        logger = logging.getLogger("deltaplano.bot")
        logger.warning(f"[DEBUG] handle_message chiamato: user_id={user_id}, text={text}")
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
            # --- Genera testo ---
            lines = ["\U0001F30E NASA-ISRO/SAR Dashboard\n"]
            lines.append("Data | Soil | Temp | Humidity | Rain | Risk")
            for d in dashboard["dashboard"]:
                lines.append(f"{d['date']} | {d['soil']:.1f} | {d['temp']:.1f} | {d['humidity']:.0f} | {d['rain']:.1f} | {d['risk']:.2f}")
            lines.append("")
            lines.append(f"Rischio settimanale: {dashboard['weekly_risk']:.2f} ({dashboard['weekly_label']})")
            # Testo esplicativo HERO DEMO
            if dashboard['weekly_label'] == 'ALTO' or dashboard['weekly_label'] == 'HIGH':
                lines.append(f"Weekly mean risk {dashboard['weekly_risk']:.2f}. The micro-area shows high fungal favorability: SAR moisture proxy, humidity and rainfall are all elevated.")
            elif dashboard['weekly_label'] == 'MEDIO' or dashboard['weekly_label'] == 'MEDIUM':
                lines.append(f"Weekly mean risk {dashboard['weekly_risk']:.2f}. Moisture persistence and official weather support indicate a medium fungal pressure around this 50 m radius.")
            else:
                lines.append(f"Weekly mean risk {dashboard['weekly_risk']:.2f}. The micro-area looks comparatively drier and less supportive for fungal development across the current 7-day weather window.")
            # --- Genera immagine grafica ---
            from bot.nasa_sar_dashboard import generate_dashboard_report_image
            img = generate_dashboard_report_image(dashboard, lat, lon)
            import tempfile
            img_path = tempfile.mktemp(suffix="_dashboard.png", prefix="nasa_sar_")
            img.save(img_path)
            # Invio automatico immagine su Telegram se bot e chat_id sono forniti
            if telegram_bot is not None and chat_id is not None:
                try:
                    with open(img_path, "rb") as f:
                        try:
                            send_result = telegram_bot.send_photo(chat_id=chat_id, photo=f, caption="\n".join(lines))
                        except TypeError:
                            f.seek(0)
                            send_result = telegram_bot.send_photo(photo=f, caption="\n".join(lines))
                        if inspect.isawaitable(send_result):
                            _run_awaitable_sync(send_result)
                    return "[Immagine dashboard inviata su Telegram]"
                except Exception as e:
                    lines.append(f"[ERRORE invio immagine Telegram: {e}]")
            lines.append("")
            lines.append(f"[Immagine dashboard salvata: {img_path}]")
            return "\n".join(lines)
        # Tutto il resto: nessun altro modello, fallback o simulazione
        return "Solo la logica HERO DEMO è attiva. Scrivi 'dashboard' per il riepilogo settimanale."

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
