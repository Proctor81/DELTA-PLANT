"""
Planner Node: decomposizione task
"""
from .base_node import BaseNode
from typing import Dict, Any
import structlog

logger = structlog.get_logger("planner_node")

class PlannerNode(BaseNode):
    """Nodo planner: decomposizione task in subtask con DeltaContext."""
    def __init__(self):
        super().__init__("planner")

    async def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        logger.info("PlannerNode: decomposizione task", state=state)
        # TODO: decomposizione task (stub)
        state["plan"] = ["Esegui diagnosi", "Recupera dati sensori"]
        return state
