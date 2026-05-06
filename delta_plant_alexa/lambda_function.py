"""Entry point AWS Lambda per DELTA Plant Alexa Custom Skill.

Responsabilita principali:
- verifica obbligatoria dell'Application ID Alexa (skill ID)
- registrazione handler in ordine di priorita sicuro
- configurazione logging sicura (nessun dato sensibile al livello INFO)
- gestione errori lambda_handler senza leakage di internals

Variabili ambiente attese (Lambda Console / Secrets Manager):
  DELTA_ALEXA_SKILL_ID       - Application ID della skill (obbligatorio in produzione)
  DELTA_ALEXA_TIMEOUT_SEC    - timeout logico verso orchestrator (default 8)
  DELTA_ALEXA_MAX_INPUT      - caratteri massimi input utente (default 550)
  DELTA_ALEXA_MAX_REQ_SESSION - richieste massime per sessione (default 18)
  DELTA_ALEXA_ORCHESTRATOR_HTTP_URL - URL fallback HTTP orchestrator (opzionale)
  HF_API_TOKEN               - token HuggingFace (per backend LLM)
  HF_MODEL_NAME              - nome modello HuggingFace (opzionale)
"""

from __future__ import annotations

import logging
import os

from ask_sdk_core.skill_builder import SkillBuilder
from ask_sdk_core.dispatch_components import AbstractRequestInterceptor, AbstractResponseInterceptor
from ask_sdk_core.handler_input import HandlerInput
from ask_sdk_model import Response

from delta_plant_alexa.handlers.launch_handler import LaunchRequestHandler
from delta_plant_alexa.handlers.chat_handler import (
    ChatIntentHandler,
    CancelAndStopIntentHandler,
    GenericExceptionHandler,
)
from delta_plant_alexa.handlers.language_handler import LanguageSwitchHandler
from delta_plant_alexa.handlers.fallback_handler import FallbackIntentHandler
from delta_plant_alexa.handlers.help_handler import HelpIntentHandler
from delta_plant_alexa.handlers.session_ended_handler import SessionEndedRequestHandler
from delta_plant_alexa.config import SECURITY_CONFIG


# ─────────────────────────────────────────────────────────────────────────────
# Logging: livello INFO in produzione, DEBUG solo se esplicitamente abilitato.
# Non loggare MAI dati sensibili a INFO o superiore.
# ─────────────────────────────────────────────────────────────────────────────
_log_level_raw = os.getenv("DELTA_LOG_LEVEL", "INFO").upper()
_log_level = getattr(logging, _log_level_raw, logging.INFO)
logging.basicConfig(
    level=_log_level,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
LOGGER = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Verifica Skill ID
# In produzione DELTA_ALEXA_SKILL_ID DEVE essere impostato; se mancante viene
# loggato un warning ma l'esecuzione continua per facilitare lo sviluppo locale.
# In ambiente Lambda, impostare la variabile e considerarla obbligatoria.
# ─────────────────────────────────────────────────────────────────────────────
_SKILL_ID: str = SECURITY_CONFIG.alexa_skill_id
if not _SKILL_ID:
    LOGGER.warning(
        "DELTA_ALEXA_SKILL_ID non configurato. "
        "Impostare la variabile ambiente in produzione Lambda."
    )


class SkillIdVerificationInterceptor(AbstractRequestInterceptor):
    """Interceptor che verifica l'Application ID Alexa ad ogni invocazione.

    Blocca richieste provenienti da skill diverse da quella configurata.
    Se DELTA_ALEXA_SKILL_ID non e impostato, il controllo viene saltato
    (utile in sviluppo locale, NON accettabile in produzione).
    """

    def process(self, handler_input: HandlerInput) -> None:
        if not _SKILL_ID:
            # Skip verifica solo se variabile non configurata (dev/test locale).
            return
        try:
            incoming_app_id = (
                handler_input.request_envelope.context.system.application.application_id
            )
        except Exception:
            LOGGER.error("Impossibile leggere application_id dalla request")
            raise ValueError("Richiesta Alexa malformata: application_id mancante")

        if incoming_app_id != _SKILL_ID:
            LOGGER.warning(
                "SkillIdVerification FAILED: incoming=%s expected=%s",
                incoming_app_id,
                _SKILL_ID,
            )
            raise ValueError("Skill ID non autorizzato")


class RequestLogger(AbstractRequestInterceptor):
    """Log minimale delle richieste entranti per diagnostica operativa.

    Non viene loggato il contenuto degli slot o dei messaggi utente.
    """

    def process(self, handler_input: HandlerInput) -> None:
        try:
            request_type = handler_input.request_envelope.request.object_type
            session_id = handler_input.request_envelope.session.session_id
            LOGGER.info("Alexa request type=%s session=%s", request_type, session_id)
        except Exception:
            LOGGER.debug("RequestLogger: impossibile leggere metadati richiesta")


class ResponseLogger(AbstractResponseInterceptor):
    """Log minimale delle risposte in uscita per diagnostica operativa.

    Non viene loggato il testo SSML della risposta.
    """

    def process(self, handler_input: HandlerInput, response: Response) -> None:
        try:
            should_end = getattr(response, "should_end_session", None)
            LOGGER.info("Alexa response should_end_session=%s", should_end)
        except Exception:
            pass


# ─────────────────────────────────────────────────────────────────────────────
# Costruzione skill con handler registrati in ordine di priorita.
# L'ordine e importante: handler piu specifici devono precedere quelli generici.
# ─────────────────────────────────────────────────────────────────────────────
sb = SkillBuilder()

# Interceptor di sicurezza: devono essere i PRIMI ad eseguire.
sb.add_global_request_interceptor(SkillIdVerificationInterceptor())
sb.add_global_request_interceptor(RequestLogger())
sb.add_global_response_interceptor(ResponseLogger())

# Handler specifici (ordine priorita).
sb.add_request_handler(LaunchRequestHandler())
sb.add_request_handler(LanguageSwitchHandler())
sb.add_request_handler(ChatIntentHandler())
sb.add_request_handler(HelpIntentHandler())
sb.add_request_handler(CancelAndStopIntentHandler())
sb.add_request_handler(FallbackIntentHandler())
sb.add_request_handler(SessionEndedRequestHandler())

# Exception handler: deve essere l'ultimo registrato.
sb.add_exception_handler(GenericExceptionHandler())

# Lambda handler: entry point AWS Lambda.
lambda_handler = sb.lambda_handler()

