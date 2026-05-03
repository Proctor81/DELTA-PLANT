"""
DELTA - chat/chat_engine.py
Chat Engine intelligente con HuggingFace Inference API come LLM primario.
Fallback automatico a TinyLlama locale se HF non disponibile.
"""
import os
import logging
from pathlib import Path
from memory.conversation_memory import ConversationMemory
from llm.huggingface_llm import HuggingFaceLLM, DELTA_SYSTEM_PROMPT

logger = logging.getLogger("delta.chat_engine")

# Massimo messaggi di storia da includere nel contesto
MAX_HISTORY_TURNS = 6


class ChatEngine:
    """
    Engine di chat per DELTA.
    Usa HuggingFace Inference API (cloud) come LLM primario e
    TinyLlama locale come fallback offline.
    """

    def __init__(self, model_path: str = ""):
        self.model_path = model_path
        self.memory = ConversationMemory()
        # LLM primario: HuggingFace cloud
        self._hf_llm = HuggingFaceLLM(
            api_token=os.environ.get("HF_API_TOKEN", ""),
            model_name=os.environ.get("HF_MODEL_NAME", "mistralai/Mistral-7B-Instruct-v0.3"),
            max_tokens=512,
            temperature=0.65,
            timeout=15,
        )
        # Evita chiamate di rete sincrone in __init__: il bot Telegram deve
        # potersi istanziare subito e tentare HF solo quando arriva un messaggio.
        self._hf_available = bool(self._hf_llm.api_token)
        # LLM fallback locale (TinyLlama via llama.cpp)
        self._local_llm = None  # inizializzato lazy

    def _check_hf_token(self) -> bool:
        """Valida il token HF all'avvio. Restituisce True se disponibile."""
        ok, msg = self._hf_llm.validate_token()
        if ok:
            logger.info("HuggingFace LLM pronto: %s", msg)
        else:
            logger.warning("HuggingFace LLM non disponibile: %s", msg)
        return ok

    def _get_local_llm(self):
        """Inizializza TinyLlama solo quando necessario (lazy)."""
        if self._local_llm is None:
            model_path = Path(self.model_path) if self.model_path else None
            llama_bin = Path("./llama.cpp/build/bin/llama-cli")
            if not model_path or not model_path.is_file():
                logger.warning("TinyLlama non disponibile: modello mancante (%s)", self.model_path)
                return None
            if not llama_bin.is_file():
                logger.warning("TinyLlama non disponibile: binario assente (%s)", llama_bin)
                return None
            try:
                from llm.llama_cpp_wrapper import LlamaCppWrapper
                self._local_llm = LlamaCppWrapper(self.model_path)
                logger.info("TinyLlama locale inizializzato come fallback")
            except Exception as e:
                logger.warning(f"TinyLlama non disponibile: {e}")
        return self._local_llm

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

    def chat(self, user_id: str, user_input: str) -> str:
        """
        Elabora un messaggio utente e restituisce la risposta DELTA.

        Flusso:
        1. Recupera storia conversazionale utente
        2. Tenta risposta via HuggingFace cloud
        3. Se fallisce, usa TinyLlama locale
        4. Salva turno in memoria
        """
        history = self.memory.get_history(user_id)

        # ── Tentativo 1: HuggingFace cloud ──────────────────────────────────
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
        else:
            logger.info("HuggingFace non disponibile — uso TinyLlama locale")

        # ── Fallback 2: TinyLlama locale ─────────────────────────────────────
        logger.info(f"Uso TinyLlama locale come fallback per user {user_id}")
        try:
            local_llm = self._get_local_llm()
            if local_llm:
                prompt = self._format_local_prompt(history, user_input)
                tokens = []
                for token in local_llm.generate(prompt):
                    tokens.append(token)
                response = " ".join(tokens).strip()
                if response and not response.startswith("[ERRORE llama.cpp]"):
                    self.memory.append(user_id, user_input, response)
                    return response
                if response:
                    logger.warning("TinyLlama fallback non riuscito: %s", response)
        except Exception as e:
            logger.error(f"Eccezione TinyLlama: {e}")

        # ── Fallback finale ───────────────────────────────────────────────────
        fallback_response = (
            "Mi dispiace, al momento non riesco a generare una risposta. "
            "Verifica la connessione e il token HuggingFace nel file .env"
        )
        self.memory.append(user_id, user_input, fallback_response)
        return fallback_response

    def _format_local_prompt(self, history: list, user_input: str) -> str:
        """Formatta il prompt per TinyLlama nel formato chat."""
        system = "Sei DELTA, un assistente agronomico. Rispondi in italiano."
        recent = history[-(MAX_HISTORY_TURNS * 2):]
        ctx = "\n".join(recent)
        return f"{system}\n{ctx}\nUtente: {user_input}\nDELTA:"

    def reset(self, user_id: str) -> None:
        """Cancella la storia conversazionale di un utente."""
        self.memory.reset(user_id)

    def get_status(self) -> dict:
        """Restituisce lo stato corrente del chat engine."""
        return {
            "hf_token_present": bool(os.environ.get("HF_API_TOKEN")),
            "hf_token_valid": self._hf_available,
            "hf_active_model": self._hf_llm._active_model or self._hf_llm.model_name,
            "local_model_path": self.model_path,
            "local_llm_loaded": self._local_llm is not None,
        }
