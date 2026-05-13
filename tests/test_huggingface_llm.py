import sys
from types import SimpleNamespace

from llm.huggingface_llm import HuggingFaceLLM


class _FakeCompletions:
    def __init__(self, outcomes):
        self._outcomes = list(outcomes)
        self.calls = 0

    def create(self, **kwargs):
        outcome = self._outcomes[self.calls]
        self.calls += 1
        if isinstance(outcome, Exception):
            raise outcome
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=outcome))]
        )


class _FakeClient:
    def __init__(self, outcomes):
        self.completions = _FakeCompletions(outcomes)
        self.chat = SimpleNamespace(completions=self.completions)


def test_huggingface_llm_retries_transient_provider_error(monkeypatch):
    llm = HuggingFaceLLM(api_token="hf_test", model_name="test/model")
    fake_client = _FakeClient([
        RuntimeError("Request ID: Root=1-abc transient provider error"),
        "Risposta recuperata",
    ])
    monkeypatch.setattr(llm, "_get_client", lambda: fake_client)

    response, model = llm.chat("ciao")

    assert response == "Risposta recuperata"
    assert model == "test/model"
    assert fake_client.completions.calls == 2


def test_huggingface_llm_hides_request_id_from_user(monkeypatch):
    llm = HuggingFaceLLM(api_token="hf_test", model_name="test/model")
    fake_client = _FakeClient([
        RuntimeError("Request ID: Root=1-abc provider temporary unavailable"),
        RuntimeError("Request ID: Root=1-def provider temporary unavailable"),
    ])
    monkeypatch.setattr(llm, "_get_client", lambda: fake_client)

    response, model = llm.chat("ciao")

    assert model == "none"
    assert "Request ID" not in response
    assert "temporaneamente non disponibile" in response


def test_huggingface_llm_recreates_client_before_retry(monkeypatch):
    llm = HuggingFaceLLM(api_token="hf_test", model_name="test/model")
    clients = [
        _FakeClient([RuntimeError("Request ID: Root=1-abc transient provider error")]),
        _FakeClient(["Risposta dal client ricreato"]),
    ]
    call_index = {"value": 0}

    def fake_get_client():
        idx = min(call_index["value"], len(clients) - 1)
        call_index["value"] += 1
        return clients[idx]

    reset_flags = []

    monkeypatch.setattr(llm, "_get_client", fake_get_client)
    monkeypatch.setattr(llm, "_reset_client", lambda: reset_flags.append(True))

    response, model = llm.chat("ciao")

    assert response == "Risposta dal client ricreato"
    assert model == "test/model"
    assert reset_flags == [True]
    assert call_index["value"] >= 2


def test_huggingface_llm_auth_error_checks_token_before_blaming_it(monkeypatch):
    llm = HuggingFaceLLM(api_token="hf_test", model_name="test/model")
    fake_client = _FakeClient([
        RuntimeError("Client error '401 Unauthorized' for url 'https://router.huggingface.co/v1/chat/completions'"),
    ])
    monkeypatch.setattr(llm, "_get_client", lambda: fake_client)
    monkeypatch.setattr(llm, "validate_token", lambda: (True, "Token valido (utente HF: test)"))

    response, model = llm.chat("ciao")

    assert model == "none"
    assert "Token HuggingFace non valido" not in response
    assert "permesso 'Make calls to Inference Providers'" in response


def test_huggingface_llm_auth_error_reports_invalid_token_when_validation_fails(monkeypatch):
    llm = HuggingFaceLLM(api_token="hf_test", model_name="test/model")
    fake_client = _FakeClient([
        RuntimeError("Client error '401 Unauthorized' for url 'https://router.huggingface.co/v1/chat/completions'"),
    ])
    monkeypatch.setattr(llm, "_get_client", lambda: fake_client)
    monkeypatch.setattr(
        llm,
        "validate_token",
        lambda: (
            False,
            "Token HF non valido (401 Unauthorized). Crea un nuovo token.",
        ),
    )

    response, model = llm.chat("ciao")

    assert model == "none"
    assert "Token HuggingFace non valido" in response


def test_validate_token_reports_missing_token_without_calling_hf(monkeypatch):
    monkeypatch.delenv("HF_API_TOKEN", raising=False)
    llm = HuggingFaceLLM(api_token="", model_name="test/model")

    ok, message = llm.validate_token()

    assert ok is False
    assert "Token assente" in message


def test_validate_token_reports_invalid_token_on_401(monkeypatch):
    class FakeApi:
        def __init__(self, token):
            self.token = token

        def whoami(self):
            raise RuntimeError("401 Unauthorized")

    monkeypatch.setitem(sys.modules, "huggingface_hub", SimpleNamespace(HfApi=FakeApi))

    llm = HuggingFaceLLM(api_token="hf_bad", model_name="test/model")

    ok, message = llm.validate_token()

    assert ok is False
    assert "Token HF non valido" in message