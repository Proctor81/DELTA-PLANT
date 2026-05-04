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

    # Modello default consigliato (sovrascrivibile con HF_MODEL_NAME)
    _DEFAULT_MODEL = "meta-llama/Llama-3.1-8B-Instruct"

    def __init__(
        self,
        model_name: Optional[str] = None,
        api_token: Optional[str] = None,
        endpoint: Optional[str] = None,
        **kwargs,
    ):
        _model = model_name or os.environ.get(
            "HF_MODEL_NAME", self._DEFAULT_MODEL
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

        model = self._active_model or self.model_name
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
            return f"[HuggingFace error: {e}]"

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
            "priority_list": [self.model_name],
        }