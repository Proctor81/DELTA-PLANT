"""
DELTA - data/database.py
Gestione persistenza SQLite per diagnosi, dati sensori e raccomandazioni.
Schema normalizzato con timestamp ISO 8601 e dati JSON strutturati.
"""

import json
import logging
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, List, Optional

from core.config import DATABASE_CONFIG

logger = logging.getLogger("delta.data.database")

DEFAULT_RETENTION_DAYS = 30

# Schema DDL
CREATE_DIAGNOSES_TABLE = """
CREATE TABLE IF NOT EXISTS diagnoses (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp         TEXT NOT NULL,
    -- Sensori
    temperature_c     REAL,
    humidity_pct      REAL,
    pressure_hpa      REAL,
    light_lux         REAL,
    co2_ppm           REAL,
    ph                REAL,
    ec_ms_cm          REAL,
    sensor_source     TEXT,
    -- AI
    ai_class          TEXT,
    ai_confidence     REAL,
    ai_simulated      INTEGER DEFAULT 0,
    ai_top3_json      TEXT,
    -- Diagnosi
    plant_status      TEXT,
    overall_risk      TEXT,
    needs_review      INTEGER DEFAULT 0,
    explanation       TEXT,
    summary           TEXT,
    activated_rules   TEXT,
    -- Raccomandazioni
    recommendations   TEXT,
    -- Meta
    created_at        TEXT DEFAULT (datetime('now','utc'))
);
"""

CREATE_INDEX = """
CREATE INDEX IF NOT EXISTS idx_diagnoses_timestamp ON diagnoses(timestamp);
"""


