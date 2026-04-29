"""
DELTA - HuggingFace Adapter per DELTA Orchestrator
Usa huggingface_hub.InferenceClient (API OpenAI-compatibile, serverless).
"""
from .base_llm_adapter import BaseLLMAdapter
from typing import Dict, Any, Optional
import os
import structlog

logger = structlog.get_logger("huggingface_adapter")

# Sistema prompt per il contesto dell'orchestratore
_ORCHESTRATOR_SYSTEM = (
    "Sei DELTA, un assistente agronomico intelligente. "
    "Rispondi sempre in italiano. "
    "Sei esperto di malattie delle piante, fitofarmaci e agronomia."
)


class HuggingFaceAdapter(BaseLLMAdapter):
    """
    Adapter HuggingFace per DELTA Orchestrator.
    Usa InferenceClient (huggingface_hub) con fallback su lista di modelli.
    """

    # Modelli in ordine di priorità per DELTA
    _MODEL_PRIORITY = [
        "mistralai/Mistral-7B-Instruct-v0.3",
        "Qwen/Qwen2.5-7B-Instruct",
        "meta-llama/Llama-3.1-8B-Instruct",
        "microsoft/Phi-3.5-mini-instruct",
        "HuggingFaceH4/zephyr-7b-beta",
        "Qwen/Qwen2.5-3B-Instruct",
    ]

    def __init__(
        self,
        model_name: Optional[str] = None,
        api_token: Optional[str] = None,
        endpoint: Optional[str] = None,
        **kwargs,
    ):
        _model = model_name or os.environ.get(
            "HF_MODEL_NAME", self._MODEL_PRIORITY[0]
        )
        super().__init__(_model, **kwargs)
        self.api_token = api_token or os.environ.get("HF_API_TOKEN", "")
        self._client = None
        self._active_model: Optional[str] = None

    def _get_client(self):
        if self._client is None:
            from huggingface_hub import InferenceClient
            self._client = InferenceClient(api_key=self.api_token, timeout=60)
        return self._client

    async def generate(self, prompt: str, context: Optional[Dict] = None) -> str:
        """Genera una risposta usando HuggingFace Inference API."""
        if not self.api_token:
            logger.warning("HF_API_TOKEN mancante")
            return "[HuggingFace error: token non configurato]"

        client = self._get_client()
        messages = [
            {"role": "system", "content": _ORCHESTRATOR_SYSTEM},
            {"role": "user", "content": prompt},
        ]

        # Usa il modello attivo o il primo della lista
        models_to_try = []
        if self._active_model:
            models_to_try.append(self._active_model)
        models_to_try.append(self.model_name)
        models_to_try.extend(
            m for m in self._MODEL_PRIORITY
            if m not in models_to_try
        )

        for model in models_to_try:
            try:
                resp = client.chat.completions.create(
                    model=model,
                    messages=messages,
                    max_tokens=512,
                    temperature=0.65,
                )
                answer = resp.choices[0].message.content.strip()
                self._active_model = model
                logger.info(
                    "HuggingFace risposta OK",
                    model=model,
                    chars=len(answer),
                )
                return answer
            except Exception as e:
                logger.warning(
                    "HuggingFace generate error",
                    model=model,
                    error=str(e)[:120],
                )
                continue

        return "[HuggingFace error: nessun modello disponibile]"

    def is_available(self) -> bool:
        """Controlla la disponibilità sincrona del servizio HF."""
        if not self.api_token:
            return False
        try:
            import httpx
            r = httpx.get(
                "https://huggingface.co/api/whoami",
                headers={"Authorization": f"Bearer {self.api_token}"},
                timeout=10,
            )
            return r.status_code == 200
        except Exception as e:
            logger.warning("HuggingFace availability check failed", error=str(e))
            return False

    def get_info(self) -> Dict[str, Any]:
        return {
            "active_model": self._active_model or self.model_name,
            "has_token": bool(self.api_token),
            "priority_list": self._MODEL_PRIORITY,
        }