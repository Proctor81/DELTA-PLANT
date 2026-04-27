"""
Router Node: selezione modello LLM
"""
from .base_node import BaseNode
from typing import Dict, Any
import structlog

logger = structlog.get_logger("router_node")

class RouterNode(BaseNode):
    """Nodo di routing per selezione modello LLM."""
    def __init__(self):
        super().__init__("router")

    async def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        logger.info("RouterNode: selezione modello", state=state)
        # TODO: logica di selezione modello (es. in base a task, contesto, preferenze)
        state["current_model"] = state.get("current_model", "ollama/llama3.2")
        return state
