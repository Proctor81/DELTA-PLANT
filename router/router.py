# Routing tra LLM e Vision
from chat.chat_engine import ChatEngine
from vision.mobilenet_service import MobileNetService


class Router:
    def __init__(self, llm_model_path: str = ""):
        # model_path mantenuto per compatibilita, backend LLM gestito internamente.
        _ = llm_model_path
        self.chat_engine = ChatEngine()
        self.vision_service = MobileNetService()

    def route(self, user_id, user_input: str, image_path=None):
        # Routing: se c'e' un'immagine o keyword, usa vision, altrimenti LLM
        if image_path or self.is_vision_task(user_input):
            result = self.vision_service.classify(image_path)
            route = "vision"
            response = result  # dict con class/confidence
        else:
            response = self.chat_engine.chat(str(user_id), user_input)
            route = "chat"
        return route, response

    def is_vision_task(self, user_input: str) -> bool:
        keywords = ["classifica", "malattia", "foglia", "pianta", "immagine", "analizza"]
        return any(k in user_input.lower() for k in keywords)
