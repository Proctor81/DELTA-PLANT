"""
Executor Node: chiamata tool e LLM
"""
from .base_node import BaseNode
from typing import Dict, Any
import structlog
from ..tools.registry import registry
from delta_orchestrator.adapters.ollama_adapter import OllamaAdapter
from delta_orchestrator.adapters.huggingface_adapter import HuggingFaceAdapter
from delta_orchestrator.adapters.tinyllama_adapter import TinyLlamaAdapter

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
        # Usa TinyLlama LLM locale come principale, fallback su Ollama e HuggingFace
        user_message = None
        if isinstance(state.get("messages"), list) and state["messages"]:
            user_message = state["messages"][-1].get("content")
        if user_message:
            llm_response = None
            try:
                tinyllama = TinyLlamaAdapter()
                llm_response = await tinyllama.generate(user_message)
                if llm_response and not llm_response.startswith("[TinyLlama error"):
                    state["final_answer"] = llm_response.strip()
                else:
                    raise Exception("TinyLlama non disponibile")
            except Exception as e:
                logger.warning("TinyLlama non disponibile, uso Ollama", error=str(e))
                import os
                ollama_endpoint = os.environ.get("OLLAMA_ENDPOINT", "http://localhost:11434")
                ollama = OllamaAdapter(endpoint=ollama_endpoint)
                try:
                    llm_response = await ollama.generate(user_message)
                    if llm_response and not llm_response.startswith("[Ollama error"):
                        state["final_answer"] = llm_response.strip()
                    else:
                        raise Exception("Ollama non disponibile")
                except Exception as e2:
                    logger.warning("Ollama non disponibile, uso HuggingFace", error=str(e2))
                    hf_token = os.environ.get("HF_API_TOKEN")
                    hf_models = [
                        "openai/gpt-oss-120b:fastest"
                    ]
                    for hf_model in hf_models:
                        hf_adapter = HuggingFaceAdapter(model_name=hf_model, api_token=hf_token)
                        try:
                            llm_response = await hf_adapter.generate(user_message)
                            if llm_response and not str(llm_response).lower().startswith("[huggingface error"):
                                state["final_answer"] = llm_response.strip()
                                break
                        except Exception as e3:
                            logger.warning(f"Errore HuggingFace LLM con modello {hf_model}", error=str(e3))
                            continue
                    else:
                        state["final_answer"] = "[Errore LLM: impossibile generare una risposta]"
        else:
            diagnosis = state["tool_results"].get("tflite_diagnosis", {})
            disease = diagnosis.get("disease", "Sconosciuto")
            confidence = diagnosis.get("confidence", 0.0)
            state["final_answer"] = f"Risultato diagnosi: {disease} (confidenza: {confidence:.2%})"
        logger.info("ExecutorNode: final_answer valorizzato", final_answer=state["final_answer"])
        return state
