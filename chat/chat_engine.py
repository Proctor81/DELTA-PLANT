"""
DELTA - chat/chat_engine.py
Chat Engine intelligente con HuggingFace Inference API come LLM primario.
"""
import os
import logging
from memory.conversation_memory import ConversationMemory
from llm.huggingface_llm import HuggingFaceLLM, DELTA_SYSTEM_PROMPT

logger = logging.getLogger("delta.chat_engine")

# Massimo messaggi di storia da includere nel contesto
MAX_HISTORY_TURNS = 6


class ChatEngine:
    """
    Engine di chat per DELTA.
    Usa HuggingFace Inference API (cloud) come unico backend LLM.
    """

    def __init__(self, model_path: str = ""):
        # model_path mantenuto per compatibilita retroattiva ma non usato.
        _ = model_path
        self.memory = ConversationMemory()
        # Backend LLM unico: HuggingFace cloud
        self._hf_llm = HuggingFaceLLM(
            api_token=os.environ.get("HF_API_TOKEN", ""),
            model_name=os.environ.get("HF_MODEL_NAME", "meta-llama/Llama-3.1-8B-Instruct"),
            max_tokens=512,
            temperature=0.65,
            timeout=15,
        )
        # Evita chiamate di rete sincrone in __init__: il bot Telegram deve
        # potersi istanziare subito e tentare HF solo quando arriva un messaggio.
        self._hf_available = bool(self._hf_llm.api_token)
    def _check_hf_token(self) -> bool:
        """Valida il token HF all'avvio. Restituisce True se disponibile."""
        ok, msg = self._hf_llm.validate_token()
        if ok:
            logger.info("HuggingFace LLM pronto: %s", msg)
        else:
            logger.warning("HuggingFace LLM non disponibile: %s", msg)
        return ok

    def _build_hf_history(self, raw_history: list) -> list:
        """
        Converte la storia grezza (lista di stringhe) nel formato
        messages OpenAI usato da HuggingFace InferenceClient.
        Mantiene solo gli ultimi MAX_HISTORY_TURNS scambi.
        """
        messages = []
        turns = []
        for line in raw_history:
            if line.startswith("Utente: "):
                turns.append({"role": "user", "content": line[len("Utente: "):]})
            elif line.startswith("DELTA: "):
                turns.append({"role": "assistant", "content": line[len("DELTA: "):]})
        # Tronca alla finestra di contesto configurata
        return turns[-(MAX_HISTORY_TURNS * 2):]

    def chat_internal(self, prompt: str) -> str:
        """
        Chiamata stateless all'LLM: nessuna memoria letta o scritta.
        Usata per chiamate interne (generazione domande, classificazioni binarie)
        dove salvare i turni in ConversationMemory causerebbe contaminazione
        del contesto conversazionale reale dell'utente.
        """
        if not self._hf_available:
            return ""
        try:
            response, _ = self._hf_llm.chat(
                user_message=prompt,
                history=[],
                system_prompt=DELTA_SYSTEM_PROMPT,
            )
            return response or ""
        except Exception as exc:
            logger.warning("chat_internal error: %s", exc)
            return ""

    def chat(self, user_id: str, user_input: str) -> str:
        """
        Elabora un messaggio utente e restituisce la risposta DELTA.

        Flusso:
        1. Recupera storia conversazionale utente
        2. Tenta risposta via HuggingFace cloud
        3. Salva turno in memoria
        """
        history = self.memory.get_history(user_id)

        # ── Backend unico: HuggingFace cloud ─────────────────────────────────
        if self._hf_available:
            try:
                hf_history = self._build_hf_history(history)
                response, model_used = self._hf_llm.chat(
                    user_message=user_input,
                    history=hf_history,
                    system_prompt=DELTA_SYSTEM_PROMPT,
                )
                if response and not response.startswith("[DELTA] Impossibile"):
                    logger.info(f"Risposta HF [{model_used}] per user {user_id}")
                    self.memory.append(user_id, user_input, response)
                    return response
                else:
                    logger.warning(f"HF ha restituito errore: {response[:80]}")
            except Exception as e:
                logger.warning(f"Eccezione HF chat: {e}")
                # Se errore 401, disabilita HF per questa sessione
                if "401" in str(e) or "unauthorized" in str(e).lower():
                    self._hf_available = False

        # ── Errore finale ─────────────────────────────────────────────────────
        fallback_response = (
            "Mi dispiace, al momento il backend LLM non e disponibile. "
            "Verifica connessione, HF_API_TOKEN e HF_MODEL_NAME nel file .env"
        )
        self.memory.append(user_id, user_input, fallback_response)
        return fallback_response

    def reset(self, user_id: str) -> None:
        """Cancella la storia conversazionale di un utente."""
        self.memory.reset(user_id)

    def get_status(self) -> dict:
        """Restituisce lo stato corrente del chat engine."""
        return {
            "hf_token_present": bool(os.environ.get("HF_API_TOKEN")),
            "hf_token_valid": self._hf_available,
            "hf_active_model": self._hf_llm._active_model or self._hf_llm.model_name,
        }
