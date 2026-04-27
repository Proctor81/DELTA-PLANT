"""
Nodo base per DELTA Orchestrator
"""
from abc import ABC, abstractmethod
from typing import Any, Dict
import structlog

logger = structlog.get_logger("base_node")

class BaseNode(ABC):
    """Classe base per tutti i nodi del grafo."""
    def __init__(self, name: str):
        self.name = name

    @abstractmethod
    async def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Esegue la logica del nodo."""
        pass
