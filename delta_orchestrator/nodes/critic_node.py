"""
Critic Node: valutazione confidenza
"""
from .base_node import BaseNode
from typing import Dict, Any
import structlog

logger = structlog.get_logger("critic_node")

class CriticNode(BaseNode):
    """Nodo critic: valuta la confidenza della risposta."""
    def __init__(self):
        super().__init__("critic")

    async def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        logger.info("CriticNode: valutazione confidenza", state=state)
        # Se c'è già una risposta finale, considera la confidenza al massimo
        if state.get("final_answer"):
            state["confidence"] = 1.0
            return state
        # TODO: calcolo reale della confidenza
        state["confidence"] = state.get("tool_results", {}).get("tflite_diagnosis", {}).get("confidence", 0.0)
        return state
