"""Rilevamento minacce per input Alexa destinato a DELTA orchestrator.

Questo componente implementa controlli difensivi a basso costo:
- keyword blacklist case-insensitive
- euristiche regex per prompt injection / jailbreak
- rate limiting per sessione (in memoria)
- logging prudente senza persistere testo completo sensibile
"""

from __future__ import annotations

import hashlib
import logging
import re
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from delta_plant_alexa.config import SECURITY_CONFIG


LOGGER = logging.getLogger(__name__)


# Regex orientate a bloccare pattern comuni di evasione istruzioni e accesso privilegiato.
DANGEROUS_REGEXES: List[re.Pattern[str]] = [
    re.compile(r"ignore\s+(all\s+)?previous\s+instructions", re.IGNORECASE),
    re.compile(r"reveal\s+(the\s+)?system\s+prompt", re.IGNORECASE),
    re.compile(r"\b(jailbreak|bypass|override)\b", re.IGNORECASE),
    re.compile(r"\b(root|sudo|admin)\b", re.IGNORECASE),
    re.compile(r"\b(delete|drop\s+table|truncate)\b", re.IGNORECASE),
    re.compile(r"\b(api\s*key|secret|token|password|credential)\b", re.IGNORECASE),
]


@dataclass
class ThreatCheckResult:
    """Risultato analisi input con motivazione sintetica."""

    allowed: bool
    reason: str = ""
    matched_pattern: str = ""


class SessionRateLimiter:
    """Rate limiter semplice in memoria per sessione Alexa.

    Nota: in AWS Lambda, la memoria puo essere riusata tra invocazioni warm.
    Questo approccio resta utile come difesa best effort lato funzione.
    """

    def __init__(self, max_requests: int) -> None:
        self.max_requests = max_requests
        self._session_counters: Dict[str, int] = {}

    def increment_and_check(self, session_id: str) -> Tuple[bool, int]:
        """Incrementa il contatore sessione e verifica il limite.

        Ritorna:
        - allowed: True se entro limite
        - current_count: numero richieste gia viste in sessione
        """
        current_count = self._session_counters.get(session_id, 0) + 1
        self._session_counters[session_id] = current_count
        return current_count <= self.max_requests, current_count


class ThreatDetector:
    """Componente principale di rilevamento minacce input/output testuale."""

    def __init__(self) -> None:
        self.blocked_patterns = [p.lower() for p in SECURITY_CONFIG.blocked_patterns]
        self.rate_limiter = SessionRateLimiter(
            max_requests=SECURITY_CONFIG.max_requests_per_session
        )

    def check_rate_limit(self, session_id: str) -> ThreatCheckResult:
        """Verifica il numero massimo richieste per sessione."""
        allowed, current_count = self.rate_limiter.increment_and_check(session_id=session_id)
        if not allowed:
            self._log_suspicious_event(
                event_type="rate_limit_exceeded",
                session_id=session_id,
                detail=f"count={current_count}",
            )
            return ThreatCheckResult(
                allowed=False,
                reason="Rate limit sessione superato",
                matched_pattern="max_requests_per_session",
            )
        return ThreatCheckResult(allowed=True)

    def check_input(self, text: str, session_id: Optional[str] = None) -> ThreatCheckResult:
        """Analizza l'input utente e blocca contenuti ad alto rischio."""
        normalized = (text or "").strip().lower()

        if not normalized:
            return ThreatCheckResult(allowed=False, reason="Input vuoto")

        if len(normalized) > SECURITY_CONFIG.max_user_input_chars:
            return ThreatCheckResult(
                allowed=False,
                reason="Input troppo lungo",
                matched_pattern="max_user_input_chars",
            )

        # Blocco diretto su keyword blacklist configurata.
        for pattern in self.blocked_patterns:
            if pattern in normalized:
                self._log_suspicious_event(
                    event_type="blacklist_match",
                    session_id=session_id,
                    detail=pattern,
                    user_text=normalized,
                )
                return ThreatCheckResult(
                    allowed=False,
                    reason="Input bloccato per policy sicurezza",
                    matched_pattern=pattern,
                )

        # Secondo pass su regex anti-injection.
        for regex in DANGEROUS_REGEXES:
            if regex.search(normalized):
                matched = regex.pattern
                self._log_suspicious_event(
                    event_type="regex_match",
                    session_id=session_id,
                    detail=matched,
                    user_text=normalized,
                )
                return ThreatCheckResult(
                    allowed=False,
                    reason="Tentativo potenziale di prompt injection",
                    matched_pattern=matched,
                )

        return ThreatCheckResult(allowed=True)

    def check_output(self, text: str, session_id: Optional[str] = None) -> ThreatCheckResult:
        """Controllo base su output orchestrator per evitare leakage/azioni pericolose."""
        normalized = (text or "").strip().lower()
        for pattern in SECURITY_CONFIG.blocked_output_patterns:
            if pattern.lower() in normalized:
                self._log_suspicious_event(
                    event_type="dangerous_output",
                    session_id=session_id,
                    detail=pattern,
                )
                return ThreatCheckResult(
                    allowed=False,
                    reason="Output bloccato per policy sicurezza",
                    matched_pattern=pattern,
                )
        return ThreatCheckResult(allowed=True)

    def _log_suspicious_event(
        self,
        event_type: str,
        detail: str,
        session_id: Optional[str] = None,
        user_text: str = "",
    ) -> None:
        """Logga in forma minimizzata per privacy e compliance.

        Non salviamo mai il testo completo dell'utente nei log.
        Usiamo hash breve + lunghezza per correlazione tecnica.
        """
        text_hash = ""
        text_len = 0
        if user_text:
            text_len = len(user_text)
            text_hash = hashlib.sha256(user_text.encode("utf-8")).hexdigest()[:12]

        safe_session = session_id or "anonymous_session"
        LOGGER.warning(
            "suspicious_event type=%s detail=%s session=%s text_hash=%s text_len=%s ts=%s",
            event_type,
            detail,
            safe_session,
            text_hash,
            text_len,
            int(time.time()),
        )
