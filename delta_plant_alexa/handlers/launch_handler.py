"""Handler per LaunchRequest: avvio skill DELTA Plant.

Mostra benvenuto personalizzato per locale, informa l'utente della natura
conversazionale del servizio e invita alla prima domanda.
Nessuna funzionalita sensibile esposta.
"""

from __future__ import annotations

import logging
from typing import Any

from ask_sdk_core.dispatch_components import AbstractRequestHandler
from ask_sdk_core.handler_input import HandlerInput
from ask_sdk_core.utils import is_request_type
from ask_sdk_model import Response

from delta_plant_alexa.utils.language_manager import LanguageManager
from delta_plant_alexa.utils.ssml_builder import SSMLBuilder


LOGGER = logging.getLogger(__name__)


class LaunchRequestHandler(AbstractRequestHandler):
    """Gestisce l'avvio skill Alexa."""

    def __init__(self) -> None:
        self._language_manager = LanguageManager()
        self._ssml_builder = SSMLBuilder()

    def can_handle(self, handler_input: HandlerInput) -> bool:
        return is_request_type("LaunchRequest")(handler_input)

    def handle(self, handler_input: HandlerInput) -> Response:
        locale = self._get_locale(handler_input)
        session_attrs = handler_input.attributes_manager.session_attributes

        # Inizializza attributi sessione con valori sicuri.
        session_attrs.setdefault("locale", locale)
        session_attrs.setdefault("turn_count", 0)
        session_attrs.setdefault("history", [])

        LOGGER.info("LaunchRequest locale=%s", locale)

        # Messaggio di benvenuto informativo: informa su natura conversazionale
        # e presenza canale Telegram per funzioni avanzate (foto, sensori, ecc.).
        welcome_text = self._language_manager.get_message(locale, "welcome")
        disclaimer = self._get_disclaimer(locale)
        full_text = f"{welcome_text} {disclaimer}"

        ssml = self._ssml_builder.build_welcome(full_text, locale=locale)
        reprompt_text = self._get_reprompt(locale)
        reprompt_ssml = self._ssml_builder.build_response(reprompt_text, locale=locale)

        handler_input.attributes_manager.session_attributes = session_attrs

        return (
            handler_input.response_builder
            .speak(ssml)
            .ask(reprompt_ssml)
            .response
        )

    def _get_locale(self, handler_input: HandlerInput) -> str:
        try:
            return handler_input.request_envelope.request.locale or "it-IT"
        except Exception:
            return "it-IT"

    @staticmethod
    def _get_disclaimer(locale: str) -> str:
        disclaimers = {
            "it-IT": "Posso rispondere solo a domande agronomiche conversazionali. Per foto e sensori usa Telegram DELTA.",
            "en-US": "I can answer only conversational agronomy questions. For photos and sensors use Telegram DELTA.",
            "fr-FR": "Je reponds uniquement aux questions agronomiques. Pour les photos et capteurs, utilisez Telegram DELTA.",
            "de-DE": "Ich beantworte nur agronomische Fragen. Fotos und Sensoren sind nur per Telegram DELTA verfugbar.",
            "es-ES": "Respondo solo preguntas agronomicas. Para fotos y sensores usa Telegram DELTA.",
            "nl-NL": "Ik beantwoord alleen agronomische vragen. Voor fotos en sensoren gebruik Telegram DELTA.",
        }
        return disclaimers.get(locale, disclaimers["it-IT"])

    @staticmethod
    def _get_reprompt(locale: str) -> str:
        reprompts = {
            "it-IT": "Hai qualche domanda su colture, malattie o trattamenti?",
            "en-US": "Do you have a question about crops, diseases or treatments?",
            "fr-FR": "Avez-vous une question sur les cultures, maladies ou traitements?",
            "de-DE": "Haben Sie eine Frage zu Kulturen, Krankheiten oder Behandlungen?",
            "es-ES": "Tienes alguna pregunta sobre cultivos, enfermedades o tratamientos?",
            "nl-NL": "Heeft u een vraag over gewassen, ziekten of behandelingen?",
        }
        return reprompts.get(locale, reprompts["it-IT"])

