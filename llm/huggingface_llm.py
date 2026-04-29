"""
DELTA - llm/huggingface_llm.py
Wrapper HuggingFace Inference API per chat intelligente in cloud.
Usa huggingface_hub.InferenceClient (API OpenAI-compatibile).
Seleziona automaticamente il miglior modello disponibile dalla lista di priorità.
"""

import os
import logging
from typing import List, Dict, Optional, Tuple

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
║                                                                      ║
║ Nel frattempo DELTA usa TinyLlama locale come fallback.              ║
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

Stile di risposta:
- Conciso, tecnico ma comprensibile
- Dai priorità a informazioni pratiche e applicabili
- Quando pertinente, cita prodotti fitosanitari o pratiche agronomiche specifiche
- Se la domanda riguarda un'immagine analizzata, commenta il risultato AI e aggiungi considerazioni agronomiche
- Non inventare dati; se non conosci qualcosa, dillo chiaramente

Sei l'interfaccia intelligente di un sistema Raspberry Pi con telecamera e sensori ambientali.
"""

# ─────────────────────────────────────────────────────────────────────────────
# LISTA MODELLI IN ORDINE DI PREFERENZA (migliore per DELTA agronomico IT)
# ─────────────────────────────────────────────────────────────────────────────
HF_MODEL_PRIORITY = [
    "meta-llama/Llama-3.1-8B-Instruct",      # Verificato funzionante — ottimo IT
    "Qwen/Qwen2.5-7B-Instruct",              # Forte multilingue
    "Qwen/Qwen2.5-72B-Instruct",             # Versione grande, alta qualità
    "microsoft/Phi-3.5-mini-instruct",        # Leggero, buone prestazioni
    "Qwen/Qwen2.5-3B-Instruct",              # Fallback leggero
    "HuggingFaceH4/zephyr-7b-beta",          # Fallback conversazione
    "mistralai/Mistral-7B-Instruct-v0.3",    # Potrebbe non essere disponibile
]


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
            "HF_MODEL_NAME", HF_MODEL_PRIORITY[0]
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

    def _probe_model(self, client, model: str) -> bool:
        """Verifica se un modello è raggiungibile con una chiamata di test minima."""
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": "ok"}],
                max_tokens=5,
                temperature=0.1,
            )
            _ = resp.choices[0].message.content
            return True
        except Exception as e:
            logger.debug(f"Modello {model} non disponibile: {e}")
            return False

    def select_best_model(self) -> Optional[str]:
        """
        Prova i modelli in ordine di priorità e restituisce il primo disponibile.
        Memorizza il risultato per evitare probe ripetuti.
        """
        if self._active_model:
            return self._active_model

        if not self.api_token:
            logger.warning("HF_API_TOKEN non configurato — impossibile selezionare modello HF")
            return None

        client = self._get_client()
        # Prima prova il modello configurato
        models_to_try = [self.model_name] + [
            m for m in HF_MODEL_PRIORITY if m != self.model_name
        ]

        for model in models_to_try:
            logger.info(f"Probe modello HF: {model}")
            if self._probe_model(client, model):
                self._active_model = model
                logger.info(f"Modello HF selezionato: {model}")
                return model

        logger.error("Nessun modello HF disponibile — verifica token e connessione")
        return None

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
        if not self.api_token:
            return (
                "⚠️ Token HuggingFace non configurato. "
                "Imposta HF_API_TOKEN nel file .env",
                "none",
            )

        # Seleziona il modello attivo
        model = self._active_model or self.model_name
        if not model:
            return "[DELTA] Nessun modello LLM disponibile.", "none"

        client = self._get_client()

        # Costruisci la sequenza di messaggi
        messages = [
            {"role": "system", "content": system_prompt or DELTA_SYSTEM_PROMPT}
        ]
        if history:
            messages.extend(history)
        messages.append({"role": "user", "content": user_message})

        try:
            resp = client.chat.completions.create(
                model=model,
                messages=messages,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
            )
            answer = resp.choices[0].message.content.strip()
            logger.info(f"HF risposta generata con {model} ({len(answer)} chars)")
            return answer, model

        except Exception as e:
            err_msg = str(e)
            logger.warning(f"Errore HF con modello {model}: {err_msg}")

            # Rileva token scaduto/non valido → mostra istruzioni e abbandona subito
            if "401" in err_msg or "unauthorized" in err_msg.lower():
                logger.warning(_TOKEN_HELP)
                return (
                    "[DELTA] Token HuggingFace non valido. "
                    "Crea un nuovo token su https://huggingface.co/settings/tokens "
                    "(tipo Fine-grained, permesso 'Make calls to Inference Providers') "
                    "e aggiorna HF_API_TOKEN in .env.",
                    "none",
                )

            # Auto-fallback: prova il prossimo modello della lista
            fallback_tried = {model}
            for fallback in HF_MODEL_PRIORITY:
                if fallback in fallback_tried:
                    continue
                fallback_tried.add(fallback)
                try:
                    logger.info(f"Fallback HF → {fallback}")
                    resp = client.chat.completions.create(
                        model=fallback,
                        messages=messages,
                        max_tokens=self.max_tokens,
                        temperature=self.temperature,
                    )
                    answer = resp.choices[0].message.content.strip()
                    self._active_model = fallback  # Aggiorna modello attivo
                    logger.info(f"Fallback HF riuscito con {fallback}")
                    return answer, fallback
                except Exception as fe:
                    logger.debug(f"Fallback {fallback} fallito: {fe}")
                    continue

            return (
                f"[DELTA] Impossibile generare risposta LLM. "
                f"Verifica connessione e token HF. Errore: {err_msg[:100]}",
                "none",
            )

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
        }
