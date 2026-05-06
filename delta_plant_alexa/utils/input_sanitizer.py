"""Sanitizzazione input utente per DELTA Plant Alexa.

Questo modulo applica una pipeline difensiva prima di inoltrare testo
all'orchestrator:
- normalizzazione unicode e spazi
- rimozione caratteri di controllo
- limiti di lunghezza
- neutralizzazione pattern tipici di prompt injection
- validazione con threat detector centralizzato
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Optional

from delta_plant_alexa.config import SECURITY_CONFIG
from delta_plant_alexa.security.threat_detector import ThreatDetector, ThreatCheckResult


# Regex per eliminare caratteri di controllo che possono alterare parsing/log.
CONTROL_CHARS_RE = re.compile(r"[\x00-\x1F\x7F]")

# Regex per ridurre sequenze whitespace anomale in una sola separazione.
MULTI_SPACE_RE = re.compile(r"\s+")

# Pattern comuni di injection da neutralizzare anche quando non bloccati completamente.
INJECTION_MARKERS_RE = re.compile(
	r"(```|<\/?system>|<\/?assistant>|<\/?developer>|\[\[.*?\]\])",
	flags=re.IGNORECASE,
)


@dataclass(frozen=True)
class SanitizationResult:
	"""Risultato della pipeline di sanitizzazione."""

	safe_text: str
	allowed: bool
	reason: str = ""
	matched_pattern: str = ""


class InputSanitizer:
	"""Sanitizza e valida input testuale utente in modo conservativo."""

	def __init__(self, threat_detector: Optional[ThreatDetector] = None) -> None:
		# Il detector viene iniettato per facilitare test e riuso.
		self.threat_detector = threat_detector or ThreatDetector()

	def sanitize_user_input(
		self,
		user_text: str,
		session_id: Optional[str] = None,
	) -> SanitizationResult:
		"""Applica sanitizzazione completa e blocca input potenzialmente malevoli."""
		raw_text = user_text or ""

		# 1) Normalizzazione unicode per ridurre bypass tramite omoglifi basilari.
		normalized = unicodedata.normalize("NFKC", raw_text)

		# 2) Rimozione caratteri di controllo non vocali.
		normalized = CONTROL_CHARS_RE.sub(" ", normalized)

		# 3) Collapse spazi, newline e tab per un testo pulito e prevedibile.
		normalized = MULTI_SPACE_RE.sub(" ", normalized).strip()

		if not normalized:
			return SanitizationResult(
				safe_text="",
				allowed=False,
				reason="Messaggio vuoto dopo sanitizzazione",
			)

		# 4) Limite lunghezza applicato prima di ulteriori elaborazioni.
		if len(normalized) > SECURITY_CONFIG.max_user_input_chars:
			return SanitizationResult(
				safe_text=normalized[: SECURITY_CONFIG.max_user_input_chars],
				allowed=False,
				reason="Input oltre limite massimo consentito",
				matched_pattern="max_user_input_chars",
			)

		# 5) Neutralizzazione marker strutturali tipici di prompt injection.
		normalized = INJECTION_MARKERS_RE.sub(" ", normalized)
		normalized = MULTI_SPACE_RE.sub(" ", normalized).strip()

		# 6) Validazione centralizzata con blacklist + regex euristiche.
		check: ThreatCheckResult = self.threat_detector.check_input(
			text=normalized,
			session_id=session_id,
		)
		if not check.allowed:
			return SanitizationResult(
				safe_text="",
				allowed=False,
				reason=check.reason,
				matched_pattern=check.matched_pattern,
			)

		return SanitizationResult(safe_text=normalized, allowed=True)

	@staticmethod
	def sanitize_for_log(text: str, limit: int = 120) -> str:
		"""Versione breve e innocua per logging operativo.

		Evita di riportare integralmente il contenuto utente nei log.
		"""
		cleaned = MULTI_SPACE_RE.sub(" ", (text or "")).strip()
		if len(cleaned) > limit:
			return f"{cleaned[:limit]}..."
		return cleaned
