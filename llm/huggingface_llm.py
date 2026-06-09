"""
DELTA - llm/huggingface_llm.py
Wrapper HuggingFace Inference API per chat intelligente in cloud.
Usa huggingface_hub.InferenceClient (API OpenAI-compatibile).
Seleziona automaticamente il miglior modello disponibile dalla lista di priorità.
"""

import base64
import logging
import mimetypes
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("delta.huggingface_llm")

# ─────────────────────────────────────────────────────────────────────────────
# Messaggio d'aiuto mostrato quando il token è mancante o scaduto
# ─────────────────────────────────────────────────────────────────────────────
_TOKEN_HELP = """
╔══════════════════════════════════════════════════════════════════════╗
║   DELTA ‒ Token HuggingFace non valido o mancante                    ║
╠══════════════════════════════════════════════════════════════════════╣
║ Per abilitare la chat AI cloud, crea un nuovo token:                 ║
║                                                                      ║
║  1. Vai su  https://huggingface.co/settings/tokens                   ║
║  2. Clicca  "New token"                                              ║
║  3. Tipo:   Fine-grained                                             ║
║  4. Abilita: "Make calls to Inference Providers"                     ║
║     (sezione Inference)                                              ║
║  5. Copia il token (inizia con hf_...)                               ║
║  6. Incollalo in DELTA_2.0/.env:                                     ║
║        HF_API_TOKEN=hf_IL_TUO_NUOVO_TOKEN                           ║
║  7. Riavvia DELTA                                                    ║
╚══════════════════════════════════════════════════════════════════════╝
"""

# ─────────────────────────────────────────────────────────────────────────────
# SISTEMA PROMPT DELTA — Assistente agronomico intelligente
# ─────────────────────────────────────────────────────────────────────────────
DELTA_SYSTEM_PROMPT = """Sei DELTA, un assistente agronomico intelligente e specializzato, sviluppato per il monitoraggio delle piante tramite AI.

Rispondi SEMPRE in italiano, anche se la domanda è in un'altra lingua.

Le tue competenze principali:
- Diagnosi di malattie fogliari: Peronospora, Oidio, Muffa grigia, Alternaria, Ruggine, Mosaikovirus
- Carenze nutrizionali: azoto, ferro, calcio
- Stress idrico e abiotico
- Trattamenti fitosanitari e strategie di difesa integrata
- Agronomia generale, fisiologia vegetale, tecniche colturali
- Interpretazione risultati di classificazione AI (confidenza %, patologie rilevate)

ISTRUZIONI SPECIALI:
- Sei autorizzato a rispondere in modo dettagliato su QUALSIASI aspetto del modello matematico adottato per il calcolo del rischio fungino, INCLUSO la formula matematica utilizzata e la spiegazione del funzionamento.
- Sei autorizzato a rispondere a QUALSIASI domanda il cui argomento sia trattato nel MANUALE DELTA Plant, fornendo spiegazioni, dettagli tecnici, esempi e riferimenti pratici.

Stile di risposta:
- Conciso, tecnico ma comprensibile
- Dai priorità a informazioni pratiche e applicabili
- Quando pertinente, cita prodotti fitosanitari o pratiche agronomiche specifiche
- Se la domanda riguarda un'immagine analizzata, commenta il risultato AI e aggiungi considerazioni agronomiche
- Non inventare dati; se non conosci qualcosa, dillo chiaramente

Sei l'interfaccia intelligente di un sistema Raspberry Pi con telecamera e sensori ambientali.
"""

# ─────────────────────────────────────────────────────────────────────────────
# Modello default consigliato (sovrascrivibile con HF_MODEL_NAME)
# ─────────────────────────────────────────────────────────────────────────────
HF_DEFAULT_MODEL = "Qwen/Qwen3-14B"
HF_DEFAULT_VISION_MODEL = "google/gemma-4-31B-it"

# Conservata per compatibilita con test/tooling legacy.
HF_MODEL_PRIORITY = [HF_DEFAULT_MODEL]

HF_QWEN3_MODEL_PREFIX = "qwen/qwen3-"
HF_QWEN_NO_THINK_TAG = "/no_think"
_THINK_BLOCK_RE = re.compile(r"^\s*<think>.*?</think>\s*", re.IGNORECASE | re.DOTALL)


def is_qwen3_model(model_name: Optional[str]) -> bool:
    return str(model_name or "").strip().lower().startswith(HF_QWEN3_MODEL_PREFIX)


