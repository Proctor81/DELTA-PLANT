import chat.chat_engine as chat_engine
from chat.chat_engine import ChatEngine


class FakeMemory:
    def __init__(self, history):
        self._history = list(history)
        self.appended = []

    def get_history(self, user_id):
        return list(self._history)

    def append(self, user_id, user_input, response):
        self.appended.append((user_id, user_input, response))


class FakeLLM:
    def __init__(self, response_text="Risposta di follow-up"):
        self.response_text = response_text
        self.calls = []

    def chat(self, user_message, history=None, system_prompt=None):
        self.calls.append({
            "user_message": user_message,
            "history": history or [],
            "system_prompt": system_prompt,
        })
        return self.response_text, "fake-model"


def _build_engine(history):
    engine = ChatEngine()
    engine._hf_available = True
    engine.memory = FakeMemory(history)
    engine._hf_llm = FakeLLM()
    return engine


def test_extract_latest_diagnosis_context_returns_latest_saved_diagnosis():
    engine = _build_engine([])
    context = engine._extract_latest_diagnosis_context([
        "Utente: domanda generica",
        "DELTA: risposta generica",
        "Utente: Ho chiesto una diagnosi della pianta.\nPianta: pomodoro.\nElementi completi della diagnosi:\nStato pianta: Compromesso",
        "DELTA: Diagnosi finale operativa sul pomodoro.",
    ])

    assert "Pianta: pomodoro." in context
    assert "Elementi completi della diagnosi:" in context
    assert "Diagnosi finale operativa sul pomodoro." in context


def test_chat_anchors_followup_to_latest_diagnosis_context():
    history = [
        "Utente: Ho chiesto una diagnosi della pianta.\nPianta: pomodoro.\nElementi completi della diagnosi:\nStato pianta: Compromesso\nRischio: ALTO",
        "DELTA: Diagnosi finale operativa sul pomodoro con rischio alto.",
    ]
    engine = _build_engine(history)

    response = engine.chat("77", "approfondisci il nome della pianta e il rischio")

    assert response == "Risposta di follow-up"
    call = engine._hf_llm.calls[0]
    assert "DIAGNOSI DELTA RECENTE" in call["user_message"]
    assert "Pianta: pomodoro." in call["user_message"]
    assert "approfondisci il nome della pianta e il rischio" in call["user_message"]
    assert "devi usare quella diagnosi come contesto tecnico principale" in call["system_prompt"]
    assert engine.memory.appended == [
        ("77", "approfondisci il nome della pianta e il rischio", "Risposta di follow-up")
    ]


def test_chat_leaves_unrelated_question_unwrapped():
    history = [
        "Utente: Ho chiesto una diagnosi della pianta.\nPianta: pomodoro.",
        "DELTA: Diagnosi finale operativa sul pomodoro.",
    ]
    engine = _build_engine(history)

    engine.chat("77", "come funziona la fotosintesi?")

    call = engine._hf_llm.calls[0]
    assert call["user_message"] == "come funziona la fotosintesi?"
    assert "Gestione del contesto diagnostico" not in call["system_prompt"]


def test_chat_engine_loads_env_when_instantiated_outside_main(monkeypatch, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "HF_API_TOKEN=hf_test_token\nHF_MODEL_NAME=test/model\nHF_MAX_TOKENS=321\nHF_TIMEOUT=45\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(chat_engine, "_ENV_FILE", env_file)
    monkeypatch.delenv("HF_API_TOKEN", raising=False)
    monkeypatch.delenv("HF_MODEL_NAME", raising=False)
    monkeypatch.delenv("HF_MAX_TOKENS", raising=False)
    monkeypatch.delenv("HF_TIMEOUT", raising=False)

    engine = ChatEngine()

    assert engine._hf_llm.api_token == "hf_test_token"
    assert engine._hf_llm.model_name == "test/model"
    assert engine._hf_llm.max_tokens == 321
    assert engine._hf_llm.timeout == 45
    assert engine._hf_available is True