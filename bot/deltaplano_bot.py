# Bot Telegram integrato con ChatEngine HuggingFace + Vision
import logging
from chat.chat_engine import ChatEngine
from vision.mobilenet_service import MobileNetService

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
        """Instrada messaggio testo/immagine e restituisce la risposta."""
        user_id_str = str(user_id)
        if image_path:
            try:
                result = self.vision_service.classify(image_path)
                cls = result.get("class", "Sconosciuto")
                conf = result.get("confidence", 0.0)
                logger.info(f"Vision: {cls} ({conf:.1%}) per user {user_id_str}")
                return f"Analisi immagine: {cls} (confidenza {conf:.1%})"
            except Exception as exc:
                logger.warning(f"Errore vision: {exc}")
                return "Impossibile analizzare l'immagine."
        try:
            response = self.chat_engine.chat(user_id_str, text)
            logger.info(f"Chat LLM risposta per user {user_id_str}: {response[:60]}")
            return response
        except Exception as exc:
            logger.error(f"Errore chat_engine: {exc}", exc_info=True)
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
