"""Client sicuro per invocare DELTA orchestrator dalla skill Alexa.

Caratteristiche principali:
- isolamento funzionale: solo canale chat conversazionale
- difesa anti prompt injection in ingresso e in uscita
- chiamata diretta a delta_orchestrator con try/except rigorosi
- fallback HTTP opzionale, sempre con policy di sicurezza
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import requests

from delta_plant_alexa.config import SECURITY_CONFIG
from delta_plant_alexa.security.threat_detector import ThreatDetector
from delta_plant_alexa.utils.input_sanitizer import InputSanitizer
from delta_plant_alexa.utils.response_guard import ResponseGuard


LOGGER = logging.getLogger(__name__)


SYSTEM_INSTRUCTIONS = (
	"Sei DELTA Plant Alexa Chat. "
	"RISPONDI solo su consigli agronomici conversazionali e cura piante. "
	"NON fornire istruzioni su admin, sensori, immagini, training, quantum, export, delete, shell o credenziali. "
	"Se richiesta fuori ambito, rifiuta in modo cortese e reindirizza alla chat Telegram avanzata. "
	"Mantieni risposta breve, sicura, pratica."
)


@dataclass(frozen=True)
class OrchestratorChatResult:
	"""Risultato normalizzato per i layer handler Alexa."""

	answer_text: str
	blocked: bool = False
	reason: str = ""
	suspicious: bool = False


class DeltaOrchestratorClient:
	"""Facade sicura per orchestrator DELTA orientata ad Alexa public skill."""

	def __init__(self) -> None:
		self.threat_detector = ThreatDetector()
		self.input_sanitizer = InputSanitizer(threat_detector=self.threat_detector)
		self.response_guard = ResponseGuard(threat_detector=self.threat_detector)

	def process_chat(
		self,
		user_text: str,
		session_id: str,
		locale: str,
		session_attributes: Optional[Dict[str, Any]] = None,
	) -> OrchestratorChatResult:
		"""Pipeline completa: rate limit -> sanitize -> orchestrator -> output guard."""
		attrs: Dict[str, Any] = session_attributes or {}

		# 1) Rate limiting per sessione Alexa.
		rate_check = self.threat_detector.check_rate_limit(session_id=session_id)
		if not rate_check.allowed:
			return OrchestratorChatResult(
				answer_text=(
					"Hai raggiunto il limite di richieste per questa sessione. "
					"Apri una nuova sessione Alexa per continuare."
				),
				blocked=True,
				reason=rate_check.reason,
				suspicious=True,
			)

		# 2) Sanitizzazione input utente e validazione anti-injection.
		sanitize_result = self.input_sanitizer.sanitize_user_input(
			user_text=user_text,
			session_id=session_id,
		)
		if not sanitize_result.allowed:
			return OrchestratorChatResult(
				answer_text=(
					"Per sicurezza posso gestire solo richieste agronomiche conversazionali. "
					"Riformula la domanda su colture, sintomi o prevenzione."
				),
				blocked=True,
				reason=sanitize_result.reason,
				suspicious=True,
			)

		# 3) Structured prompting: separazione esplicita tra istruzioni sistema e input utente.
		safe_prompt = self._build_structured_prompt(
			sanitized_user_input=sanitize_result.safe_text,
			locale=locale,
		)

		# 4) Costruzione contesto minimo e non privilegiato.
		history = self._safe_history_from_session(attrs)
		delta_context = {
			# Campi sensibili forzati a null per isolamento funzionale.
			"tflite_diagnosis": None,
			"sensor_data": None,
			"quantum_risk_score": None,
			"image_path": None,
			"plant_type": "generic",
		}
		orchestrator_state = {
			"messages": history,
			"delta_context": delta_context,
			"errors": [],
			"final_answer": None,
		}

		# 5) Invocazione orchestrator: diretto python prima, fallback HTTP opzionale dopo.
		raw_answer = self._invoke_orchestrator(
			structured_prompt=safe_prompt,
			state=orchestrator_state,
		)

		# 6) Guardia output prima del ritorno ad Alexa.
		guard = self.response_guard.validate_output(raw_answer, session_id=session_id)
		if not guard.allowed:
			LOGGER.warning(
				"output_blocked session_id=%s reason=%s matched=%s",
				session_id,
				guard.reason,
				guard.matched_pattern,
			)
			return OrchestratorChatResult(
				answer_text=guard.safe_text,
				blocked=True,
				reason=guard.reason,
				suspicious=True,
			)

		return OrchestratorChatResult(answer_text=guard.safe_text)

	def _invoke_orchestrator(self, structured_prompt: str, state: Dict[str, Any]) -> str:
		"""Invoca orchestrator in modo difensivo con fallback degradato."""
		# Tentativo 1: chiamata diretta in-process (preferita).
		direct_answer = self._invoke_direct(structured_prompt=structured_prompt, state=state)
		if direct_answer:
			return direct_answer

		# Tentativo 2: fallback HTTP opzionale se configurato.
		http_answer = self._invoke_http_fallback(structured_prompt=structured_prompt, state=state)
		if http_answer:
			return http_answer

		# Fallback finale sicuro e non informativo su internals.
		return (
			"Al momento il servizio conversazionale non e disponibile. "
			"Riprova tra poco oppure usa il canale Telegram DELTA per funzioni avanzate."
		)

	def _invoke_direct(self, structured_prompt: str, state: Dict[str, Any]) -> str:
		"""Import diretto di delta_orchestrator con gestione errori stretta."""
		try:
			# Import locale in try/except per non rompere cold start se dipendenze mancano.
			from delta_orchestrator.integration.delta_bridge import orchestrate_task

			result: Dict[str, Any] = self._run_async_safely(
				orchestrate_task(structured_prompt, state)
			)
			return self._extract_answer_from_result(result)
		except Exception as exc:
			LOGGER.exception("direct_orchestrator_call_failed: %s", exc)
			return ""

	def _invoke_http_fallback(self, structured_prompt: str, state: Dict[str, Any]) -> str:
		"""Fallback HTTP opzionale verso endpoint orchestrator remoto."""
		base_url = (SECURITY_CONFIG.orchestrator_http_fallback_url or "").strip()
		if not base_url:
			return ""

		# timeout client minore o uguale al budget sicurezza configurato.
		timeout_seconds = max(1, SECURITY_CONFIG.orchestrator_timeout_seconds)

		payload = {
			"messages": state.get("messages", []) + [{"role": "user", "content": structured_prompt}],
			"delta_context": state.get("delta_context", {}),
			"errors": [],
			"final_answer": None,
		}
		endpoint = base_url.rstrip("/") + "/orchestrate"
		try:
			response = requests.post(endpoint, json=payload, timeout=timeout_seconds)
			response.raise_for_status()
			data = response.json()
			return self._extract_answer_from_result(data)
		except Exception as exc:
			LOGGER.warning("http_orchestrator_fallback_failed endpoint=%s error=%s", endpoint, exc)
			return ""

	@staticmethod
	def _extract_answer_from_result(result: Dict[str, Any]) -> str:
		"""Estrae testo risposta da vari formati output dell'orchestrator."""
		if not isinstance(result, dict):
			return ""

		# Formato preferito: final_answer.
		final_answer = result.get("final_answer")
		if isinstance(final_answer, str) and final_answer.strip():
			return final_answer.strip()

		# Possibile fallback su chiavi comuni.
		for key in ("answer", "response", "text", "output"):
			value = result.get(key)
			if isinstance(value, str) and value.strip():
				return value.strip()

		# Ultimo tentativo: ultimo messaggio assistant in messages.
		messages = result.get("messages")
		if isinstance(messages, list):
			for item in reversed(messages):
				if isinstance(item, dict) and item.get("role") == "assistant":
					content = item.get("content", "")
					if isinstance(content, str) and content.strip():
						return content.strip()

		return ""

	@staticmethod
	def _run_async_safely(coro: Any) -> Any:
		"""Esegue coroutine in modo compatibile con runtime diversi."""
		try:
			return asyncio.run(coro)
		except RuntimeError:
			# Se esiste gia un event loop attivo, creiamo un loop dedicato.
			new_loop = asyncio.new_event_loop()
			try:
				return new_loop.run_until_complete(coro)
			finally:
				new_loop.close()

	@staticmethod
	def _safe_history_from_session(session_attributes: Dict[str, Any]) -> List[Dict[str, str]]:
		"""Recupera history dalla sessione Alexa in formato sicuro e limitato."""
		history = session_attributes.get("history", [])
		if not isinstance(history, list):
			return []

		normalized_history: List[Dict[str, str]] = []
		for item in history[-24:]:
			if not isinstance(item, dict):
				continue
			role = item.get("role")
			content = item.get("content")
			if role in {"user", "assistant"} and isinstance(content, str):
				normalized_history.append({"role": role, "content": content[:600]})
		return normalized_history

	@staticmethod
	def _build_structured_prompt(sanitized_user_input: str, locale: str) -> str:
		"""Crea prompt strutturato con separazione esplicita input/istruzioni."""
		return (
			"### SYSTEM_INSTRUCTIONS\n"
			f"{SYSTEM_INSTRUCTIONS}\n\n"
			"### SECURITY_CONSTRAINTS\n"
			"- Accesso consentito: solo chat conversazionale su agronomia\n"
			"- Accesso negato: sensori, immagini, quantum, training, admin, export, delete\n"
			"- Se la richiesta e fuori policy: rifiuta e reindirizza a Telegram\n\n"
			"### USER_CONTEXT\n"
			f"locale={locale}\n\n"
			"### USER_INPUT\n"
			f"{sanitized_user_input}\n"
		)
