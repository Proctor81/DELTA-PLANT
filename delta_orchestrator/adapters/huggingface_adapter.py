"""
HuggingFace Adapter per DELTA Ð Orchestrator
"""
from .base_llm_adapter import BaseLLMAdapter
from typing import Dict, Any, Optional
import structlog
import httpx

logger = structlog.get_logger("huggingface_adapter")

class HuggingFaceAdapter(BaseLLMAdapter):
    """Adapter per modelli HuggingFace (API inference o locale)."""
    def __init__(self, model_name: str, api_token: Optional[str] = None, endpoint: Optional[str] = None, **kwargs):
        super().__init__(model_name, **kwargs)
        self.api_token = api_token
        self.endpoint = endpoint or f"https://api-inference.huggingface.co/models/{model_name}"
        self._client = httpx.AsyncClient(timeout=60)

    async def generate(self, prompt: str, context: Optional[Dict] = None) -> str:
        headers = {"Authorization": f"Bearer {self.api_token}"} if self.api_token else {}
        payload = {"inputs": prompt}
        try:
            response = await self._client.post(self.endpoint, headers=headers, json=payload)
            response.raise_for_status()
            result = response.json()
            logger.info("HuggingFace response", result=result)
            if isinstance(result, list) and result:
                return result[0].get("generated_text", "")
            return str(result)
        except Exception as e:
            logger.error("HuggingFace generate error", error=str(e))
            return f"[HuggingFace error: {e}]"

    def is_available(self) -> bool:
        try:
            resp = httpx.get(self.endpoint)
            return resp.status_code == 200
        except Exception as e:
            logger.warning("HuggingFace availability check failed", error=str(e))
            return False

    def get_info(self) -> Dict[str, Any]:
        return {"model": self.model_name, "endpoint": self.endpoint, "api_token": bool(self.api_token)}