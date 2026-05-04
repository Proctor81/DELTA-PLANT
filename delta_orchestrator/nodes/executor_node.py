"""
Executor Node: chiamata tool e LLM
Priorita LLM: 1) HuggingFace cloud  2) Ollama locale
"""
from .base_node import BaseNode
from typing import Dict, Any
import os
import structlog
from ..tools.registry import registry
from delta_orchestrator.adapters.huggingface_adapter import HuggingFaceAdapter
from delta_orchestrator.adapters.ollama_adapter import OllamaAdapter

logger = structlog.get_logger("executor_node")


class ExecutorNode(BaseNode):
    """Nodo executor: esegue tool e LLM con priorita HuggingFace -> Ollama."""

    def __init__(self):
        super().__init__("executor")

    async def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        logger.info("ExecutorNode: esecuzione tool/LLM", state=state)

        # Esegui tool di contesto delta
        tool = registry.get("delta_context_tool")
        state["tool_results"] = tool(state.get("delta_context", {}))

        user_message = None
        if isinstance(state.get("messages"), list) and state["messages"]:
            user_message = state["messages"][-1].get("content")

        if not user_message:
            # Nessun messaggio utente: restituisci solo la diagnosi
            diagnosis = state["tool_results"].get("tflite_diagnosis", {})
            disease = diagnosis.get("disease", "Sconosciuto")
            confidence = diagnosis.get("confidence", 0.0)
            state["final_answer"] = (
                f"Risultato diagnosi: {disease} (confidenza: {confidence:.2%})"
            )
            logger.info("ExecutorNode: risposta diagnosi diretta", final_answer=state["final_answer"])
            return state

        llm_response = None

        # ── PRIORITA 1: HuggingFace cloud ─────────────────────────────────
        hf_token = os.environ.get("HF_API_TOKEN", "")
        if hf_token:
            hf_model = os.environ.get("HF_MODEL_NAME", "meta-llama/Llama-3.1-8B-Instruct")
            hf_adapter = HuggingFaceAdapter(model_name=hf_model, api_token=hf_token)
            try:
                llm_response = await hf_adapter.generate(user_message)
                if llm_response and not str(llm_response).startswith("[HuggingFace error"):
                    state["final_answer"] = llm_response.strip()
                    logger.info(
                        "ExecutorNode: risposta HuggingFace OK",
                        model=hf_adapter._active_model or hf_model,
                    )
                    return state
                else:
                    logger.warning(
                        "HuggingFace non ha prodotto risposta valida",
                        response=str(llm_response)[:80],
                    )
            except Exception as e:
                logger.warning("HuggingFace non disponibile", error=str(e))
        else:
            logger.info("HF_API_TOKEN non presente, salto HuggingFace")

        # ── PRIORITA 2: Ollama locale ──────────────────────────────────────
        ollama_endpoint = os.environ.get("OLLAMA_ENDPOINT", "http://localhost:11434")
        ollama = OllamaAdapter(endpoint=ollama_endpoint)
        try:
            llm_response = await ollama.generate(user_message)
            if llm_response and not llm_response.startswith("[Ollama error"):
                state["final_answer"] = llm_response.strip()
                logger.info("ExecutorNode: risposta Ollama OK")
                return state
        except Exception as e:
            logger.warning("Ollama non disponibile", error=str(e))

        # ── Fallback finale ────────────────────────────────────────────────
        state["final_answer"] = (
            "[DELTA] Nessun LLM disponibile. "
            "Verifica HF_API_TOKEN nel file .env o avvia Ollama."
        )
        logger.error("ExecutorNode: tutti gli LLM falliti")
        return state
