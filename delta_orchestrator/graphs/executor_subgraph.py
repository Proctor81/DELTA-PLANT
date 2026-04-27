"""
Executor Subgraph per DELTA Orchestrator
"""
from ..nodes.executor_node import ExecutorNode
from typing import Dict, Any

class ExecutorSubgraph:
    """Subgrafo per esecuzione tool/LLM."""
    def __init__(self):
        self.executor_node = ExecutorNode()

    async def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        return await self.executor_node.run(state)
