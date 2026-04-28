# Routing tra LLM e Vision
from chat.chat_engine import ChatEngine
from vision.mobilenet_service import MobileNetService

class Router:
    def __init__(self, llm_model_path):
        self.chat_engine = ChatEngine(llm_model_path)
        self.vision_service = MobileNetService()

    def route(self, user_id, user_input, image_path=None):
        # Routing: se c'è un'immagine o keyword, usa vision, altrimenti LLM
        if image_path or self.is_vision_task(user_input):
            response = self.vision_service.classify(image_path)
            route = "vision"
        else:
            response = self.chat_engine.chat(user_id, user_input)
            route = "chat"
        return route, response

    def is_vision_task(self, user_input):
        # TODO: Migliorare con regole/keyword
        keywords = ["classifica", "malattia", "foglia", "pianta", "immagine"]
        return any(k in user_input.lower() for k in keywords)
