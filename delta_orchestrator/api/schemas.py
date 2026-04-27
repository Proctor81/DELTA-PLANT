"""
Schemi FastAPI per DELTA Orchestrator
"""
from pydantic import BaseModel
from typing import Dict, Any

class OrchestrateRequest(BaseModel):
    state: Dict[str, Any]

class OrchestrateResponse(BaseModel):
    result: Dict[str, Any]
