"""Guardia di sicurezza per output orchestrator verso Alexa.

Questo modulo applica policy di sicurezza in uscita:
- blocco frasi/comandi pericolosi
- riduzione leakage di segreti
- limite lunghezza parlato
- fallback con risposta neutra e sicura
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from delta_plant_alexa.config import SECURITY_CONFIG
from delta_plant_alexa.security.threat_detector import ThreatDetector, ThreatCheckResult


# Pattern redazione per stringhe simili a token/chiavi/API key.
SECRET_LIKE_RE = re.compile(
	r"\b(hf_[A-Za-z0-9]{20,}|sk-[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16})\b"
)

# Pattern che indicano tentativi di azione non ammessa in una skill conversazionale.
DANGEROUS_ACTION_RE = re.compile(
	r"\b(rm\s+-rf|drop\s+table|delete\s+all|sudo|wget\s+http|curl\s+http)\b",
	flags=re.IGNORECASE,
)


@dataclass(frozen=True)
class GuardResult:
	"""Risultato della verifica output."""

	safe_text: str
	allowed: bool
	reason: str = ""
	matched_pattern: str = ""


class ResponseGuard:
	"""Valida la risposta orchestrator prima della sintesi vocale Alexa."""

	def __init__(self, threat_detector: Optional[ThreatDetector] = None) -> None:
		self.threat_detector = threat_detector or ThreatDetector()

	def validate_output(self, output_text: str, session_id: Optional[str] = None) -> GuardResult:
		"""Controlla e sanifica output; blocca contenuti fuori policy."""
		text = (output_text or "").strip()

		if not text:
			return GuardResult(
				safe_text="Mi dispiace, al momento non ho una risposta disponibile.",
				allowed=False,
				reason="Output vuoto",
			)

		# 1) Primo pass centralizzato su blacklist output.
		threat_check: ThreatCheckResult = self.threat_detector.check_output(
			text=text,
			session_id=session_id,
		)
		if not threat_check.allowed:
			return GuardResult(
				safe_text=self.safe_fallback_message(),
				allowed=False,
				reason=threat_check.reason,
				matched_pattern=threat_check.matched_pattern,
			)

		# 2) Secondo pass regex per comandi distruttivi/esecutivi.
		dangerous_match = DANGEROUS_ACTION_RE.search(text)
		if dangerous_match:
			return GuardResult(
				safe_text=self.safe_fallback_message(),
				allowed=False,
				reason="Output con azione non consentita",
				matched_pattern=dangerous_match.group(0),
			)

		# 3) Redazione token/secret in caso di leakage accidentale.
		sanitized = SECRET_LIKE_RE.sub("[REDACTED]", text)

		# 4) Limite lunghezza parlato per robustezza UX e timeout voice.
		max_output_chars = 1200
		if len(sanitized) > max_output_chars:
			sanitized = sanitized[:max_output_chars].rstrip() + "..."

		return GuardResult(safe_text=sanitized, allowed=True)

	@staticmethod
	def safe_fallback_message() -> str:
		"""Messaggio neutro quando la risposta viene bloccata dalla policy."""
		return (
			"Per motivi di sicurezza posso fornire solo supporto conversazionale "
			"su agronomia e cura delle piante. Riformula la richiesta in modo semplice."
		)
