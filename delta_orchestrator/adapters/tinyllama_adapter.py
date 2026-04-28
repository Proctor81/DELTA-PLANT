"""
TinyLlama Adapter per DELTA Ð Orchestrator
"""
from .base_llm_adapter import BaseLLMAdapter
from typing import Dict, Any, Optional
import subprocess
import structlog

logger = structlog.get_logger("tinyllama_adapter")

class TinyLlamaAdapter(BaseLLMAdapter):
    """Adapter per modello TinyLlama locale via llama_cpp_wrapper."""
    def __init__(self, model_path: str = "models/tinyllama-1.1b-chat-v1.0-q4_K_M.gguf", **kwargs):
        super().__init__(model_path, **kwargs)
        self.model_path = model_path

    async def generate(self, prompt: str, context: Optional[Dict] = None) -> str:
        # Usa il wrapper Python locale
        try:
            from llm.llama_cpp_wrapper import LlamaCppWrapper
            llm = LlamaCppWrapper(self.model_path)
            # TinyLlama non supporta contesto, prompt diretto
            tokens = []
            for token in llm.generate(prompt):
                tokens.append(token)
            response = " ".join(tokens).strip()
            logger.info("TinyLlama response", result=response)
            return response
        except Exception as e:
            logger.error("TinyLlama generate error", error=str(e))
            return f"[TinyLlama error: {e}]"

    def is_available(self) -> bool:
        try:
            from llm.llama_cpp_wrapper import LlamaCppWrapper
            llm = LlamaCppWrapper(self.model_path)
            # Test rapido
            for _ in llm.generate("Ciao"): return True
            return True
        except Exception as e:
            logger.warning("TinyLlama availability check failed", error=str(e))
            return False

    def get_info(self) -> Dict[str, Any]:
        return {"model": self.model_path, "adapter": "TinyLlamaAdapter"}
