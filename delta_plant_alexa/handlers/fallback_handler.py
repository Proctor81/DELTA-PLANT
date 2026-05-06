"""Handler per AMAZON.FallbackIntent: richiesta non compresa.

Riporta l'utente verso argomenti agronomici sicuri senza esporre
internals del sistema.
"""

from __future__ import annotations

import logging

from ask_sdk_core.dispatch_components import AbstractRequestHandler
from ask_sdk_core.handler_input import HandlerInput
from ask_sdk_core.utils import is_intent_name
from ask_sdk_model import Response

from delta_plant_alexa.utils.language_manager import LanguageManager
from delta_plant_alexa.utils.ssml_builder import SSMLBuilder


LOGGER = logging.getLogger(__name__)


class FallbackIntentHandler(AbstractRequestHandler):
    """Gestisce intent non riconosciuti senza esporre informazioni interne."""

    def __init__(self) -> None:
        self._language_manager = LanguageManager()
        self._ssml_builder = SSMLBuilder()

    def can_handle(self, handler_input: HandlerInput) -> bool:
        return is_intent_name("AMAZON.FallbackIntent")(handler_input)

    def handle(self, handler_input: HandlerInput) -> Response:
        session_attrs = handler_input.attributes_manager.session_attributes
        locale = session_attrs.get("locale", "it-IT")

        LOGGER.info("FallbackIntent: locale=%s", locale)

        text = self._get_fallback_message(locale)
        reprompt = self._get_reprompt(locale)

        ssml = self._ssml_builder.build_response(text, locale=locale)
        reprompt_ssml = self._ssml_builder.build_response(reprompt, locale=locale)

        return (
            handler_input.response_builder
            .speak(ssml)
            .ask(reprompt_ssml)
            .response
        )

    @staticmethod
    def _get_fallback_message(locale: str) -> str:
        messages = {
            "it-IT": "Non ho capito bene. Puoi chiedermi di malattie fogliari, carenze, irrigazione o strategie agronomiche.",
            "en-US": "I did not quite understand. Ask me about leaf diseases, deficiencies, irrigation or agronomy strategies.",
            "fr-FR": "Je n'ai pas bien compris. Posez-moi des questions sur les maladies foliaires, deficiences, irrigation ou strategies agronomiques.",
            "de-DE": "Ich habe nicht ganz verstanden. Fragen Sie mich nach Blattkrankheiten, Mangeln, Bewasserung oder Agronomiestrategie.",
            "es-ES": "No entendi bien. Puedes preguntarme sobre enfermedades foliares, deficiencias, riego o estrategias agronomicas.",
            "nl-NL": "Ik heb het niet goed begrepen. Vraag me naar bladziekten, tekorten, irrigatie of agronomie strategie.",
        }
        return messages.get(locale, messages["it-IT"])

    @staticmethod
    def _get_reprompt(locale: str) -> str:
        reprompts = {
            "it-IT": "Di cosa hai bisogno per le tue colture?",
            "en-US": "What do you need for your crops?",
            "fr-FR": "De quoi avez-vous besoin pour vos cultures?",
            "de-DE": "Was benotigen Sie fur Ihre Kulturen?",
            "es-ES": "Que necesitas para tus cultivos?",
            "nl-NL": "Wat heeft u nodig voor uw gewassen?",
        }
        return reprompts.get(locale, reprompts["it-IT"])