class Database:
    """
    Gestisce il database SQLite per la persistenza dei record DELTA.
    Thread-safe: usa check_same_thread=False con locking applicativo.
    """

    def __init__(self):
        db_path = Path(DATABASE_CONFIG["db_path"])
        db_path.parent.mkdir(parents=True, exist_ok=True)

        self._conn = sqlite3.connect(
            str(db_path),
            check_same_thread=False,
            detect_types=sqlite3.PARSE_DECLTYPES,
        )
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL;")
        self._conn.execute("PRAGMA foreign_keys=ON;")
        self._init_schema()
        logger.info("Database SQLite aperto: %s", db_path)

    def _init_schema(self):
        """Crea le tabelle se non esistono."""
        with self._conn:
            self._conn.execute(CREATE_DIAGNOSES_TABLE)
            self._conn.execute(CREATE_INDEX)

    # ─────────────────────────────────────────────
    # SCRITTURA
    # ─────────────────────────────────────────────

    def save_record(self, record: Dict[str, Any]) -> int:
        """
        Salva un record completo di diagnosi nel database.

        Args:
            record: dict con chiavi 'timestamp', 'sensor_data', 'ai_result',
                    'diagnosis', 'recommendations'

        Returns:
            ID del record inserito
        """
        sd = record.get("sensor_data", {})
        ai = record.get("ai_result", {})
        dx = record.get("diagnosis", {})
        recs = record.get("recommendations", [])
        snap = dx.get("sensor_snapshot", sd)

        row = {
            "timestamp":        record.get("timestamp", datetime.utcnow().isoformat()),
            "temperature_c":    snap.get("temperature_c"),
            "humidity_pct":     snap.get("humidity_pct"),
            "pressure_hpa":     snap.get("pressure_hpa"),
            "light_lux":        snap.get("light_lux"),
            "co2_ppm":          snap.get("co2_ppm"),
            "ph":               snap.get("ph"),
            "ec_ms_cm":         snap.get("ec_ms_cm"),
            "sensor_source":    str(snap.get("source") or ""),
            "ai_class":         str(ai.get("class") or ""),
            "ai_confidence":    float(ai.get("confidence") or 0.0),
            "ai_simulated":     1 if ai.get("simulated") else 0,
            "ai_top3_json":     json.dumps(ai.get("top3", []), ensure_ascii=False),
            "plant_status":     str(dx.get("plant_status") or ""),
            "overall_risk":     str(dx.get("overall_risk") or ""),
            "needs_review":     1 if dx.get("needs_human_review") else 0,
            "explanation":      str(dx.get("explanation") or ""),
            "summary":          str(dx.get("summary") or ""),
            "activated_rules":  json.dumps(dx.get("activated_rules", []), ensure_ascii=False),
            "recommendations":  json.dumps(recs, ensure_ascii=False),
        }

        sql = """
        INSERT INTO diagnoses (
            timestamp, temperature_c, humidity_pct, pressure_hpa,
            light_lux, co2_ppm, ph, ec_ms_cm, sensor_source,
            ai_class, ai_confidence, ai_simulated, ai_top3_json,
            plant_status, overall_risk, needs_review,
            explanation, summary, activated_rules, recommendations
        ) VALUES (
            :timestamp, :temperature_c, :humidity_pct, :pressure_hpa,
            :light_lux, :co2_ppm, :ph, :ec_ms_cm, :sensor_source,
            :ai_class, :ai_confidence, :ai_simulated, :ai_top3_json,
            :plant_status, :overall_risk, :needs_review,
            :explanation, :summary, :activated_rules, :recommendations
        )
        """
        with self._conn:
            cursor = self._conn.execute(sql, row)
        record_id = cursor.lastrowid
        logger.debug("Record salvato nel DB con ID %d.", record_id)
        self.prune_older_than_days(DATABASE_CONFIG.get("retention_days", DEFAULT_RETENTION_DAYS))
        self._cleanup_old_records()
        return record_id

    # ─────────────────────────────────────────────
    # LETTURA
    # ─────────────────────────────────────────────

    def get_recent(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Restituisce gli ultimi N record di diagnosi."""
        sql = "SELECT * FROM diagnoses ORDER BY id DESC LIMIT ?"
        cursor = self._conn.execute(sql, (limit,))
        return [dict(row) for row in cursor.fetchall()]

    def get_records_since_days(
        self,
        days: int = DEFAULT_RETENTION_DAYS,
        *,
        now: Optional[datetime] = None,
    ) -> List[Dict[str, Any]]:
        """Restituisce i record compresi nella finestra mobile degli ultimi N giorni."""
        cutoff = (now or datetime.utcnow()) - timedelta(days=max(int(days), 1))
        sql = "SELECT * FROM diagnoses WHERE timestamp >= ? ORDER BY timestamp DESC, id DESC"
        cursor = self._conn.execute(sql, (cutoff.isoformat(),))
        return [dict(row) for row in cursor.fetchall()]

    def get_by_id(self, record_id: int) -> Optional[Dict[str, Any]]:
        """Restituisce un record specifico per ID."""
        sql = "SELECT * FROM diagnoses WHERE id = ?"
        row = self._conn.execute(sql, (record_id,)).fetchone()
        return dict(row) if row else None

    def count(self) -> int:
        """Restituisce il numero totale di record."""
        return self._conn.execute("SELECT COUNT(*) FROM diagnoses").fetchone()[0]

    # ─────────────────────────────────────────────
    # PULIZIA
    # ─────────────────────────────────────────────

    def _cleanup_old_records(self):
        """Rimuove i record più vecchi se il database supera il limite configurato."""
        max_records = DATABASE_CONFIG.get("max_records", 10000)
        current = self.count()
        if current > max_records:
            excess = current - max_records
            self._conn.execute(
                "DELETE FROM diagnoses WHERE id IN "
                "(SELECT id FROM diagnoses ORDER BY id ASC LIMIT ?)",
                (excess,),
            )
            self._conn.commit()
            logger.info("Pulizia DB: rimossi %d record vecchi.", excess)

    def prune_older_than_days(
        self,
        days: int = DEFAULT_RETENTION_DAYS,
        *,
        now: Optional[datetime] = None,
    ) -> int:
        """Cancella i record più vecchi della finestra mobile richiesta."""
        cutoff = (now or datetime.utcnow()) - timedelta(days=max(int(days), 1))
        with self._conn:
            cursor = self._conn.execute(
                "DELETE FROM diagnoses WHERE timestamp < ?",
                (cutoff.isoformat(),),
            )
        deleted = int(cursor.rowcount or 0)
        if deleted:
            logger.info("Pulizia DB retention: rimossi %d record oltre %d giorni.", deleted, days)
        return deleted

    # ─────────────────────────────────────────────
    # CHIUSURA
    # ─────────────────────────────────────────────

    def close(self):
        """Chiude la connessione al database."""
        try:
            self._conn.close()
            logger.info("Database SQLite chiuso.")
        except Exception as exc:
            logger.warning("Errore chiusura DB: %s", exc)

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass
