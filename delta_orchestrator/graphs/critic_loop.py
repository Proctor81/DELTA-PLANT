"""
Critic Loop con edge condizionale (confidence)
"""
from ..nodes.critic_node import CriticNode
from ..graphs.executor_subgraph import ExecutorSubgraph
from typing import Dict, Any

class CriticLoop:
    """Loop critic con edge condizionale su confidence."""
    def __init__(self, threshold: float = 0.85, max_iter: int = 5):
        self.critic_node = CriticNode()
        self.executor_subgraph = ExecutorSubgraph()
        self.threshold = threshold
        self.max_iter = max_iter

    async def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        iteration = 0
        while iteration < self.max_iter:
            state = await self.critic_node.run(state)
            if state.get("confidence", 0.0) >= self.threshold:
                break
            state = await self.executor_subgraph.run(state)
            iteration += 1
            state["iteration_count"] = iteration
        return state
