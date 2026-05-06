"""Endpoint Flask dedicato per DELTA Plant Alexa Chat: /api/alexa/chat.

Questo endpoint permette di integrare la logica conversazionale della skill
Alexa anche in contesti HTTP (es. test locale, integrazione con altri sistemi
autorizzati). NON e un endpoint pubblico: deve essere protetto a livello
infrastrutturale (VPN, token API, o rate limiter a monte).

Caratteristiche di sicurezza:
- verifica header X-Alexa-Skill-Id (opzionale, raccomandato in produzione)
- pipeline completa input_sanitizer -> orchestrator -> output_guard
- nessun dato sensibile nei log HTTP
- risposta JSON strutturata con campo 'blocked' per diagnostica
- timeout impostato dalla configurazione centrale

Uso previsto:
  Registrare il blueprint sull'app Flask principale di DELTA:
    from delta_plant_alexa.flask_endpoint.alexa_chat_endpoint import alexa_chat_bp
    app.register_blueprint(alexa_chat_bp)
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional

from flask import Blueprint, Request, jsonify, request

from delta_plant_alexa.config import SECURITY_CONFIG
from delta_plant_alexa.utils.delta_orchestrator_client import DeltaOrchestratorClient


LOGGER = logging.getLogger(__name__)

# Blueprint registrabile sull'app Flask principale.
alexa_chat_bp = Blueprint("alexa_chat", __name__, url_prefix="/api/alexa")

# Client condiviso per riuso tra richieste (stateless, sicuro).
_orchestrator_client = DeltaOrchestratorClient()

# Skill ID di riferimento per verifica header opzionale.
_EXPECTED_SKILL_ID: str = SECURITY_CONFIG.alexa_skill_id


@alexa_chat_bp.route("/chat", methods=["POST"])
def alexa_chat() -> Any:
    """Endpoint POST /api/alexa/chat: elabora messaggio conversazionale.

    Request body JSON:
        {
          "message": "Come posso trattare la peronospora?",
          "session_id": "test-session-001",       # obbligatorio
          "locale": "it-IT"                        # opzionale, default it-IT
        }

    Response JSON:
        {
          "answer": "...",
          "blocked": false,
          "reason": ""
        }
    """
    # 1) Verifica Content-Type per prevenire CSRF e parsing errato.
    if not request.is_json:
        LOGGER.warning("/api/alexa/chat: Content-Type non JSON")
        return jsonify({"error": "Content-Type deve essere application/json"}), 415

    # 2) Verifica opzionale Skill ID da header custom per ambienti protetti.
    _check_skill_id_header(request)

    # 3) Parsing body con limiti espliciti.
    try:
        body: Dict[str, Any] = request.get_json(force=False, silent=True) or {}
    except Exception:
        return jsonify({"error": "Body JSON non valido"}), 400

    user_message: str = str(body.get("message", "")).strip()
    session_id: str = str(body.get("session_id", "")).strip()
    locale: str = str(body.get("locale", "it-IT")).strip()

    if not session_id:
        return jsonify({"error": "Campo 'session_id' obbligatorio"}), 400

    if not user_message:
        return jsonify({"error": "Campo 'message' obbligatorio"}), 400

    # 4) Limite lunghezza input lato HTTP prima ancora della sanitizzazione.
    if len(user_message) > SECURITY_CONFIG.max_user_input_chars:
        return jsonify({"error": "Messaggio troppo lungo"}), 400

    # 5) Pipeline completa sicurezza tramite client orchestrator.
    result = _orchestrator_client.process_chat(
        user_text=user_message,
        session_id=session_id,
        locale=locale,
        session_attributes={},
    )

    LOGGER.info(
        "/api/alexa/chat session=%s locale=%s blocked=%s",
        session_id,
        locale,
        result.blocked,
    )

    return jsonify({
        "answer": result.answer_text,
        "blocked": result.blocked,
        "reason": result.reason if result.blocked else "",
    })


def _check_skill_id_header(req: Request) -> None:
    """Verifica header X-Alexa-Skill-Id se DELTA_ALEXA_SKILL_ID e configurato.

    Non blocca la richiesta in assenza dell'header (retrocompatibilita con
    test locali), ma logga un avviso. In produzione, applicare un firewall
    a monte che garantisca la presenza e correttezza dell'header.
    """
    if not _EXPECTED_SKILL_ID:
        return
    incoming_id = req.headers.get("X-Alexa-Skill-Id", "")
    if incoming_id and incoming_id != _EXPECTED_SKILL_ID:
        LOGGER.warning(
            "/api/alexa/chat: Skill-Id header mismatch incoming=%s",
            incoming_id,
        )

