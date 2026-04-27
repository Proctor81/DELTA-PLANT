"""
Base LLM Adapter per DELTA Ð Orchestrator
"""
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

class BaseLLMAdapter(ABC):
    """Interfaccia base per tutti gli LLM Adapter."""

    def __init__(self, model_name: str, **kwargs):
        self.model_name = model_name
        self.kwargs = kwargs

    @abstractmethod
    async def generate(self, prompt: str, context: Optional[Dict] = None) -> str:
        """Genera una risposta dal modello LLM."""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Verifica se il modello è disponibile."""
        pass

    @abstractmethod
    def get_info(self) -> Dict[str, Any]:
        """Restituisce informazioni sul modello."""
        pass
