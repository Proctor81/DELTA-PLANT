"""
Together Adapter per DELTA Ð Orchestrator
"""
from .base_llm_adapter import BaseLLMAdapter
from typing import Dict, Any, Optional
import structlog
import httpx

logger = structlog.get_logger("together_adapter")

class TogetherAdapter(BaseLLMAdapter):
    """Adapter per Together API (LLM as a Service)."""
    def __init__(self, model_name: str, api_key: Optional[str] = None, endpoint: Optional[str] = None, **kwargs):
        super().__init__(model_name, **kwargs)
        self.api_key = api_key
        self.endpoint = endpoint or "https://api.together.xyz/v1/completions"
        self._client = httpx.AsyncClient(timeout=60)

    async def generate(self, prompt: str, context: Optional[Dict] = None) -> str:
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        payload = {"model": self.model_name, "prompt": prompt}
        try:
            response = await self._client.post(self.endpoint, headers=headers, json=payload)
            response.raise_for_status()
            result = response.json()
            logger.info("Together response", result=result)
            return result.get("choices", [{}])[0].get("text", "")
        except Exception as e:
            logger.error("Together generate error", error=str(e))
            return f"[Together error: {e}]"

    def is_available(self) -> bool:
        try:
            resp = httpx.get(self.endpoint)
            return resp.status_code == 200
        except Exception as e:
            logger.warning("Together availability check failed", error=str(e))
            return False

    def get_info(self) -> Dict[str, Any]:
        return {"model": self.model_name, "endpoint": self.endpoint, "api_key": bool(self.api_key)}}