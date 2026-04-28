# Chat Engine per TinyLlama
from memory.conversation_memory import ConversationMemory
from llm.llama_cpp_wrapper import LlamaCppWrapper

SYSTEM_PROMPT = """
Sei DELTA, un assistente tecnico, conciso e utile. Rispondi sempre in italiano, anche se la domanda è in inglese o in un'altra lingua.
"""

class ChatEngine:
    def __init__(self, model_path):
        self.llm = LlamaCppWrapper(model_path)
        self.memory = ConversationMemory()

    def chat(self, user_id, user_input):
        history = self.memory.get_history(user_id)
        prompt = self.format_prompt(history, user_input)
        # Ottieni solo la prima risposta generata (stringa)
        response = ""
        for token in self.llm.generate(prompt):
            response += token + " "
        response = response.strip()
        self.memory.append(user_id, user_input, response)
        return response

    def format_prompt(self, history, user_input):
        # TODO: Formattazione prompt per TinyLlama
        return SYSTEM_PROMPT + "\n" + "\n".join(history) + "\nUtente: " + user_input + "\nDELTA:"
