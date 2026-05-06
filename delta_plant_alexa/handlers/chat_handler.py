"""Handler principale per ChatIntent: conversazione multi-turn sicura.

Gestione multi-turn:
- fino a MAX_TURNS turni per sessione Alexa (10-12 consigliati)
- history conservata in session_attributes["history"] (lista di dict role/content)
- history troncata a MAX_HISTORY_ITEMS per evitare overflow payload

Pipeline sicurezza:
- rate limit sessione tramite threat_detector
- sanitizzazione input tramite input_sanitizer
- chiamata orchestrator tramite DeltaOrchestratorClient (structured prompt + output guard)
- risposta all'utente solo dopo validazione output

Privacy:
- nessun dato utente salvato fuori dalla sessione Alexa temporanea
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from ask_sdk_core.dispatch_components import AbstractRequestHandler, AbstractExceptionHandler
from ask_sdk_core.handler_input import HandlerInput
from ask_sdk_core.utils import is_intent_name, is_request_type
from ask_sdk_model import Response

from delta_plant_alexa.utils.delta_orchestrator_client import DeltaOrchestratorClient, OrchestratorChatResult
from delta_plant_alexa.utils.language_manager import LanguageManager
from delta_plant_alexa.utils.ssml_builder import SSMLBuilder


LOGGER = logging.getLogger(__name__)

# Limite turni di conversazione per sessione.
MAX_TURNS: int = 12
# Numero massimo elementi conservati in history (turni user+assistant = 2 per turno).
MAX_HISTORY_ITEMS: int = 24


class ChatIntentHandler(AbstractRequestHandler):
    """Gestisce ChatIntent con conversazione multi-turn sicura."""

    def __init__(self) -> None:
        self._orchestrator = DeltaOrchestratorClient()
        self._language_manager = LanguageManager()
        self._ssml_builder = SSMLBuilder()

    def can_handle(self, handler_input: HandlerInput) -> bool:
        return is_intent_name("ChatIntent")(handler_input)

    def handle(self, handler_input: HandlerInput) -> Response:
        session_attrs = handler_input.attributes_manager.session_attributes

        locale = self._resolve_locale(handler_input, session_attrs)
        session_id = self._get_session_id(handler_input)

        # Incrementa contatore turni.
        turn_count: int = int(session_attrs.get("turn_count", 0)) + 1
        session_attrs["turn_count"] = turn_count
        session_attrs.setdefault("history", [])

        LOGGER.info("ChatIntent turn=%d session=%s locale=%s", turn_count, session_id, locale)

        # Blocco soft al superamento del limite turni.
        if turn_count > MAX_TURNS:
            return self._build_turn_limit_response(handler_input, locale)

        # Estrazione input utente dal slot.
        user_text = self._extract_user_message(handler_input)
        if not user_text:
            return self._build_empty_input_response(handler_input, locale)

        # Invocazione pipeline sicura verso orchestrator.
        result: OrchestratorChatResult = self._orchestrator.process_chat(
            user_text=user_text,
            session_id=session_id,
            locale=locale,
            session_attributes=session_attrs,
        )

        # Aggiorna history in sessione solo con dati puliti.
        if not result.blocked:
            self._update_history(session_attrs, user_text=user_text, answer=result.answer_text)

        handler_input.attributes_manager.session_attributes = session_attrs

        answer_ssml = self._ssml_builder.build_response(result.answer_text, locale=locale)
        reprompt_ssml = self._ssml_builder.build_response(
            self._get_reprompt(locale), locale=locale
        )

        return (
            handler_input.response_builder
            .speak(answer_ssml)
            .ask(reprompt_ssml)
            .response
        )

    # ──────────────────────────────────────────────────────────────────────────
    # Metodi privati di supporto
    # ──────────────────────────────────────────────────────────────────────────

    def _resolve_locale(self, handler_input: HandlerInput, session_attrs: Dict[str, Any]) -> str:
        """Priorita: sessione -> request -> default."""
        session_locale = session_attrs.get("locale")
        try:
            request_locale = handler_input.request_envelope.request.locale
        except Exception:
            request_locale = None
        return self._language_manager.resolve_locale(request_locale, session_locale)

    @staticmethod
    def _get_session_id(handler_input: HandlerInput) -> str:
        """Recupera session ID Alexa in modo sicuro."""
        try:
            return handler_input.request_envelope.session.session_id or "anonymous_session"
        except Exception:
            return "anonymous_session"

    @staticmethod
    def _extract_user_message(handler_input: HandlerInput) -> str:
        """Estrae slot userMessage con gestione robusta di valori null/vuoti."""
        try:
            slots = handler_input.request_envelope.request.intent.slots
            if slots and "userMessage" in slots:
                slot = slots["userMessage"]
                if slot and slot.value:
                    return slot.value.strip()
        except Exception:
            pass
        return ""

    @staticmethod
    def _update_history(
        session_attrs: Dict[str, Any],
        user_text: str,
        answer: str,
    ) -> None:
        """Aggiorna history in sessione mantenendo solo gli ultimi MAX_HISTORY_ITEMS elementi.

        Solo i dati gia validati vengono salvati (user_text sanitizzato, answer validata).
        Non viene salvato nulla se i valori sono vuoti.
        """
        history: List[Dict[str, str]] = session_attrs.get("history", [])
        if not isinstance(history, list):
            history = []

        # Tronca a stringa breve per evitare payload Alexa troppo pesanti.
        history.append({"role": "user", "content": user_text[:600]})
        history.append({"role": "assistant", "content": answer[:800]})

        # Mantieni solo gli ultimi MAX_HISTORY_ITEMS elementi (FIFO).
        session_attrs["history"] = history[-MAX_HISTORY_ITEMS:]

    def _build_turn_limit_response(self, handler_input: HandlerInput, locale: str) -> Response:
        """Risposta cortese quando la sessione ha raggiunto il limite di turni."""
        messages = {
            "it-IT": (
                "Abbiamo conversato a lungo in questa sessione. "
                "Termina e riavvia DELTA Plant per continuare, "
                "oppure usa Telegram DELTA per una sessione piu lunga."
            ),
            "en-US": (
                "We have had a long conversation in this session. "
                "Please close and restart DELTA Plant to continue, "
                "or use Telegram DELTA for a longer session."
            ),
            "fr-FR": (
                "Nous avons beaucoup converse dans cette session. "
                "Fermez et relancez DELTA Plant pour continuer, "
                "ou utilisez Telegram DELTA pour une session plus longue."
            ),
            "de-DE": (
                "Wir haben in dieser Sitzung viel gesprochen. "
                "Beenden und starten Sie DELTA Plant neu, "
                "oder verwenden Sie Telegram DELTA fur eine langere Sitzung."
            ),
            "es-ES": (
                "Hemos conversado mucho en esta sesion. "
                "Cierra y reinicia DELTA Plant para continuar, "
                "o usa Telegram DELTA para una sesion mas larga."
            ),
            "nl-NL": (
                "We hebben veel gesproken in deze sessie. "
                "Sluit af en start DELTA Plant opnieuw om door te gaan, "
                "of gebruik Telegram DELTA voor een langere sessie."
            ),
        }
        text = messages.get(locale, messages["it-IT"])
        ssml = self._ssml_builder.build_response(text, locale=locale)
        return (
            handler_input.response_builder
            .speak(ssml)
            .set_should_end_session(True)
            .response
        )

    def _build_empty_input_response(self, handler_input: HandlerInput, locale: str) -> Response:
        """Risposta per input non rilevato dallo slot."""
        messages = {
            "it-IT": "Non ho sentito la domanda. Puoi ripetere per favore?",
            "en-US": "I did not catch your question. Could you please repeat it?",
            "fr-FR": "Je n'ai pas entendu votre question. Pouvez-vous repeter s'il vous plait?",
            "de-DE": "Ich habe Ihre Frage nicht verstanden. Konnten Sie sie bitte wiederholen?",
            "es-ES": "No escuche la pregunta. Puede repetirla por favor?",
            "nl-NL": "Ik heb uw vraag niet gehoord. Kunt u het alstublieft herhalen?",
        }
        text = messages.get(locale, messages["it-IT"])
        ssml = self._ssml_builder.build_response(text, locale=locale)
        reprompt = self._get_reprompt(locale)
        reprompt_ssml = self._ssml_builder.build_response(reprompt, locale=locale)
        return (
            handler_input.response_builder
            .speak(ssml)
            .ask(reprompt_ssml)
            .response
        )

    @staticmethod
    def _get_reprompt(locale: str) -> str:
        reprompts = {
            "it-IT": "Hai altre domande sulla coltivazione o la salute delle piante?",
            "en-US": "Do you have more questions about farming or plant health?",
            "fr-FR": "Avez-vous d'autres questions sur la culture ou la sante des plantes?",
            "de-DE": "Haben Sie weitere Fragen zum Anbau oder zur Pflanzengesundheit?",
            "es-ES": "Tienes mas preguntas sobre cultivo o salud de las plantas?",
            "nl-NL": "Heeft u meer vragen over teelt of plantgezondheid?",
        }
        return reprompts.get(locale, reprompts["it-IT"])


class CancelAndStopIntentHandler(AbstractRequestHandler):
    """Gestisce AMAZON.CancelIntent e AMAZON.StopIntent con risposta localizzata."""

    def __init__(self) -> None:
        self._language_manager = LanguageManager()
        self._ssml_builder = SSMLBuilder()

    def can_handle(self, handler_input: HandlerInput) -> bool:
        return is_intent_name("AMAZON.CancelIntent")(handler_input) or is_intent_name(
            "AMAZON.StopIntent"
        )(handler_input)

    def handle(self, handler_input: HandlerInput) -> Response:
        session_attrs = handler_input.attributes_manager.session_attributes
        locale = session_attrs.get("locale", "it-IT")

        LOGGER.info("CancelOrStopIntent locale=%s", locale)

        farewells = {
            "it-IT": "Buona coltivazione! DELTA Plant e qui quando vuoi.",
            "en-US": "Happy farming! DELTA Plant is here whenever you need.",
            "fr-FR": "Bonne culture! DELTA Plant est la quand vous voulez.",
            "de-DE": "Gutes Anbauen! DELTA Plant ist fur Sie da.",
            "es-ES": "Buena cosecha! DELTA Plant esta aqui cuando lo necesites.",
            "nl-NL": "Goede oogst! DELTA Plant is er als je het nodig hebt.",
        }
        text = farewells.get(locale, farewells["it-IT"])
        ssml = self._ssml_builder.build_response(text, locale=locale)

        return (
            handler_input.response_builder
            .speak(ssml)
            .set_should_end_session(True)
            .response
        )


class GenericExceptionHandler(AbstractExceptionHandler):
    """Intercetta eccezioni non gestite e risponde in modo sicuro senza leakage.

    Non viene mai esposto lo stack trace o dettagli interni nella risposta vocale.
    """

    def __init__(self) -> None:
        self._ssml_builder = SSMLBuilder()

    def can_handle(self, handler_input: HandlerInput, exception: Exception) -> bool:
        return True

    def handle(self, handler_input: HandlerInput, exception: Exception) -> Response:
        LOGGER.exception("Unhandled exception in Alexa skill handler: %s", exception)

        session_attrs = handler_input.attributes_manager.session_attributes
        locale = session_attrs.get("locale", "it-IT")

        errors = {
            "it-IT": "Si e verificato un errore temporaneo. Riprova tra poco.",
            "en-US": "A temporary error occurred. Please try again shortly.",
            "fr-FR": "Une erreur temporaire s'est produite. Veuillez reessayer.",
            "de-DE": "Ein vorubergehender Fehler ist aufgetreten. Bitte versuchen Sie es erneut.",
            "es-ES": "Ocurrio un error temporal. Por favor intentalo de nuevo.",
            "nl-NL": "Er is een tijdelijke fout opgetreden. Probeer het binnenkort opnieuw.",
        }
        text = errors.get(locale, errors["it-IT"])
        ssml = self._ssml_builder.build_response(text, locale=locale)

        return (
            handler_input.response_builder
            .speak(ssml)
            .response
        )

