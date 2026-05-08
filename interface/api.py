"""
DELTA - interface/api.py
API REST locale opzionale tramite Flask.
Espone endpoint per diagnosi, dati sensori e record storici.
Abilitare in core/config.py → API_CONFIG["enable_api"] = True
"""

import json
import logging
from typing import TYPE_CHECKING

from core.config import API_CONFIG

if TYPE_CHECKING:
    from core.agent import DeltaAgent

logger = logging.getLogger("delta.interface.api")


def create_app(agent: "DeltaAgent"):
    """
    Factory dell'applicazione Flask.

    Args:
        agent: istanza DeltaAgent già inizializzata

    Returns:
        app Flask configurata
    """
    try:
        from flask import Flask, jsonify, request, abort  # type: ignore
    except ImportError:
        logger.error("Flask non installato. API non disponibile.")
        raise ImportError(
            "Flask è richiesto per l'API. Installare con: pip install flask"
        )

    app = Flask("delta_api")
    # Disabilita sorting automatico JSON per mantenere l'ordine
    app.json.sort_keys = False

    # ─────────────────────────────────────────────
    # HEALTH CHECK
    # ─────────────────────────────────────────────

    @app.get("/health")
    def health():
        """Stato del sistema."""
        return jsonify({
            "status": "ok",
            "model_ready": agent.model_loader.is_ready(),
            "sensor_hw": agent.sensor_reader._hw_available,
            "db_records": agent.database.count(),
        })

    # ─────────────────────────────────────────────
    # DIAGNOSI
    # ─────────────────────────────────────────────

    @app.post("/diagnose")
    def diagnose():
        """
        Avvia una nuova diagnosi.
        Body JSON opzionale: { "sensor_data": { ... } }
        """
        payload = request.get_json(silent=True) or {}
        sensor_data = payload.get("sensor_data")

        try:
            record = agent.run_diagnosis(sensor_data=sensor_data)
            return jsonify(record), 200
        except Exception as exc:
            logger.error("Errore API /diagnose: %s", exc, exc_info=True)
            return jsonify({"error": str(exc)}), 500

    # ─────────────────────────────────────────────
    # SENSORI
    # ─────────────────────────────────────────────

    @app.get("/sensors")
    def sensors():
        """Restituisce i dati sensori più recenti."""
        data = agent.get_latest_sensor_data()
        # Rimuovi chiave interna
        data.pop("_anomalies", None)
        return jsonify(data)

    @app.get("/sensors/read")
    def sensors_read():
        """Forza una nuova lettura istantanea dei sensori."""
        try:
            data = agent.sensor_reader.read_all()
            smoothed = agent.sensor_filter.apply(data)
            smoothed.pop("_anomalies", None)
            return jsonify(smoothed)
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

    # ─────────────────────────────────────────────
    # STORICO
    # ─────────────────────────────────────────────

    @app.get("/diagnoses")
    def diagnoses_list():
        """
        Restituisce le ultime N diagnosi.
        Query param: ?limit=50
        """
        limit = min(int(request.args.get("limit", 50)), 500)
        records = agent.database.get_recent(limit=limit)
        return jsonify(records)

    @app.get("/diagnoses/<int:record_id>")
    def diagnosis_by_id(record_id: int):
        """Restituisce un singolo record per ID."""
        record = agent.database.get_by_id(record_id)
        if record is None:
            abort(404)
        return jsonify(record)

    # ─────────────────────────────────────────────
    # MODELLO
    # ─────────────────────────────────────────────

    @app.get("/model/info")
    def model_info():
        """Informazioni sul modello AI caricato."""
        vision_service = getattr(agent, "vision_service", None)
        return jsonify({
            "ready": agent.model_loader.is_ready(),
            "labels": agent.model_loader.labels,
            "input_shape": agent.model_loader.get_input_shape(),
            "backend": agent.model_loader._backend if hasattr(
                agent.model_loader, "_backend"
            ) else "unknown",
            "active_model": vision_service.active_model if vision_service else "legacy",
            "vision_backend": vision_service.backend_type if vision_service else "legacy",
            "explainability": vision_service.can_explain if vision_service else False,
        })

    return app


def run_api(agent: "DeltaAgent"):
    """
    Avvia il server Flask in un thread daemon separato.
    Chiamare solo se API_CONFIG["enable_api"] è True.
    """
    import threading

    if not API_CONFIG.get("enable_api", False):
        logger.info("API Flask disabilitata nella configurazione.")
        return

    try:
        app = create_app(agent)
    except ImportError:
        return

    def _serve():
        app.run(
            host=API_CONFIG["host"],
            port=API_CONFIG["port"],
            debug=API_CONFIG["debug"],
            use_reloader=False,
        )

    thread = threading.Thread(target=_serve, name="FlaskAPI", daemon=True)
    thread.start()
    logger.info(
        "API Flask avviata su http://%s:%d",
        API_CONFIG["host"],
        API_CONFIG["port"],
    )
