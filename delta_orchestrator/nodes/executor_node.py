"""
Executor Node: chiamata tool e LLM
"""
from .base_node import BaseNode
from typing import Dict, Any
import structlog
from ..tools.registry import registry

logger = structlog.get_logger("executor_node")

class ExecutorNode(BaseNode):
    """Nodo executor: esegue tool e LLM."""
    def __init__(self):
        super().__init__("executor")

    async def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        logger.info("ExecutorNode: esecuzione tool/LLM", state=state)
        # Esempio: chiama delta_context_tool
        tool = registry.get("delta_context_tool")
        state["tool_results"] = tool(state.get("delta_context", {}))
        return state
