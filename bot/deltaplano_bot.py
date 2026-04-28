# Bot Telegram integrato con router
import logging
from router.router import Router
from memory.conversation_memory import ConversationMemory

# TODO: Inserire token reale e setup python-telegram-bot

class DELTAPLANOBot:
    def __init__(self, llm_model_path):
        self.router = Router(llm_model_path)
        self.memory = ConversationMemory()
        # TODO: Inizializzazione bot Telegram

    def handle_message(self, user_id, text, image_path=None):
        route, response = self.router.route(user_id, text, image_path)
        logging.info(f"User: {user_id} | Input: {text} | Route: {route} | Response: {response}")
        return response

    def handle_command(self, user_id, command):
        if command == "/reset":
            self.memory.reset(user_id)
            return "Memoria conversazione resettata."
        elif command == "/status":
            # TODO: Stato LLM + MobileNet
            return "LLM: OK\nMobileNet: OK"
        else:
            return "Comando non riconosciuto."
