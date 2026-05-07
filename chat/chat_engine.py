"""
DELTA - chat/chat_engine.py
Chat Engine intelligente con HuggingFace Inference API come LLM primario.
"""
import os
import logging
import re
from pathlib import Path
from memory.conversation_memory import ConversationMemory
from llm.huggingface_llm import HuggingFaceLLM, DELTA_SYSTEM_PROMPT

logger = logging.getLogger("delta.chat_engine")

# Massimo messaggi di storia da includere nel contesto
MAX_HISTORY_TURNS = 6
DIAGNOSIS_TURN_MARKER = "Ho chiesto una diagnosi della pianta."
MAX_DIAGNOSIS_CONTEXT_CHARS = 5000

DIAGNOSIS_FOLLOWUP_KEYWORDS = (
    "approfond",
    "spiega",
    "dettagl",
    "chiar",
    "svilupp",
    "comment",
    "interpreta",
    "diagnosi",
    "risultato",
    "referto",
    "rischio",
    "qrs",
    "raccomand",
    "anomali",
    "sensori",
    "sensore",
    "classe ai",
    "classe",
    "pianta",
    "malatti",
    "patologi",
    "punto",
    "elemento",
    "sezione",
    "cosa significa",
    "perche",
    "perché",
)

DIAGNOSIS_FOLLOWUP_REFERENTS = (
    "questo",
    "questa",
    "questi",
    "queste",
    "quello",
    "quella",
    "essa",
)

_ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


def _load_project_env_if_needed() -> None:
    """Carica .env anche quando ChatEngine viene istanziato fuori da main.py."""
    if not _ENV_FILE.is_file():
        return
    if os.environ.get("HF_API_TOKEN") and os.environ.get("HF_MODEL_NAME"):
        return

    try:
        for line in _ENV_FILE.read_text(encoding="utf-8").splitlines():
            raw = line.strip()
            if not raw or raw.startswith("#") or "=" not in raw:
                continue
            key, value = raw.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))
    except OSError as exc:
        logger.warning("Impossibile leggere %s: %s", _ENV_FILE, exc)


class ChatEngine:
    """
    Engine di chat per DELTA.
    Usa HuggingFace Inference API (cloud) come unico backend LLM.
    """

    def __init__(self, model_path: str = ""):
        # model_path mantenuto per compatibilita retroattiva ma non usato.
        _ = model_path
        _load_project_env_if_needed()
        self.memory = ConversationMemory()
        # Backend LLM unico: HuggingFace cloud
        self._hf_llm = HuggingFaceLLM(
            api_token=os.environ.get("HF_API_TOKEN", ""),
            model_name=os.environ.get("HF_MODEL_NAME", "meta-llama/Llama-3.1-8B-Instruct"),
            max_tokens=int(os.environ.get("HF_MAX_TOKENS", "1500")),
            temperature=0.65,
            timeout=int(os.environ.get("HF_TIMEOUT", "60")),
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

    @staticmethod
    def _normalize_text(text: str) -> str:
        return re.sub(r"\s+", " ", (text or "").strip().lower())

    def _extract_latest_diagnosis_context(self, raw_history: list) -> str:
        """Estrae l'ultima diagnosi salvata in memoria come contesto esplicito."""
        for idx in range(len(raw_history) - 1, -1, -1):
            line = raw_history[idx]
            if not line.startswith("Utente: "):
                continue
            content = line[len("Utente: "):]
            if DIAGNOSIS_TURN_MARKER not in content:
                continue

            parts = [content]
            if idx + 1 < len(raw_history) and raw_history[idx + 1].startswith("DELTA: "):
                parts.append("Risposta diagnostica DELTA:\n" + raw_history[idx + 1][len("DELTA: "):])

            diagnosis_context = "\n\n".join(parts).strip()
            if len(diagnosis_context) > MAX_DIAGNOSIS_CONTEXT_CHARS:
                diagnosis_context = diagnosis_context[:MAX_DIAGNOSIS_CONTEXT_CHARS].rstrip() + "..."
            return diagnosis_context
        return ""

    def _looks_like_diagnosis_followup(self, user_input: str, raw_history: list) -> bool:
        """Rileva richieste che devono essere ancorate alla diagnosi recente."""
        if not raw_history:
            return False

        normalized = self._normalize_text(user_input)
        if not normalized:
            return False

        if any(keyword in normalized for keyword in DIAGNOSIS_FOLLOWUP_KEYWORDS):
            return True

        words = normalized.split()
        if len(words) <= 12 and any(ref in words for ref in DIAGNOSIS_FOLLOWUP_REFERENTS):
            return True

        return False

    def _prepare_turn_prompt(self, user_input: str, raw_history: list) -> tuple[str, str]:
        """Prepara il prompt del turno, ancorando esplicitamente gli approfondimenti alla diagnosi."""
        diagnosis_context = self._extract_latest_diagnosis_context(raw_history)
        if not diagnosis_context or not self._looks_like_diagnosis_followup(user_input, raw_history):
            return user_input, DELTA_SYSTEM_PROMPT

        anchored_system_prompt = (
            DELTA_SYSTEM_PROMPT
            + "\n\nGestione del contesto diagnostico:\n"
            "- Se nella cronologia è presente una diagnosi DELTA recente e l'utente fa una richiesta di follow-up, "
            "devi usare quella diagnosi come contesto tecnico principale.\n"
            "- Se l'utente chiede di approfondire, chiarire, spiegare un punto, il rischio, le raccomandazioni, i sensori, "
            "le anomalie o il nome della pianta, riferisciti alla diagnosi più recente senza cambiare argomento.\n"
            "- Se il nome della pianta è presente nella diagnosi recente, dichiaralo esplicitamente.\n"
            "- Non inventare elementi mancanti: usa solo quanto presente nella diagnosi recente e nella richiesta attuale."
        )
        anchored_user_input = (
            "Usa la diagnosi DELTA recente seguente come riferimento principale per rispondere. "
            "Se la richiesta è ellittica o deittica, interpretala come riferita a questa diagnosi.\n\n"
            f"DIAGNOSI DELTA RECENTE:\n{diagnosis_context}\n\n"
            f"RICHIESTA ATTUALE DELL'UTENTE:\n{user_input}"
        )
        return anchored_user_input, anchored_system_prompt

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
        llm_user_input, system_prompt = self._prepare_turn_prompt(user_input, history)

        # ── Backend unico: HuggingFace cloud ─────────────────────────────────
        if self._hf_available:
            try:
                hf_history = self._build_hf_history(history)
                response, model_used = self._hf_llm.chat(
                    user_message=llm_user_input,
                    history=hf_history,
                    system_prompt=system_prompt,
                )
                # Filtra risposte di errore: non salvarle in memoria per non
                # inquinare la storia conversazionale con messaggi di servizio.
                _is_error = not response or response.startswith("[DELTA]")
                if not _is_error:
                    logger.info(f"Risposta HF [{model_used}] per user {user_id}")
                    self.memory.append(user_id, user_input, response)
                    return response
                else:
                    logger.warning(f"HF ha restituito errore/no-response: {response[:80]}")
                    # Token non valido → disabilita per questa sessione
                    if response and ("Token" in response or "401" in response or "non valido" in response.lower()):
                        self._hf_available = False
                    return response
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
        return fallback_response

    def remember_turn(self, user_id: str, user_input: str, response: str) -> None:
        """Salva esplicitamente un turno conversazionale gia generato."""
        self.memory.append(user_id, user_input, response)

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
