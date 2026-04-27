"""
Main Graph per DELTA Orchestrator (LangGraph style)
"""
from ..nodes.router_node import RouterNode
from ..graphs.planner_subgraph import PlannerSubgraph
from ..graphs.executor_subgraph import ExecutorSubgraph
from ..graphs.critic_loop import CriticLoop
from ..state.schema import DeltaOrchestratorState
from ..config.settings import settings
from typing import Dict, Any
import structlog
import asyncio

logger = structlog.get_logger("main_graph")

class MainGraph:
    """Grafo principale orchestrator (LangGraph style)."""
    def __init__(self):
        self.router_node = RouterNode()
        self.planner_subgraph = PlannerSubgraph()
        self.executor_subgraph = ExecutorSubgraph()
        self.critic_loop = CriticLoop(threshold=settings.confidence_threshold, max_iter=settings.max_iterations if hasattr(settings, 'max_iterations') else 5)

    async def run(self, state: Dict[str, Any] = None) -> Dict[str, Any]:
        if state is None:
            state = DeltaOrchestratorState().dict()
        logger.info("MainGraph: start", state=state)
        state = await self.router_node.run(state)
        state = await self.planner_subgraph.run(state)
        state = await self.executor_subgraph.run(state)
        state = await self.critic_loop.run(state)
        logger.info("MainGraph: end", state=state)
        return state
