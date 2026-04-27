"""
Bridge di integrazione per DELTA Orchestrator
"""
from typing import Dict, Any, Union
from ..state.schema import DeltaOrchestratorState
from ..graphs.main_graph import MainGraph
import structlog

logger = structlog.get_logger("delta_bridge")

graph = MainGraph()

async def orchestrate_task(task: str, delta_context: Union[dict, DeltaOrchestratorState]) -> dict:
    """Funzione principale di orchestrazione, integrabile da main.py, Flask, Telegram bot, ecc.
    Args:
        task: descrizione del task richiesto
        delta_context: stato attuale (dict o DeltaOrchestratorState)
    Returns:
        dict con risultato finale
    """
    logger.info("orchestrate_task: start", task=task)
    if isinstance(delta_context, DeltaOrchestratorState):
        state = delta_context.dict()
    else:
        state = delta_context
    state["messages"] = state.get("messages", []) + [{"role": "user", "content": task}]
    result = await graph.run(state)
    logger.info("orchestrate_task: end", result=result)
    return result
