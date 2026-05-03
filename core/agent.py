"""
DELTA - core/agent.py
Orchestratore principale del sistema DELTA Plant.
Coordina sensori, visione artificiale, AI e diagnosi tramite multithreading.
"""

import threading
import time
import logging
from datetime import datetime
from typing import Optional, Dict, Any

import numpy as np

from core.config import SENSOR_CONFIG, MODEL_CONFIG, ORGAN_CONFIG
from sensors.reader import SensorReader
from sensors.filtering import SensorFilter
from sensors.anomaly_detection import AnomalyDetector
from vision.camera import CameraModule
from vision.preprocessing import Preprocessor
from vision.segmentation import LeafSegmentor, FlowerSegmentor, FruitSegmentor
from vision.organ_detector import PlantOrganDetector
from ai.model_loader import ModelLoader
from ai.inference import PlantInference
from diagnosis.engine import DiagnosisEngine
from recommendations.agronomy_engine import AgronomyEngine
from data.database import Database
from data.excel_export import ExcelExporter
from data.logger import setup_logger

logger = logging.getLogger("delta.agent")


class DeltaAgent:
    """
    Orchestratore principale DELTA Plant.
    Gestisce il ciclo di vita completo: acquisizione dati,
    inferenza, diagnosi e raccomandazioni.
    """

    def __init__(self):
        logger.info("Inizializzazione DELTA Agent...")

        # ── Moduli core ──────────────────────────────────────
        self.sensor_reader = SensorReader()
        self.sensor_filter = SensorFilter(window=SENSOR_CONFIG["smoothing_window"])
        self.anomaly_detector = AnomalyDetector()
        self.camera = CameraModule()
        self.preprocessor = Preprocessor()
        self.segmentor = LeafSegmentor()
        self.flower_segmentor = FlowerSegmentor()
        self.fruit_segmentor = FruitSegmentor()
        self.organ_detector = PlantOrganDetector()
        self.model_loader = ModelLoader()
        self.inference_engine = PlantInference(self.model_loader)
        self.diagnosis_engine = DiagnosisEngine()
        self.agronomy_engine = AgronomyEngine()
        self.database = Database()
        self.exporter = ExcelExporter()

        # ── Stato interno ────────────────────────────────────
        self._running = False
        self._latest_sensor_data: Dict[str, Any] = {}
        self._lock = threading.Lock()
        self._sensor_thread: Optional[threading.Thread] = None

        logger.info("DELTA Agent inizializzato correttamente.")

    # ─────────────────────────────────────────────
    # CICLO SENSORI (background thread)
    # ─────────────────────────────────────────────

    def _sensor_loop(self):
        """Thread continuo di lettura sensori con smoothing e anomaly detection."""
        logger.info("Thread sensori avviato.")
        interval = SENSOR_CONFIG["read_interval_sec"]

        while self._running:
            try:
                raw = self.sensor_reader.read_all()
                smoothed = self.sensor_filter.apply(raw)
                anomalies = self.anomaly_detector.check(smoothed)

                if anomalies:
                    logger.warning("Anomalie sensori rilevate: %s", anomalies)

                with self._lock:
                    self._latest_sensor_data = smoothed
                    self._latest_sensor_data["_anomalies"] = anomalies

            except Exception as exc:
                logger.error("Errore lettura sensori: %s", exc, exc_info=True)

            time.sleep(interval)

    def start_sensor_thread(self):
        """Avvia il thread di lettura continua dei sensori."""
        self._running = True
        self._sensor_thread = threading.Thread(
            target=self._sensor_loop,
            name="SensorThread",
            daemon=True,
        )
        self._sensor_thread.start()
        logger.info("Thread sensori in esecuzione (intervallo: %ds).",
                    SENSOR_CONFIG["read_interval_sec"])

    def stop_sensor_thread(self):
        """Ferma il thread sensori in modo pulito."""
        self._running = False
        if self._sensor_thread and self._sensor_thread.is_alive():
            self._sensor_thread.join(timeout=5)
        logger.info("Thread sensori fermato.")

    # ─────────────────────────────────────────────
    # DIAGNOSI COMPLETA
    # ─────────────────────────────────────────────

    def run_diagnosis(self, sensor_data: Optional[Dict[str, Any]] = None,
                      image: Optional[np.ndarray] = None) -> Dict[str, Any]:
        """
        Esegue una diagnosi completa:
        1. Acquisisce immagine dalla camera (o usa quella fornita)
        2. Segmenta la foglia
        3. Esegue inferenza AI
        4. Combina con dati sensori
        5. Genera diagnosi e raccomandazioni
        6. Persiste su database e Excel

        Args:
            sensor_data: dati sensori opzionali (usa ultimi disponibili se None)
            image: array numpy BGR opzionale. Se fornito salta l'acquisizione camera.

        Returns:
            dict con diagnosi completa
        """
        logger.info("Avvio diagnosi completa...")
        timestamp = datetime.utcnow().isoformat()

        # ── 1. Dati sensori ──────────────────────────────────
        if sensor_data is None:
            with self._lock:
                sensor_data = dict(self._latest_sensor_data)

        if not sensor_data:
            logger.warning("Nessun dato sensore disponibile - lettura istantanea.")
            sensor_data = self.sensor_reader.read_all()

        # ── 2. Acquisizione immagine ─────────────────────────
        if image is not None:
            logger.info("Usando immagine fornita esternamente (modalità cartella input).")
        else:
            image = self.camera.capture_frame()
        if image is None:
            logger.error("Acquisizione immagine fallita.")
            raise RuntimeError("Impossibile acquisire immagine dalla camera.")

        # ── 3. Rilevamento multi-organo ───────────────────────
        organ_results = self.organ_detector.detect_all(image)
        detected_organs = [o for o, r in organ_results.items() if r.detected]
        logger.info("Organi rilevati: %s", detected_organs or ["foglia (default)"])

        # ── 4. Segmentazione foglia ──────────────────────────
        leaf_mask, leaf_roi = self.segmentor.segment(image)
        target_image = leaf_roi if leaf_roi is not None else image

        # ── 5. Segmentazione fiore (se rilevato) ─────────────
        organ_analyses: Dict[str, Any] = {}
        # v3.0: Flower analysis disabled in leaf-only mode
        if not MODEL_CONFIG.get("leaf_only_mode", False):
            if organ_results.get("fiore") and organ_results["fiore"].detected:
                flower_roi = organ_results["fiore"].roi
                if flower_roi is not None:
                    flower_processed = self.preprocessor.prepare_for_inference(flower_roi)
                    flower_ai = self.inference_engine.predict(
                        flower_processed, sensor_data, label_set="flower"
                    )
                    organ_analyses["fiore"] = flower_ai
                    logger.info("Analisi fiore: %s (%.1f%%)",
                                flower_ai.get("class"), flower_ai.get("confidence", 0) * 100)

        # ── 6. Segmentazione frutto (se rilevato) ────────────
        # v3.0: Fruit analysis disabled in leaf-only mode
        if not MODEL_CONFIG.get("leaf_only_mode", False):
            if organ_results.get("frutto") and organ_results["frutto"].detected:
                fruit_roi = organ_results["frutto"].roi
                if fruit_roi is not None:
                    fruit_processed = self.preprocessor.prepare_for_inference(fruit_roi)
                    fruit_ai = self.inference_engine.predict(
                        fruit_processed, sensor_data, label_set="fruit"
                    )
                    organ_analyses["frutto"] = fruit_ai
                    logger.info("Analisi frutto: %s (%.1f%%)",
                                fruit_ai.get("class"), fruit_ai.get("confidence", 0) * 100)

        # ── 7. Preprocessing foglia ───────────────────────────
        processed = self.preprocessor.prepare_for_inference(target_image)

        # ── 8. Inferenza AI foglia ────────────────────────────
        ai_result = self.inference_engine.predict(processed, sensor_data)
        logger.info("Inferenza AI foglia: %s (%.1f%%)",
                    ai_result["class"], ai_result["confidence"] * 100)

        # ── 9. Active learning: bassa confidenza o healthy specifico ──
        ai_class_norm = str(ai_result.get("class", "")).strip().lower()
        crop_specific_healthy = ai_class_norm.endswith("_healthy") and ai_class_norm != "healthy"

        if ai_result["confidence"] < MODEL_CONFIG["low_confidence_threshold"]:
            if ai_result.get("simulated"):
                logger.info("Confidenza bassa (%.1f%%) su output simulato — nessun modello reale.",
                            ai_result["confidence"] * 100)
            else:
                logger.warning("Confidenza bassa (%.1f%%) - richiesto input utente.",
                               ai_result["confidence"] * 100)
            ai_result["needs_human_review"] = True
        elif crop_specific_healthy:
            logger.info(
                "Classe healthy specifica (%s): attivo revisione umana per verifica specie.",
                ai_result.get("class"),
            )
            ai_result["needs_human_review"] = True
        else:
            ai_result["needs_human_review"] = False

        # ── 10. Diagnosi combinata + Quantum Oracle ───────────
        diagnosis = self.diagnosis_engine.diagnose(ai_result, sensor_data, organ_analyses)

        # ── 11. Raccomandazioni ──────────────────────────────
        recommendations = self.agronomy_engine.generate(diagnosis, sensor_data)

        # ── 12. Record completo ──────────────────────────────
        record = {
            "timestamp": timestamp,
            "sensor_data": sensor_data,
            "organ_results": {
                k: {
                    "detected": v.detected,
                    "coverage_ratio": round(v.coverage_ratio, 4),
                    "n_bboxes": len(v.bounding_boxes),
                }
                for k, v in organ_results.items()
            },
            "ai_result": ai_result,
            "organ_analyses": organ_analyses,
            "diagnosis": diagnosis,
            "recommendations": recommendations,
        }

        # ── 13. Persistenza ───────────────────────────────────
        try:
            self.database.save_record(record)
            self.exporter.append_record(record)
        except Exception as exc:
            logger.error("Errore persistenza dati: %s", exc, exc_info=True)

        logger.info("Diagnosi completata: %s", diagnosis.get("summary", "N/A"))
        return record

    # ─────────────────────────────────────────────
    # UTILITÀ
    # ─────────────────────────────────────────────

    def get_latest_sensor_data(self) -> Dict[str, Any]:
        """Restituisce gli ultimi dati sensori acquisiti."""
        with self._lock:
            return dict(self._latest_sensor_data)

    def shutdown(self):
        """Spegne l'agent in modo ordinato."""
        logger.info("Shutdown DELTA Agent...")
        self.stop_sensor_thread()
        self.camera.release()
        self.database.close()
        logger.info("DELTA Agent spento.")
