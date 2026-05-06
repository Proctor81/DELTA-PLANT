"""Configurazione centralizzata per il modulo delta_plant_alexa.

Questo file contiene solo impostazioni necessarie alla skill Alexa,
con valori di default conservativi orientati al principio di least privilege.
Le configurazioni sensibili devono arrivare da variabili ambiente.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Dict, List


@dataclass(frozen=True)
class AlexaSecurityConfig:
    """Impostazioni di sicurezza usate trasversalmente nel modulo Alexa."""

    # Verifica obbligatoria dell'Application ID Alexa Skill.
    # In produzione questo valore va impostato in Lambda environment.
    alexa_skill_id: str = os.getenv("DELTA_ALEXA_SKILL_ID", "")

    # Timeout logico interno per chiamate orchestrator.
    # Deve essere inferiore al timeout Lambda complessivo.
    orchestrator_timeout_seconds: int = int(os.getenv("DELTA_ALEXA_TIMEOUT_SEC", "8"))

    # Limite aggressivo sulla lunghezza input utente per ridurre abuso prompt.
    max_user_input_chars: int = int(os.getenv("DELTA_ALEXA_MAX_INPUT", "550"))

    # Rate limit per sessione Alexa.
    max_requests_per_session: int = int(os.getenv("DELTA_ALEXA_MAX_REQ_SESSION", "18"))

    # Logica di isolamento: solo canale conversazionale.
    allow_chat_only: bool = True

    # Disabilitazione esplicita funzionalita ad alto rischio non esposte in skill pubblica.
    allow_image_features: bool = False
    allow_sensor_features: bool = False
    allow_training_features: bool = False
    allow_admin_features: bool = False
    allow_quantum_features: bool = False

    # URL opzionale fallback HTTP verso orchestrator se import diretto non disponibile.
    orchestrator_http_fallback_url: str = os.getenv("DELTA_ALEXA_ORCHESTRATOR_HTTP_URL", "")

    # Lista base di pattern pericolosi da bloccare a monte.
    blocked_patterns: List[str] = field(
        default_factory=lambda: [
            "ignore previous instructions",
            "ignore all previous",
            "system prompt",
            "developer message",
            "jailbreak",
            "bypass",
            "admin",
            "root",
            "sudo",
            "photo",
            "image",
            "camera",
            "sensor",
            "quantum",
            "train",
            "training",
            "export",
            "delete",
            "drop table",
            "credential",
            "secret",
            "token",
            "apikey",
            "api key",
            "passwd",
            "password",
            "shell",
            "bash",
            "powershell",
            "prompt injection",
        ]
    )

    # Pattern di output che non devono mai essere pronunciati dalla skill.
    blocked_output_patterns: List[str] = field(
        default_factory=lambda: [
            "run this command",
            "execute:",
            "rm -rf",
            "curl http",
            "wget http",
            "sudo",
            "api key",
            "secret",
            "password",
            "token",
            "system prompt",
        ]
    )


@dataclass(frozen=True)
class LanguageConfig:
    """Configurazione lingue supportate dalla skill."""

    default_locale: str = "it-IT"
    supported_locales: List[str] = field(
        default_factory=lambda: ["it-IT", "en-US", "fr-FR", "de-DE", "es-ES", "nl-NL"]
    )

    # Mappa frasi standard per messaggi di servizio localizzati.
    # Le stringhe sono brevi per restare fluide in sintesi vocale.
    service_messages: Dict[str, Dict[str, str]] = field(
        default_factory=lambda: {
            "it-IT": {
                "welcome": "Benvenuto in DELTA Plant. Posso aiutarti con consigli agronomici conversazionali.",
                "help": "Puoi chiedermi informazioni su coltivazioni e problemi comuni delle piante.",
            },
            "en-US": {
                "welcome": "Welcome to DELTA Plant. I can help with conversational agronomy advice.",
                "help": "Ask me about crops, plant symptoms, and farming best practices.",
            },
            "fr-FR": {
                "welcome": "Bienvenue dans DELTA Plant. Je peux aider avec des conseils agronomiques conversationnels.",
                "help": "Vous pouvez demander des informations sur les cultures et les symptomes des plantes.",
            },
            "de-DE": {
                "welcome": "Willkommen bei DELTA Plant. Ich helfe mit konversationellen Agronomie Tipps.",
                "help": "Fragen Sie nach Pflanzenanbau, Symptomen und bewahrten Methoden.",
            },
            "es-ES": {
                "welcome": "Bienvenido a DELTA Plant. Puedo ayudar con consejos agronomicos conversacionales.",
                "help": "Pregunta sobre cultivos, sintomas de plantas y buenas practicas.",
            },
            "nl-NL": {
                "welcome": "Welkom bij DELTA Plant. Ik help met agronomisch advies in gesprek vorm.",
                "help": "Vraag over gewassen, plant symptomen en goede teeltpraktijken.",
            },
        }
    )


SECURITY_CONFIG = AlexaSecurityConfig()
LANGUAGE_CONFIG = LanguageConfig()
