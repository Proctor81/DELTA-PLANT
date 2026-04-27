"""
Ollama Adapter per DELTA Ð Orchestrator (prioritario per RPi, lazy loading)
"""
from .base_llm_adapter import BaseLLMAdapter
from typing import Dict, Any, Optional
import asyncio
import httpx
import structlog

logger = structlog.get_logger("ollama_adapter")

class OllamaAdapter(BaseLLMAdapter):
    """Adapter per modelli Ollama locale/remoto."""
    def __init__(self, model_name: str = "llama3.2", endpoint: str = "http://localhost:11434", **kwargs):
        super().__init__(model_name, **kwargs)
        self.endpoint = endpoint
        self._client = None
        self._lazy_loaded = False

    def _lazy_load(self):
        if not self._lazy_loaded:
            self._client = httpx.AsyncClient(base_url=self.endpoint, timeout=60)
            self._lazy_loaded = True
            logger.info("Ollama client lazy loaded", model=self.model_name, endpoint=self.endpoint)

    async def generate(self, prompt: str, context: Optional[Dict] = None) -> str:
        self._lazy_load()
        payload = {"model": self.model_name, "prompt": prompt}
        if context:
            payload["context"] = context
        try:
            response = await self._client.post("/api/generate", json=payload)
            response.raise_for_status()
            result = response.json()
            logger.info("Ollama response", result=result)
            return result.get("response", "")
        except Exception as e:
            logger.error("Ollama generate error", error=str(e))
            return f"[Ollama error: {e}]"

    def is_available(self) -> bool:
        try:
            self._lazy_load()
            resp = asyncio.run(self._client.get("/api/tags"))
            return resp.status_code == 200
        except Exception as e:
            logger.warning("Ollama availability check failed", error=str(e))
            return False

    def get_info(self) -> Dict[str, Any]:
        return {"model": self.model_name, "endpoint": self.endpoint, "lazy_loaded": self._lazy_loaded}
