"""
Configurazione per DELTA Ð Multi-LLM Agent Orchestrator
"""
from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Optional
import platform


from pydantic import ConfigDict

class OrchestratorSettings(BaseSettings):
    """Impostazioni di configurazione per il modulo Orchestrator."""
    ollama_endpoint: str = Field("http://localhost:11434", description="Endpoint Ollama locale o remoto")
    mode: str = Field("edge", description="Modalità di esecuzione: 'edge' (Raspberry Pi) o 'cloud'")
    sqlite_path: str = Field("/home/proctor81/Desktop/DELTA 2.0/data/delta_orchestrator.db", description="Percorso file SQLite per checkpointing")
    redis_url: Optional[str] = Field(None, description="URL Redis opzionale per checkpointing distribuito")
    confidence_threshold: float = Field(0.85, description="Soglia di confidenza per il critic loop")
    lazy_loading: bool = Field(default_factory=lambda: platform.machine() in ["armv7l", "aarch64"], description="Abilita lazy loading su Raspberry Pi")
    log_level: str = Field("INFO", description="Livello di logging (DEBUG, INFO, WARNING, ERROR)")
    model_config = ConfigDict(extra="ignore", env_prefix="DELTA_ORCH_", env_file=".env")

settings = OrchestratorSettings()
