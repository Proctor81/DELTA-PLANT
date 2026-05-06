"""Builder SSML per DELTA Plant Alexa.

Obiettivi:
- voce calda e ritmo stabile per interazione agricola
- output sicuro con escaping XML
- supporto locale con selezione voce dedicata
"""

from __future__ import annotations

import html


# Mappa voce consigliata per locale.
# Nota: la disponibilita effettiva dipende dalla regione/account Alexa.
VOICE_BY_LOCALE = {
	"it-IT": "Giorgio",
	"en-US": "Matthew",
	"fr-FR": "Mathieu",
	"de-DE": "Hans",
	"es-ES": "Enrique",
	"nl-NL": "Ruben",
}


class SSMLBuilder:
	"""Generatore di SSML parlabile e robusto per Alexa."""

	def __init__(self, default_locale: str = "it-IT") -> None:
		self.default_locale = default_locale

	def build_response(self, text: str, locale: str = "it-IT") -> str:
		"""Crea SSML finale con voce e prosodia controllate."""
		safe_text = self._escape_ssml_text(text)
		voice_name = VOICE_BY_LOCALE.get(locale, VOICE_BY_LOCALE.get(self.default_locale, "Giorgio"))

		# Prosodia conservativa: tono leggermente basso e ritmo medio per chiarezza.
		return (
			"<speak>"
			f"<voice name=\"{voice_name}\">"
			"<amazon:domain name=\"conversational\">"
			"<prosody rate=\"95%\" pitch=\"-2%\">"
			f"{safe_text}"
			"</prosody>"
			"</amazon:domain>"
			"</voice>"
			"</speak>"
		)

	def build_welcome(self, text: str, locale: str = "it-IT") -> str:
		"""Versione welcome con piccola pausa iniziale per naturalezza."""
		safe_text = self._escape_ssml_text(text)
		voice_name = VOICE_BY_LOCALE.get(locale, VOICE_BY_LOCALE.get(self.default_locale, "Giorgio"))
		return (
			"<speak>"
			"<break time=\"250ms\"/>"
			f"<voice name=\"{voice_name}\">"
			"<amazon:domain name=\"conversational\">"
			"<prosody rate=\"94%\" pitch=\"-3%\">"
			f"{safe_text}"
			"</prosody>"
			"</amazon:domain>"
			"</voice>"
			"</speak>"
		)

	@staticmethod
	def _escape_ssml_text(text: str) -> str:
		"""Escape XML entities per evitare rottura SSML o injection tag."""
		raw = (text or "").strip()
		return html.escape(raw, quote=True)
