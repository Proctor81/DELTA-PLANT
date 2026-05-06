"""Handler per SessionEndedRequest: pulizia sessione.

Non memorizza nulla di permanente. Si limita a loggare la fine
della sessione in forma minimale per diagnostica operativa.
"""

from __future__ import annotations

import logging

from ask_sdk_core.dispatch_components import AbstractRequestHandler
from ask_sdk_core.handler_input import HandlerInput
from ask_sdk_core.utils import is_request_type
from ask_sdk_model import Response


LOGGER = logging.getLogger(__name__)


class SessionEndedRequestHandler(AbstractRequestHandler):
    """Termina sessione senza persistere dati utente."""

    def can_handle(self, handler_input: HandlerInput) -> bool:
        return is_request_type("SessionEndedRequest")(handler_input)

    def handle(self, handler_input: HandlerInput) -> Response:
        # Legge solo il motivo di chiusura per diagnostica, non il contenuto.
        try:
            reason = handler_input.request_envelope.request.reason
        except Exception:
            reason = "UNKNOWN"

        LOGGER.info("SessionEndedRequest reason=%s", reason)

        # Nessuna risposta obbligatoria per SessionEndedRequest.
        # La history temporanea di sessione viene abbandonata automaticamente
        # da Alexa: non e necessaria pulizia esplicita.
        return handler_input.response_builder.response

