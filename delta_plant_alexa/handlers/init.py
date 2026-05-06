"""Package handler per DELTA Plant Alexa.

Esporta tutti i handler registrabili nel SkillBuilder di lambda_function.py.
L'ordine di import non e vincolante: il routing viene definito in lambda_function.
"""

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

__all__ = [
    "LaunchRequestHandler",
    "ChatIntentHandler",
    "CancelAndStopIntentHandler",
    "GenericExceptionHandler",
    "LanguageSwitchHandler",
    "FallbackIntentHandler",
    "HelpIntentHandler",
    "SessionEndedRequestHandler",
]
