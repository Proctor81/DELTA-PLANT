# Bot Telegram integrato con ChatEngine HuggingFace + Vision
import logging
from chat.chat_engine import ChatEngine
from vision.mobilenet_service import MobileNetService

# HERO DEMO LOGIC: dashboard NASA-ISRO/SAR
from bot.nasa_sar_dashboard import generate_dashboard

logger = logging.getLogger("delta.deltaplano_bot")


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

    def handle_message(self, user_id, text: str, image_path: str = None) -> str:
        """
        Instrada messaggio testo/immagine e restituisce la risposta.
        Dopo l'invio del risultato, la chat viene immediatamente sbloccata (nessun blocco processo).
        """
        user_id_str = str(user_id)
        if image_path:
            try:
                result = self.vision_service.classify(image_path)
                cls = result.get("class", "Sconosciuto")
                conf = result.get("confidence", 0.0)
                logger.info(f"Vision: {cls} ({conf:.1%}) per user {user_id_str}")
                # Rilascio processo/chat libera subito dopo output
                # (hook per eventuale gestione async/process release qui)
                return f"Analisi immagine: {cls} (confidenza {conf:.1%})"
            except Exception as exc:
                logger.warning(f"Errore vision: {exc}")
                # Chat libera subito dopo errore
                return "Impossibile analizzare l'immagine."

        # Se il messaggio contiene "dashboard" o "riepilogo settimanale", attiva la logica HERO DEMO
        lowered = (text or "").lower()
        if "dashboard" in lowered or "riepilogo settimanale" in lowered or "sar" in lowered:
            # MOCK: estrai lat/lon da testo, qui fissi (esempio Roma)
            lat, lon = 41.9028, 12.4964
            dashboard = generate_dashboard(lat, lon)
            # Costruisci risposta testuale
            lines = ["\U0001F30E NASA-ISRO/SAR Dashboard\n"]
            lines.append("Data | Soil | Temp | Humidity | Rain | Risk")
            for d in dashboard["dashboard"]:
                lines.append(f"{d['date']} | {d['soil']:.1f} | {d['temp']:.1f} | {d['humidity']} | {d['rain']:.1f} | {d['risk']:.2f}")
            lines.append("")
            lines.append(f"Rischio settimanale: {dashboard['weekly_risk']:.2f} ({dashboard['weekly_label']})")
            # Chat libera subito dopo output
            # (hook per eventuale gestione async/process release qui)
            return "\n".join(lines)
        try:
            response = self.chat_engine.chat(user_id_str, text)
            logger.info(f"Chat LLM risposta per user {user_id_str}: {response[:60]}")
            # Chat libera subito dopo output
            # (hook per eventuale gestione async/process release qui)
            return response
        except Exception as exc:
            logger.error(f"Errore chat_engine: {exc}", exc_info=True)
            # Chat libera subito dopo errore
            return "Errore durante l'elaborazione della richiesta."

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
