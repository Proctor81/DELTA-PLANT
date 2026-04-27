"""
FastAPI routes per DELTA Orchestrator
"""
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse, JSONResponse
from ..graphs.main_graph import MainGraph
from ..state.schema import DeltaOrchestratorState
import asyncio
import structlog

router = APIRouter()
logger = structlog.get_logger("api.routes")

graph = MainGraph()

@router.post("/orchestrate")
async def orchestrate(request: Request):
    data = await request.json()
    state = DeltaOrchestratorState(**data)
    result = await graph.run(state.dict())
    return JSONResponse(result)

@router.post("/orchestrate/stream")
async def orchestrate_stream(request: Request):
    data = await request.json()
    state = DeltaOrchestratorState(**data)
    async def event_stream():
        yield "data: Avvio orchestrazione\n\n"
        result = await graph.run(state.dict())
        yield f"data: {result}\n\n"
    return StreamingResponse(event_stream(), media_type="text/event-stream")
