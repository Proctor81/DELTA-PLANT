"""Gestione lingua/locale per DELTA Plant Alexa.

Supporta:
- locale di default e whitelist lingue supportate
- parsing robusto del comando di cambio lingua
- recupero messaggi di servizio localizzati
"""

from __future__ import annotations

from typing import Dict, Optional

from delta_plant_alexa.config import LANGUAGE_CONFIG


# Mappa normalizzata da etichetta pronunciata a locale Alexa supportato.
LANGUAGE_TO_LOCALE: Dict[str, str] = {
	"italiano": "it-IT",
	"italian": "it-IT",
	"it": "it-IT",
	"inglese": "en-US",
	"english": "en-US",
	"en": "en-US",
	"francese": "fr-FR",
	"french": "fr-FR",
	"fr": "fr-FR",
	"tedesco": "de-DE",
	"german": "de-DE",
	"de": "de-DE",
	"spagnolo": "es-ES",
	"spanish": "es-ES",
	"es": "es-ES",
	"olandese": "nl-NL",
	"dutch": "nl-NL",
	"nl": "nl-NL",
}


class LanguageManager:
	"""Selettore centralizzato lingua conversazionale della skill."""

	def __init__(self) -> None:
		self.default_locale = LANGUAGE_CONFIG.default_locale
		self.supported_locales = set(LANGUAGE_CONFIG.supported_locales)
		self.service_messages = LANGUAGE_CONFIG.service_messages

	def resolve_locale(
		self,
		request_locale: Optional[str],
		session_locale: Optional[str] = None,
	) -> str:
		"""Determina locale effettivo con priorita sessione -> richiesta -> default."""
		if session_locale and session_locale in self.supported_locales:
			return session_locale
		if request_locale and request_locale in self.supported_locales:
			return request_locale
		return self.default_locale

	def map_spoken_language_to_locale(self, language_text: str) -> Optional[str]:
		"""Mappa lingua pronunciata in un locale supportato."""
		key = (language_text or "").strip().lower()
		mapped = LANGUAGE_TO_LOCALE.get(key)
		if mapped in self.supported_locales:
			return mapped
		return None

	def detect_locale_from_free_text(self, text: str) -> Optional[str]:
		"""Riconosce richiesta lingua da testo libero (es. parla in inglese)."""
		normalized = (text or "").strip().lower()
		for language_label, locale in LANGUAGE_TO_LOCALE.items():
			if language_label in normalized and locale in self.supported_locales:
				return locale
		return None

	def get_message(self, locale: str, key: str) -> str:
		"""Restituisce messaggio di servizio localizzato con fallback sicuro."""
		effective_locale = locale if locale in self.supported_locales else self.default_locale
		locale_messages = self.service_messages.get(effective_locale, {})
		if key in locale_messages:
			return locale_messages[key]
		return self.service_messages[self.default_locale].get(key, "")