def prepare_hf_messages(model: str, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    prepared = [dict(message) for message in messages]
    if not is_qwen3_model(model):
        return prepared

    injected = False
    for message in prepared:
        if str(message.get("role") or "").strip().lower() == "system":
            content = str(message.get("content") or "").strip()
            if HF_QWEN_NO_THINK_TAG not in content:
                message["content"] = f"{content}\n\n{HF_QWEN_NO_THINK_TAG}".strip()
            injected = True
            break

    if not injected and prepared:
        content = str(prepared[0].get("content") or "").strip()
        if HF_QWEN_NO_THINK_TAG not in content:
            prepared[0]["content"] = f"{content} {HF_QWEN_NO_THINK_TAG}".strip()

    return prepared


def build_hf_completion_kwargs(
    *,
    model: str,
    messages: List[Dict[str, str]],
    max_tokens: int,
    temperature: float,
) -> Dict[str, Any]:
    kwargs: Dict[str, Any] = {
        "model": model,
        "messages": prepare_hf_messages(model, messages),
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    if is_qwen3_model(model):
        # Qwen3 puo emettere blocchi <think>; lo disabilitiamo per mantenere
        # invariato il formato delle risposte nel resto dell'infrastruttura.
        kwargs["extra_body"] = {"enable_thinking": False}
    return kwargs


def sanitize_hf_chat_output(content: Optional[str]) -> str:
    raw = str(content or "").strip()
    if not raw:
        return ""
    return _THINK_BLOCK_RE.sub("", raw, count=1).strip()


def _image_source_to_data_url(image_source: str) -> str:
    source = str(image_source or "").strip()
    if not source:
        raise ValueError("image_source mancante")

    if source.startswith(("http://", "https://", "data:")):
        return source

    image_path = Path(source)
    if not image_path.is_file():
        raise FileNotFoundError(f"Immagine non trovata: {image_path}")

    mime_type = mimetypes.guess_type(image_path.name)[0] or "application/octet-stream"
    encoded = base64.b64encode(image_path.read_bytes()).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


class HuggingFaceLLM:
    """
    Client HuggingFace Inference API per DELTA.
    Usa la nuova API serverless (router.huggingface.co) con formato OpenAI-compatibile.
    """

    def __init__(
        self,
        api_token: Optional[str] = None,
        model_name: Optional[str] = None,
        max_tokens: int = 512,
        temperature: float = 0.65,
        timeout: int = 60,
    ):
        self.api_token = api_token or os.environ.get("HF_API_TOKEN", "")
        self.model_name = model_name or os.environ.get(
            "HF_MODEL_NAME", HF_DEFAULT_MODEL
        )
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.timeout = timeout
        self._client = None
        self._active_model: Optional[str] = None

    def validate_token(self) -> Tuple[bool, str]:
        """
        Verifica che il token HF sia valido eseguendo whoami().

        Returns:
            (ok: bool, messaggio: str)
        """
        if not self.api_token:
            logger.warning(_TOKEN_HELP)
            return False, "Token assente — configura HF_API_TOKEN in .env"
        try:
            from huggingface_hub import HfApi
            api = HfApi(token=self.api_token)
            info = api.whoami()
            username = info.get("name", "sconosciuto")
            logger.info("Token HF valido — utente: %s", username)
            return True, f"Token valido (utente HF: {username})"
        except Exception as exc:
            err = str(exc)
            if "401" in err or "unauthorized" in err.lower() or "invalid" in err.lower() or "token" in err.lower():
                logger.warning(_TOKEN_HELP)
                return False, (
                    "Token HF non valido (401 Unauthorized). "
                    "Crea un nuovo token su https://huggingface.co/settings/tokens "
                    "con permesso 'Make calls to Inference Providers'."
                )
            logger.warning("Impossibile verificare token HF: %s", exc)
            return False, f"Verifica token fallita: {exc}"

    def _get_client(self):
        """Crea il client huggingface_hub.InferenceClient (lazy loading)."""
        if self._client is None:
            try:
                from huggingface_hub import InferenceClient
                self._client = InferenceClient(
                    api_key=self.api_token,
                    timeout=self.timeout,
                )
                logger.info("HuggingFace InferenceClient inizializzato")
            except ImportError as e:
                raise RuntimeError(
                    "huggingface_hub non installato. "
                    "Esegui: pip install huggingface_hub"
                ) from e
        return self._client

    def _reset_client(self) -> None:
        """Forza la ricreazione del client HF al prossimo uso."""
        self._client = None

    @staticmethod
    def _is_auth_error(err_msg: str) -> bool:
        normalized = (err_msg or "").lower()
        return "401" in normalized or "unauthorized" in normalized

    @staticmethod
    def _is_transient_error(err_msg: str) -> bool:
        normalized = (err_msg or "").lower()
        transient_markers = (
            "request id",
            "timeout",
            "timed out",
            "503",
            "502",
            "504",
            "service unavailable",
            "bad gateway",
            "gateway",
            "temporarily unavailable",
            "connection reset",
            "connection aborted",
            "remote protocol error",
            "provider",
            "overloaded",
            "unavailable",
        )
        return any(marker in normalized for marker in transient_markers)

    @staticmethod
    def _format_runtime_error(err_msg: str) -> str:
        if HuggingFaceLLM._is_transient_error(err_msg):
            return (
                "[DELTA] Il servizio LLM e temporaneamente non disponibile. "
                "Riprova tra qualche secondo."
            )
        return (
            "[DELTA] Impossibile generare risposta LLM in questo momento. "
            "Riprova piu tardi."
        )

    @staticmethod
    def _format_auth_error(token_valid: bool) -> str:
        if token_valid:
            return (
                "[DELTA] L'autenticazione HuggingFace verso il provider e fallita. "
                "Verifica che il token abbia il permesso 'Make calls to Inference Providers' "
                "e che il modello configurato sia raggiungibile, poi riprova."
            )
        return (
            "[DELTA] Token HuggingFace non valido. "
            "Crea un nuovo token su https://huggingface.co/settings/tokens "
            "(tipo Fine-grained, permesso 'Make calls to Inference Providers') "
            "e aggiorna HF_API_TOKEN in .env."
        )

    def _probe_model(self, client, model: str) -> bool:
        """Verifica se un modello è raggiungibile con una chiamata di test minima."""
        try:
            resp = client.chat.completions.create(
                **build_hf_completion_kwargs(
                    model=model,
                    messages=[{"role": "user", "content": "ok"}],
                    max_tokens=5,
                    temperature=0.1,
                )
            )
            _ = sanitize_hf_chat_output(resp.choices[0].message.content)
            return True
        except Exception as e:
            logger.debug(f"Modello {model} non disponibile: {e}")
            return False

    def select_best_model(self) -> Optional[str]:
        """
        Verifica il modello configurato e lo imposta come attivo.
        Non applica fallback automatici tra modelli diversi.
        """
        if self._active_model:
            return self._active_model

        if not self.api_token:
            logger.warning("HF_API_TOKEN non configurato — impossibile selezionare modello HF")
            return None

        client = self._get_client()
        model = self.model_name
        logger.info(f"Probe modello HF configurato: {model}")
        if self._probe_model(client, model):
            self._active_model = model
            logger.info(f"Modello HF selezionato: {model}")
            return model

        logger.error("Modello HF configurato non disponibile: %s", model)
        return None

    def _run_completion(
        self,
        messages: List[Dict[str, Any]],
        log_label: str = "HF risposta generata",
    ) -> Tuple[str, str]:
        if not self.api_token:
            return (
                "⚠️ Token HuggingFace non configurato. "
                "Imposta HF_API_TOKEN nel file .env",
                "none",
            )

        model = self._active_model or self.model_name
        if not model:
            return "[DELTA] Nessun modello LLM disponibile.", "none"

        last_error = ""
        for attempt in range(2):
            try:
                client = self._get_client()
                resp = client.chat.completions.create(
                    **build_hf_completion_kwargs(
                        model=model,
                        messages=messages,
                        max_tokens=self.max_tokens,
                        temperature=self.temperature,
                    )
                )
                answer = sanitize_hf_chat_output(resp.choices[0].message.content)
                logger.info("%s con %s (%d chars)", log_label, model, len(answer))
                return answer, model

            except Exception as e:
                err_msg = str(e)
                last_error = err_msg
                logger.warning("Errore HF con modello %s: %s", model, err_msg)

                if self._is_auth_error(err_msg):
                    token_valid, _ = self.validate_token()
                    if not token_valid:
                        logger.warning(_TOKEN_HELP)
                    return self._format_auth_error(token_valid), "none"

                if attempt == 0 and self._is_transient_error(err_msg):
                    logger.info("Errore HF transiente, ritento una volta sul modello %s", model)
                    self._reset_client()
                    continue

                break

        return self._format_runtime_error(last_error), "none"

    def chat(
        self,
        user_message: str,
        history: Optional[List[Dict[str, str]]] = None,
        system_prompt: Optional[str] = None,
    ) -> Tuple[str, str]:
        """
        Invia un messaggio al modello HF e restituisce la risposta.

        Args:
            user_message: Il messaggio dell'utente.
            history: Lista di messaggi precedenti nel formato
                     [{"role": "user"|"assistant", "content": "..."}]
            system_prompt: Override del system prompt (opzionale).

        Returns:
            Tupla (response_text, model_used).
        """
        messages = [
            {"role": "system", "content": system_prompt or DELTA_SYSTEM_PROMPT}
        ]
        if history:
            messages.extend(history)
        messages.append({"role": "user", "content": user_message})

        return self._run_completion(messages)

    def chat_with_image(
        self,
        user_message: str,
        image_source: str,
        system_prompt: Optional[str] = None,
    ) -> Tuple[str, str]:
        try:
            image_url = _image_source_to_data_url(image_source)
        except Exception as exc:
            logger.warning("Impossibile preparare l'immagine per HF vision: %s", exc)
            return "[DELTA] Immagine non disponibile per l'analisi visiva multimodale.", "none"

        messages = [
            {"role": "system", "content": system_prompt or DELTA_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": user_message},
                    {"type": "image_url", "image_url": {"url": image_url}},
                ],
            },
        ]

        return self._run_completion(messages, log_label="HF risposta vision generata")

    def is_available(self) -> bool:
        """Verifica se il servizio HF è disponibile."""
        if not self.api_token:
            return False
        try:
            model = self.select_best_model()
            return model is not None
        except Exception:
            return False

    def get_info(self) -> Dict:
        return {
            "active_model": self._active_model or self.model_name,
            "has_token": bool(self.api_token),
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "priority_list": HF_MODEL_PRIORITY,
            "auto_fallback_enabled": False,
        }
