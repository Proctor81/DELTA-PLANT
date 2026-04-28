# Gestione memoria conversazionale per utente

class ConversationMemory:
    def __init__(self):
        self.sessions = {}

    def get_history(self, user_id):
        return self.sessions.get(user_id, [])

    def append(self, user_id, user_input, response):
        if user_id not in self.sessions:
            self.sessions[user_id] = []
        self.sessions[user_id].append(f"Utente: {user_input}")
        self.sessions[user_id].append(f"DELTA: {response}")

    def reset(self, user_id):
        self.sessions[user_id] = []
