"""
Schema di stato per DELTA Ð Multi-LLM Agent Orchestrator
"""
from pydantic import BaseModel, Field
from typing import List, Dict, Optional, Annotated
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
from datetime import datetime

class DeltaContext(BaseModel):
    tflite_diagnosis: Optional[Dict] = None
    sensor_data: Optional[Dict] = None
    quantum_risk_score: Optional[float] = None
    expert_rules_fired: List[str] = Field(default_factory=list)
    image_path: Optional[str] = None
    plant_type: Optional[str] = None
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())

class DeltaOrchestratorState(BaseModel):
    messages: Annotated[List[BaseMessage], add_messages] = Field(default_factory=list)
    delta_context: DeltaContext = Field(default_factory=DeltaContext)
    current_model: str = "ollama/llama3.2"
    tool_results: Dict = Field(default_factory=dict)
    confidence: float = 0.0
    iteration_count: int = 0
    max_iterations: int = 5
    errors: List[str] = Field(default_factory=list)
    final_answer: Optional[str] = None

    class Config:
        arbitrary_types_allowed = True
