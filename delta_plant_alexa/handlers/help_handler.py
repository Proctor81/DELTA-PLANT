"""Handler per AMAZON.HelpIntent: guida utente sulle funzionalita disponibili.

Informa esplicitamente su cosa la skill puo e NON puo fare,
in linea con le policy Alexa per skill pubbliche e per trasparenza privacy.
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


class HelpIntentHandler(AbstractRequestHandler):
    """Risponde con guida d'uso chiara e informazioni privacy."""

    def __init__(self) -> None:
        self._language_manager = LanguageManager()
        self._ssml_builder = SSMLBuilder()

    def can_handle(self, handler_input: HandlerInput) -> bool:
        return is_intent_name("AMAZON.HelpIntent")(handler_input)

    def handle(self, handler_input: HandlerInput) -> Response:
        session_attrs = handler_input.attributes_manager.session_attributes
        locale = session_attrs.get("locale", "it-IT")

        LOGGER.info("HelpIntent: locale=%s", locale)

        help_text = self._get_help_text(locale)
        reprompt = self._get_reprompt(locale)

        ssml = self._ssml_builder.build_response(help_text, locale=locale)
        reprompt_ssml = self._ssml_builder.build_response(reprompt, locale=locale)

        return (
            handler_input.response_builder
            .speak(ssml)
            .ask(reprompt_ssml)
            .response
        )

    @staticmethod
    def _get_help_text(locale: str) -> str:
        # Ogni messaggio informa anche su cosa NON e disponibile e reindirizza a Telegram.
        messages = {
            "it-IT": (
                "DELTA Plant ti aiuta con consigli agronomici conversazionali: malattie delle piante, "
                "carenze nutrizionali, irrigazione, trattamenti e pratiche colturali. "
                "Funzioni avanzate come analisi foto, lettura sensori e diagnosi AI sono disponibili "
                "solo sul canale Telegram DELTA. "
                "Hai una domanda sulla tua coltura?"
            ),
            "en-US": (
                "DELTA Plant helps with conversational agronomy advice: plant diseases, "
                "nutrient deficiencies, irrigation, treatments and farming practices. "
                "Advanced features like photo analysis, sensor readings and AI diagnosis are available "
                "only on Telegram DELTA. "
                "Do you have a question about your crop?"
            ),
            "fr-FR": (
                "DELTA Plant aide avec des conseils agronomiques: maladies des plantes, "
                "deficiences nutritives, irrigation, traitements et pratiques culturales. "
                "Les fonctions avancees comme l'analyse photo et les capteurs sont sur Telegram DELTA. "
                "Avez-vous une question sur votre culture?"
            ),
            "de-DE": (
                "DELTA Plant hilft mit agronomischen Ratschlagen: Pflanzenkrankheiten, "
                "Mangelernahrung, Bewasserung, Behandlungen und Anbaumethoden. "
                "Erweiterte Funktionen wie Fotoanalyse und Sensoren sind nur auf Telegram DELTA. "
                "Haben Sie eine Frage zu Ihrer Kultur?"
            ),
            "es-ES": (
                "DELTA Plant ayuda con consejos agronomicos: enfermedades de plantas, "
                "deficiencias nutricionales, riego, tratamientos y practicas de cultivo. "
                "Funciones avanzadas como analisis de fotos y sensores solo en Telegram DELTA. "
                "Tienes alguna pregunta sobre tu cultivo?"
            ),
            "nl-NL": (
                "DELTA Plant helpt met agronomisch advies: plantenziekten, "
                "voedingstekorten, irrigatie, behandelingen en teeltpraktijken. "
                "Geavanceerde functies zoals fotoanalyse en sensoren zijn alleen op Telegram DELTA. "
                "Heeft u een vraag over uw gewas?"
            ),
        }
        return messages.get(locale, messages["it-IT"])

    @staticmethod
    def _get_reprompt(locale: str) -> str:
        reprompts = {
            "it-IT": "Cosa vuoi sapere sulle tue piante?",
            "en-US": "What would you like to know about your plants?",
            "fr-FR": "Que voulez-vous savoir sur vos plantes?",
            "de-DE": "Was mochten Sie uber Ihre Pflanzen wissen?",
            "es-ES": "Que quieres saber sobre tus plantas?",
            "nl-NL": "Wat wilt u weten over uw planten?",
        }
        return reprompts.get(locale, reprompts["it-IT"])

