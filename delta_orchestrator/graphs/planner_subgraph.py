"""
Planner Subgraph per DELTA Orchestrator
"""
from ..nodes.planner_node import PlannerNode
from typing import Dict, Any

class PlannerSubgraph:
    """Subgrafo per decomposizione task."""
    def __init__(self):
        self.planner_node = PlannerNode()

    async def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        return await self.planner_node.run(state)
