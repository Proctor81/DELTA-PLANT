"""
DELTA - diagnosis/engine.py
Motore di diagnosi principale.
Combina output AI (Computer Vision), analisi multi-organo e dati sensori
tramite il sistema rule-based e l'Oracolo Quantistico di Grover.
"""

import logging
from typing import Dict, Any, List, Optional

from diagnosis.rules import evaluate_all_rules, get_overall_risk, RISK_NONE
from ai.quantum_risk import GroverRiskOracle

logger = logging.getLogger("delta.diagnosis.engine")


class DiagnosisEngine:
    """
    Genera una diagnosi agronomica strutturata combinando:
    - Predizione del modello AI per foglia (classe, confidenza)
    - Predizione AI per fiore e/o frutto (se rilevati)
    - Dati ambientali dai sensori
    - Sistema di regole esperte (foglia + fiore + frutto)
    - Oracolo Quantistico di Grover per quantificazione del rischio
    """

    def __init__(self):
        self._grover = GroverRiskOracle()

    def diagnose(
        self,
        ai_result: Dict[str, Any],
        sensor_data: Dict[str, Any],
        organ_analyses: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Esegue la diagnosi completa.

        Args:
            ai_result:      output dell'inferenza AI foglia
            sensor_data:    dati smoothed dai sensori ambientali
            organ_analyses: dict opzionale con chiavi 'fiore' e/o 'frutto',
                            ognuno con {'class', 'confidence', 'above_threshold'}

        Returns:
            dict strutturato con tutti i dettagli diagnostici
        """
        logger.debug("Avvio diagnosi combinata (multi-organo + Grover)...")

        organ_analyses = organ_analyses or {}

        # Arricchisci ai_result con informazioni organi per le regole
        # v3.0: Flower/fruit enrichment disabled in leaf-only mode
        enriched_ai = dict(ai_result)
        if "fiore" in organ_analyses:
            enriched_ai["flower_detected"] = True
            enriched_ai["flower_result"] = organ_analyses["fiore"]
        else:
            enriched_ai["flower_detected"] = False
        if "frutto" in organ_analyses:
            enriched_ai["fruit_detected"] = True
            enriched_ai["fruit_result"] = organ_analyses["frutto"]
        else:
            enriched_ai["fruit_detected"] = False

        # ── 1. Valutazione regole ────────────────────────────
        activated_rules = evaluate_all_rules(sensor_data, enriched_ai)
        overall_risk = get_overall_risk(activated_rules)

        # ── 2. Oracolo Quantistico di Grover ─────────────────
        rule_ids = [r.rule_id for r in activated_rules]
        quantum_result = self._grover.quantify_risk(rule_ids, organ_analyses, sensor_data)

        # ── 3. Stato pianta ──────────────────────────────────
        plant_status = self._determine_plant_status(enriched_ai, overall_risk)

        # ── 4. Messaggi diagnostici ──────────────────────────
        findings = [
            {"rule_id": r.rule_id, "description": r.description, "risk": r.risk_level}
            for r in activated_rules
        ]

        # ── 5. Spiegazione narrativa ──────────────────────────
        explanation = self._build_explanation(
            enriched_ai, sensor_data, activated_rules, organ_analyses, quantum_result
        )

        # ── 6. Riepilogo breve ───────────────────────────────
        summary = self._build_summary(plant_status, overall_risk, activated_rules, quantum_result)

        diagnosis = {
            "plant_status": plant_status,
            "overall_risk": overall_risk,
            "ai_class": ai_result.get("class", "N/A"),
            "ai_confidence": round(ai_result.get("confidence", 0.0) * 100, 1),
            "ai_simulated": ai_result.get("simulated", False),
            "needs_human_review": ai_result.get("needs_human_review", False),
            "organ_analyses": organ_analyses,
            "activated_rules": findings,
            "quantum_risk": quantum_result,
            "explanation": explanation,
            "summary": summary,
            "sensor_snapshot": self._sensor_snapshot(sensor_data),
        }

        logger.info(
            "Diagnosi: stato=%s, rischio=%s, QRS=%.3f, regole=%d attive.",
            plant_status, overall_risk,
            quantum_result.get("quantum_risk_score", 0.0),
            len(activated_rules),
        )
        return diagnosis

    # ─────────────────────────────────────────────
    # STATO PIANTA
    # ─────────────────────────────────────────────

    @staticmethod
    def _determine_plant_status(ai_result: Dict[str, Any], overall_risk: str) -> str:
        """Determina lo stato generale della pianta in linguaggio naturale."""
        def is_healthy_label(label: str) -> bool:
            normalized = (label or "").strip().lower()
            if not normalized:
                return False
            healthy_aliases = {"sano", "fiore_sano", "frutto_sano", "healthy"}
            if normalized in healthy_aliases:
                return True
            return normalized.endswith("_healthy") or normalized.endswith("_sano")

        def is_crop_specific_healthy(label: str) -> bool:
            normalized = (label or "").strip().lower()
            return normalized.endswith("_healthy") and normalized not in {"healthy"}

        ai_class = ai_result.get("class", "Sano")
        above_threshold = ai_result.get("above_threshold", False)

        flower_result = ai_result.get("flower_result", {})
        fruit_result  = ai_result.get("fruit_result", {})

        # Controlla patologie specifiche di fiore/frutto
        flower_cls = flower_result.get("class", "Fiore_sano") if flower_result else "Fiore_sano"
        fruit_cls  = fruit_result.get("class",  "Frutto_sano") if fruit_result else "Frutto_sano"

        if overall_risk == "critico":
            return "Critico"
        elif is_healthy_label(ai_class) and is_healthy_label(flower_cls) and is_healthy_label(fruit_cls):
            if is_crop_specific_healthy(ai_class) and overall_risk in (RISK_NONE, "basso"):
                return "Sano con verifica specie"
            if overall_risk in (RISK_NONE, "basso"):
                return "Ottimale"
            elif overall_risk == "medio":
                return "Buono con riserva"
        elif (not is_healthy_label(ai_class)) and above_threshold:
            return f"Patologico - {ai_class}"
        elif (not is_healthy_label(flower_cls)) and flower_result.get("above_threshold", False):
            return f"Fiore compromesso - {flower_cls}"
        elif (not is_healthy_label(fruit_cls)) and fruit_result.get("above_threshold", False):
            return f"Frutto compromesso - {fruit_cls}"
        elif overall_risk == "alto":
            return "Compromesso"
        else:
            return "Da monitorare"

    # ─────────────────────────────────────────────
    # SPIEGAZIONE NARRATIVA
    # ─────────────────────────────────────────────

    @staticmethod
    def _build_explanation(
        ai_result: Dict[str, Any],
        sensor_data: Dict[str, Any],
        activated_rules,
        organ_analyses: Dict[str, Any],
        quantum_result: Dict[str, Any],
    ) -> str:
        """Genera una spiegazione narrativa leggibile della diagnosi."""
        lines = []

        # AI Vision — foglia
        cls = ai_result.get("class", "N/A")
        conf = ai_result.get("confidence", 0.0) * 100
        simulated = ai_result.get("simulated", False)
        sim_note = " [SIMULATO]" if simulated else ""
        lines.append(
            f"Analisi foglia{sim_note}: '{cls}' con confidenza {conf:.1f}%."
        )
        if str(cls).strip().lower().endswith("_healthy"):
            lines.append(
                "Nota: classe healthy specifica di coltura. Se la specie osservata non coincide,"
                " trattare il risultato come indicativo e richiedere verifica manuale."
            )

        # AI Vision — fiore
        if "fiore" in organ_analyses:
            fr = organ_analyses["fiore"]
            lines.append(
                f"Analisi fiore: '{fr.get('class','N/A')}' "
                f"({fr.get('confidence',0)*100:.1f}% confidenza)."
            )

        # AI Vision — frutto
        if "frutto" in organ_analyses:
            fr = organ_analyses["frutto"]
            lines.append(
                f"Analisi frutto: '{fr.get('class','N/A')}' "
                f"({fr.get('confidence',0)*100:.1f}% confidenza)."
            )

        # Oracolo Quantistico
        qrs  = quantum_result.get("quantum_risk_score", 0.0)
        qlvl = quantum_result.get("risk_level", "nessuno")
        doms = quantum_result.get("dominant_description", "")
        gain = quantum_result.get("amplification_gain", 1.0)
        lines.append(
            f"Oracolo Quantistico di Grover: QRS={qrs:.3f} [{qlvl.upper()}] | "
            f"Evento dominante: {doms} | Amplificazione: {gain:.1f}x."
        )

        # Condizioni ambientali
        temp = sensor_data.get("temperature_c")
        hum  = sensor_data.get("humidity_pct")
        light = sensor_data.get("light_lux")
        co2  = sensor_data.get("co2_ppm")
        ph   = sensor_data.get("ph")
        ec   = sensor_data.get("ec_ms_cm")

        env_parts = []
        if temp is not None:  env_parts.append(f"Temperatura: {temp:.1f}°C")
        if hum  is not None:  env_parts.append(f"Umidità: {hum:.1f}%")
        if light is not None: env_parts.append(f"Luminosità: {light:.0f} lux")
        if co2  is not None:  env_parts.append(f"CO₂: {co2:.0f} ppm")
        if ph   is not None:  env_parts.append(f"pH: {ph:.2f}")
        if ec   is not None:  env_parts.append(f"EC: {ec:.2f} mS/cm")

        if env_parts:
            lines.append("Condizioni ambientali: " + " | ".join(env_parts) + ".")

        # Regole attivate
        if activated_rules:
            lines.append("Criticità rilevate:")
            for rule in activated_rules:
                risk_label = rule.risk_level.upper()
                lines.append(f"  [{risk_label}] {rule.description}")
        else:
            lines.append("Nessuna criticità rilevata dal sistema di regole.")

        return "\n".join(lines)

    # ─────────────────────────────────────────────
    # RIEPILOGO BREVE
    # ─────────────────────────────────────────────

    @staticmethod
    def _build_summary(
        plant_status: str,
        overall_risk: str,
        activated_rules,
        quantum_result: Dict[str, Any],
    ) -> str:
        """Genera una riga di riepilogo concisa."""
        n = len(activated_rules)
        qrs = quantum_result.get("quantum_risk_score", 0.0)
        qlvl = quantum_result.get("risk_level", "nessuno")
        return (
            f"Stato: {plant_status} | Rischio: {overall_risk.upper()} | "
            f"QRS Grover: {qrs:.3f} [{qlvl.upper()}] | "
            f"Problemi rilevati: {n}"
        )

    # ─────────────────────────────────────────────
    # SNAPSHOT SENSORI
    # ─────────────────────────────────────────────

    @staticmethod
    def _sensor_snapshot(sensor_data: Dict[str, Any]) -> Dict[str, Any]:
        """Estrae un dizionario pulito dei valori sensori per la persistenza."""
        fields = [
            "temperature_c", "humidity_pct", "pressure_hpa",
            "light_lux", "co2_ppm", "ph", "ec_ms_cm", "source",
        ]
        return {f: sensor_data.get(f) for f in fields}
