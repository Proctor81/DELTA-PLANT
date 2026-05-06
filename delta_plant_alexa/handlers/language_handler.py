"""Handler per LanguageSwitchIntent: cambio lingua dinamico in sessione.

Non esiste rischio sicurezza diretto ma si valida che il locale richiesto
sia nella whitelist supportata prima di applicarlo alla sessione.
"""

from __future__ import annotations

import logging
from typing import Any

from ask_sdk_core.dispatch_components import AbstractRequestHandler
from ask_sdk_core.handler_input import HandlerInput
from ask_sdk_core.utils import is_intent_name
from ask_sdk_model import Response

from delta_plant_alexa.utils.language_manager import LanguageManager
from delta_plant_alexa.utils.ssml_builder import SSMLBuilder


LOGGER = logging.getLogger(__name__)


class LanguageSwitchHandler(AbstractRequestHandler):
    """Gestisce il cambio lingua a runtime su richiesta vocale."""

    def __init__(self) -> None:
        self._language_manager = LanguageManager()
        self._ssml_builder = SSMLBuilder()

    def can_handle(self, handler_input: HandlerInput) -> bool:
        return is_intent_name("LanguageSwitchIntent")(handler_input)

    def handle(self, handler_input: HandlerInput) -> Response:
        session_attrs = handler_input.attributes_manager.session_attributes
        current_locale = session_attrs.get("locale", "it-IT")

        # Estrazione sicura del valore slot targetLanguage.
        target_language = self._extract_target_language_slot(handler_input)
        LOGGER.info("LanguageSwitchIntent: target_language='%s' current_locale='%s'", target_language, current_locale)

        # Risoluzione e validazione in whitelist.
        new_locale = self._language_manager.map_spoken_language_to_locale(target_language)
        if not new_locale:
            # Tentativo fuzzy su testo libero.
            new_locale = self._language_manager.detect_locale_from_free_text(target_language)

        if new_locale:
            session_attrs["locale"] = new_locale
            handler_input.attributes_manager.session_attributes = session_attrs
            response_text = self._get_confirmation(new_locale)
            ssml = self._ssml_builder.build_response(response_text, locale=new_locale)
        else:
            response_text = self._get_not_found_message(current_locale)
            ssml = self._ssml_builder.build_response(response_text, locale=current_locale)

        reprompt_text = self._get_reprompt(session_attrs.get("locale", current_locale))
        reprompt_ssml = self._ssml_builder.build_response(reprompt_text, locale=session_attrs.get("locale", current_locale))

        return (
            handler_input.response_builder
            .speak(ssml)
            .ask(reprompt_ssml)
            .response
        )

    @staticmethod
    def _extract_target_language_slot(handler_input: HandlerInput) -> str:
        """Estrae slot targetLanguage con gestione sicura di valori assenti."""
        try:
            slots = handler_input.request_envelope.request.intent.slots
            if slots and "targetLanguage" in slots:
                slot = slots["targetLanguage"]
                if slot and slot.value:
                    return slot.value
        except Exception:
            pass
        return ""

    @staticmethod
    def _get_confirmation(locale: str) -> str:
        messages = {
            "it-IT": "Benissimo, parlo ora in italiano. Cosa vuoi sapere?",
            "en-US": "Great, I will now speak in English. What would you like to know?",
            "fr-FR": "Tres bien, je parle maintenant en francais. Que voulez-vous savoir?",
            "de-DE": "Sehr gut, ich spreche jetzt auf Deutsch. Was mochten Sie wissen?",
            "es-ES": "Perfecto, ahora hablo en espanol. Que deseas saber?",
            "nl-NL": "Uitstekend, ik spreek nu in het Nederlands. Wat wilt u weten?",
        }
        return messages.get(locale, messages["it-IT"])

    @staticmethod
    def _get_not_found_message(locale: str) -> str:
        messages = {
            "it-IT": "Lingua non supportata. Lingue disponibili: italiano, inglese, francese, tedesco, spagnolo, olandese.",
            "en-US": "Language not supported. Available: Italian, English, French, German, Spanish, Dutch.",
            "fr-FR": "Langue non supportee. Disponibles: italien, anglais, francais, allemand, espagnol, neerlandais.",
            "de-DE": "Sprache nicht unterstuetzt. Verfugbar: Italienisch, Englisch, Franzosisch, Deutsch, Spanisch, Niederlandisch.",
            "es-ES": "Idioma no soportado. Disponibles: italiano, ingles, frances, aleman, espanol, neerlandes.",
            "nl-NL": "Taal niet ondersteund. Beschikbaar: Italiaans, Engels, Frans, Duits, Spaans, Nederlands.",
        }
        return messages.get(locale, messages["it-IT"])

    @staticmethod
    def _get_reprompt(locale: str) -> str:
        reprompts = {
            "it-IT": "Hai qualche domanda agronomica?",
            "en-US": "Do you have an agronomy question?",
            "fr-FR": "Avez-vous une question agronomique?",
            "de-DE": "Haben Sie eine agronomische Frage?",
            "es-ES": "Tienes alguna pregunta agronomica?",
            "nl-NL": "Heeft u een agronomische vraag?",
        }
        return reprompts.get(locale, reprompts["it-IT"])

