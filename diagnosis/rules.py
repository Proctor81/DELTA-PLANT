"""
DELTA - diagnosis/rules.py
Sistema rule-based agronomico.
Definisce regole esperte che combinano dati sensori e output AI
per generare diagnosi strutturate e livelli di rischio.
"""

from typing import Dict, Any, List, Tuple

from core.config import SENSOR_CONFIG


def _is_healthy_label(label: str) -> bool:
    """Riconosce le classi sane in modo robusto (italiano + PlantVillage)."""
    normalized = (label or "").strip().lower()
    if not normalized:
        return False

    healthy_aliases = {"sano", "fiore_sano", "frutto_sano", "healthy"}
    if normalized in healthy_aliases:
        return True

    return normalized.endswith("_healthy") or normalized.endswith("_sano")

# ─────────────────────────────────────────────
# LIVELLI DI RISCHIO
# ─────────────────────────────────────────────
RISK_NONE = "nessuno"
RISK_LOW = "basso"
RISK_MEDIUM = "medio"
RISK_HIGH = "alto"
RISK_CRITICAL = "critico"


class DiagnosisRule:
    """Rappresenta una singola regola diagnostica."""

    def __init__(self, rule_id: str, description: str, risk_level: str):
        self.rule_id = rule_id
        self.description = description
        self.risk_level = risk_level

    def evaluate(self, sensor_data: Dict[str, Any], ai_result: Dict[str, Any]) -> bool:
        """Valuta la regola. Override nelle sottoclassi."""
        raise NotImplementedError


# ─────────────────────────────────────────────
# REGOLE SPECIFICHE
# ─────────────────────────────────────────────

class FungalRiskRule(DiagnosisRule):
    """Rischio fungino: alta umidità + temperatura elevata."""

    def __init__(self):
        super().__init__(
            "FUNG_01",
            "Rischio sviluppo malattie fungine (alta umidità + temperatura elevata)",
            RISK_HIGH,
        )

    def evaluate(self, sensor_data, ai_result) -> bool:
        hum = sensor_data.get("humidity_pct")
        temp = sensor_data.get("temperature_c")
        if hum is None or temp is None:
            return False
        return (
            hum >= SENSOR_CONFIG["humidity_fungal_risk"]
            and temp >= SENSOR_CONFIG["temp_optimal_max"]
        )


class PhotosyntheticStressRule(DiagnosisRule):
    """Stress fotosintetico: bassa luminosità."""

    def __init__(self):
        super().__init__(
            "PHOTO_01",
            "Stress fotosintetico per carenza luminosa",
            RISK_MEDIUM,
        )

    def evaluate(self, sensor_data, ai_result) -> bool:
        light = sensor_data.get("light_lux")
        if light is None:
            return False
        return light < SENSOR_CONFIG["light_photosynthesis_min"]


class LightStressRule(DiagnosisRule):
    """Stress da eccesso luminoso (foto-inibizione)."""

    def __init__(self):
        super().__init__(
            "PHOTO_02",
            "Stress da eccesso luminoso (rischio foto-inibizione)",
            RISK_MEDIUM,
        )

    def evaluate(self, sensor_data, ai_result) -> bool:
        light = sensor_data.get("light_lux")
        if light is None:
            return False
        return light > SENSOR_CONFIG["light_stress_high"]


class Co2DeficiencyRule(DiagnosisRule):
    """Carenza CO2: crescita rallentata."""

    def __init__(self):
        super().__init__(
            "CO2_01",
            "Carenza CO2: crescita e fotosintesi rallentate",
            RISK_LOW,
        )

    def evaluate(self, sensor_data, ai_result) -> bool:
        co2 = sensor_data.get("co2_ppm")
        if co2 is None:
            return False
        return co2 < SENSOR_CONFIG["co2_optimal_min"]


class Co2ExcessRule(DiagnosisRule):
    """Eccesso CO2: possibile tossicità."""

    def __init__(self):
        super().__init__(
            "CO2_02",
            "Eccesso CO2: possibile tossicità e chiusura stomi",
            RISK_MEDIUM,
        )

    def evaluate(self, sensor_data, ai_result) -> bool:
        co2 = sensor_data.get("co2_ppm")
        if co2 is None:
            return False
        return co2 > SENSOR_CONFIG["co2_max"] * 0.7  # > 3500 ppm

    
class PhAcidRule(DiagnosisRule):
    """pH acido: blocco assorbimento nutrienti."""

    def __init__(self):
        super().__init__(
            "PH_01",
            "pH troppo acido: blocco assorbimento Ca, Mg, P",
            RISK_HIGH,
        )

    def evaluate(self, sensor_data, ai_result) -> bool:
        ph = sensor_data.get("ph")
        if ph is None:
            return False
        return ph < SENSOR_CONFIG["ph_optimal_min"]


class PhAlkalineRule(DiagnosisRule):
    """pH alcalino: carenza micronutrienti."""

    def __init__(self):
        super().__init__(
            "PH_02",
            "pH troppo alcalino: carenza Fe, Mn, Zn, Cu",
            RISK_HIGH,
        )

    def evaluate(self, sensor_data, ai_result) -> bool:
        ph = sensor_data.get("ph")
        if ph is None:
            return False
        return ph > SENSOR_CONFIG["ph_optimal_max"]


class EcToxicRule(DiagnosisRule):
    """EC eccessiva: tossicità salina."""

    def __init__(self):
        super().__init__(
            "EC_01",
            "Conducibilità elettrica eccessiva: stress osmotico e tossicità salina",
            RISK_CRITICAL,
        )

    def evaluate(self, sensor_data, ai_result) -> bool:
        ec = sensor_data.get("ec_ms_cm")
        if ec is None:
            return False
        return ec > SENSOR_CONFIG["ec_toxic"]


class EcLowRule(DiagnosisRule):
    """EC troppo bassa: carenza nutrienti."""

    def __init__(self):
        super().__init__(
            "EC_02",
            "Conducibilità elettrica bassa: carenza generalizzata di nutrienti",
            RISK_MEDIUM,
        )

    def evaluate(self, sensor_data, ai_result) -> bool:
        ec = sensor_data.get("ec_ms_cm")
        if ec is None:
            return False
        return ec < SENSOR_CONFIG["ec_optimal_min"]


class TemperatureStressRule(DiagnosisRule):
    """Temperatura fuori range ottimale."""

    def __init__(self):
        super().__init__(
            "TEMP_01",
            "Temperatura fuori range ottimale di crescita",
            RISK_MEDIUM,
        )

    def evaluate(self, sensor_data, ai_result) -> bool:
        temp = sensor_data.get("temperature_c")
        if temp is None:
            return False
        return (
            temp < SENSOR_CONFIG["temp_optimal_min"]
            or temp > SENSOR_CONFIG["temp_optimal_max"]
        )


class AiDiseaseRule(DiagnosisRule):
    """Malattia rilevata dall'AI con alta confidenza."""

    def __init__(self):
        super().__init__(
            "AI_01",
            "Malattia rilevata dal sistema di visione artificiale",
            RISK_HIGH,
        )

    def evaluate(self, sensor_data, ai_result) -> bool:
        cls = ai_result.get("class", "Sano")
        above_threshold = ai_result.get("above_threshold", False)
        return (not _is_healthy_label(cls)) and above_threshold


class AiLowConfidenceRule(DiagnosisRule):
    """Confidenza AI bassa: richiede revisione umana."""

    def __init__(self):
        super().__init__(
            "AI_02",
            "Confidenza AI insufficiente: diagnosi incerta, richiede supervisione",
            RISK_LOW,
        )

    def evaluate(self, sensor_data, ai_result) -> bool:
        return ai_result.get("needs_human_review", False)


# ─────────────────────────────────────────────
# REGOLE FIORE
# ─────────────────────────────────────────────

class FlowerAbortionRule(DiagnosisRule):
    """Aborto floreale: temperatura fuori range durante fioritura."""

    def __init__(self):
        super().__init__(
            "FLOW_01",
            "Rischio aborto floreale: temperature estreme durante la fioritura",
            RISK_HIGH,
        )

    def evaluate(self, sensor_data, ai_result) -> bool:
        temp = sensor_data.get("temperature_c")
        flower_result = ai_result.get("flower_result", {})
        flower_detected = ai_result.get("flower_detected", False)
        if not flower_detected or temp is None:
            return False
        return temp < 10.0 or temp > 35.0


class FlowerDropRule(DiagnosisRule):
    """Caduta prematura fiori: bassa umidità o eccesso azoto."""

    def __init__(self):
        super().__init__(
            "FLOW_02",
            "Rischio caduta prematura fiori: umidità bassa o stress nutrizionale",
            RISK_MEDIUM,
        )

    def evaluate(self, sensor_data, ai_result) -> bool:
        hum = sensor_data.get("humidity_pct")
        flower_detected = ai_result.get("flower_detected", False)
        if not flower_detected or hum is None:
            return False
        return hum < 30.0


class FlowerDiseaseRule(DiagnosisRule):
    """Malattia del fiore rilevata dall'AI."""

    def __init__(self):
        super().__init__(
            "FLOW_03",
            "Patologia del fiore rilevata dalla visione artificiale",
            RISK_HIGH,
        )

    def evaluate(self, sensor_data, ai_result) -> bool:
        flower_result = ai_result.get("flower_result", {})
        if not flower_result:
            return False
        cls = flower_result.get("class", "Fiore_sano")
        above = flower_result.get("above_threshold", False)
        return cls != "Fiore_sano" and above


class FlowerFungalRule(DiagnosisRule):
    """Rischio muffa grigia sul fiore: umidità elevata durante fioritura."""

    def __init__(self):
        super().__init__(
            "FLOW_04",
            "Rischio muffa grigia (Botrytis) sui fiori: umidità critica",
            RISK_CRITICAL,
        )

    def evaluate(self, sensor_data, ai_result) -> bool:
        hum = sensor_data.get("humidity_pct")
        flower_detected = ai_result.get("flower_detected", False)
        if not flower_detected or hum is None:
            return False
        return hum >= SENSOR_CONFIG["humidity_fungal_risk"]


# ─────────────────────────────────────────────
# REGOLE FRUTTO
# ─────────────────────────────────────────────

class FruitRotRule(DiagnosisRule):
    """Marciume apicale o fungino del frutto."""

    def __init__(self):
        super().__init__(
            "FRUT_01",
            "Rischio marciume del frutto: condizioni favorevoli a patogeni",
            RISK_CRITICAL,
        )

    def evaluate(self, sensor_data, ai_result) -> bool:
        fruit_result = ai_result.get("fruit_result", {})
        if not fruit_result:
            return False
        cls = fruit_result.get("class", "Frutto_sano")
        above = fruit_result.get("above_threshold", False)
        return ("Marciume" in cls or "Muffa" in cls) and above


class FruitCrackRule(DiagnosisRule):
    """Spaccatura del frutto da stress idrico alternato."""

    def __init__(self):
        super().__init__(
            "FRUT_02",
            "Rischio spaccatura frutto: irrigazione irregolare o umidità variabile",
            RISK_HIGH,
        )

    def evaluate(self, sensor_data, ai_result) -> bool:
        fruit_result = ai_result.get("fruit_result", {})
        if not fruit_result:
            return False
        cls = fruit_result.get("class", "Frutto_sano")
        above = fruit_result.get("above_threshold", False)
        return "Spaccatura" in cls and above


class FruitCalciumDefRule(DiagnosisRule):
    """Carenza calcio nel frutto (marciume apicale pomodoro)."""

    def __init__(self):
        super().__init__(
            "FRUT_03",
            "Carenza calcio nel frutto: rischio marciume apicale",
            RISK_HIGH,
        )

    def evaluate(self, sensor_data, ai_result) -> bool:
        fruit_detected = ai_result.get("fruit_detected", False)
        if not fruit_detected:
            return False
        ph = sensor_data.get("ph")
        ec = sensor_data.get("ec_ms_cm")
        if ph is None or ec is None:
            return False
        # pH elevato blocca assorbimento calcio + EC bassa = insufficiente
        return ph > 6.8 and ec < 1.2


class FruitSunburnRule(DiagnosisRule):
    """Scottatura solare del frutto: luce eccessiva + temperatura alta."""

    def __init__(self):
        super().__init__(
            "FRUT_04",
            "Rischio scottatura solare del frutto: luce intensa + temperatura elevata",
            RISK_MEDIUM,
        )

    def evaluate(self, sensor_data, ai_result) -> bool:
        fruit_detected = ai_result.get("fruit_detected", False)
        if not fruit_detected:
            return False
        light = sensor_data.get("light_lux")
        temp = sensor_data.get("temperature_c")
        if light is None or temp is None:
            return False
        return light > SENSOR_CONFIG["light_stress_high"] and temp > 32.0


class FruitDiseaseRule(DiagnosisRule):
    """Patologia generica del frutto rilevata dall'AI."""

    def __init__(self):
        super().__init__(
            "FRUT_05",
            "Patologia del frutto rilevata dalla visione artificiale",
            RISK_HIGH,
        )

    def evaluate(self, sensor_data, ai_result) -> bool:
        fruit_result = ai_result.get("fruit_result", {})
        if not fruit_result:
            return False
        cls = fruit_result.get("class", "Frutto_sano")
        above = fruit_result.get("above_threshold", False)
        return cls != "Frutto_sano" and above and "FRUT_01" not in [
            r for r in [ai_result.get("_active_rule_ids", [])]
        ]


# ─────────────────────────────────────────────
# REGISTRO REGOLE
# ─────────────────────────────────────────────

ALL_RULES: List[DiagnosisRule] = [
    FungalRiskRule(),
    PhotosyntheticStressRule(),
    LightStressRule(),
    Co2DeficiencyRule(),
    Co2ExcessRule(),
    PhAcidRule(),
    PhAlkalineRule(),
    EcToxicRule(),
    EcLowRule(),
    TemperatureStressRule(),
    AiDiseaseRule(),
    AiLowConfidenceRule(),
    # Regole fiore
    FlowerAbortionRule(),
    FlowerDropRule(),
    FlowerDiseaseRule(),
    FlowerFungalRule(),
    # Regole frutto
    FruitRotRule(),
    FruitCrackRule(),
    FruitCalciumDefRule(),
    FruitSunburnRule(),
    FruitDiseaseRule(),
]

# Mappa priorità rischi
RISK_PRIORITY = {
    RISK_CRITICAL: 5,
    RISK_HIGH: 4,
    RISK_MEDIUM: 3,
    RISK_LOW: 2,
    RISK_NONE: 1,
}


def evaluate_all_rules(
    sensor_data: Dict[str, Any],
    ai_result: Dict[str, Any],
) -> List[DiagnosisRule]:
    """
    Valuta tutte le regole e restituisce quelle attivate,
    ordinate per priorità decrescente.

    v3.0: Exclude flower/fruit rules in leaf-only mode
    """
    from core.config import ORGAN_CONFIG
    leaf_only_mode = ORGAN_CONFIG.get("leaf_only_mode", False)

    # In v3.0 leaf-only mode, skip flower and fruit rules
    if leaf_only_mode:
        # Filter to only leaf rules (indices 0-11)
        rules_to_evaluate = [r for r in ALL_RULES
                            if not (r.rule_id.startswith('FLOW_') or
                                   r.rule_id.startswith('FRUT_'))]
    else:
        rules_to_evaluate = ALL_RULES

    activated = [
        rule for rule in rules_to_evaluate
        if rule.evaluate(sensor_data, ai_result)
    ]
    activated.sort(key=lambda r: RISK_PRIORITY.get(r.risk_level, 0), reverse=True)
    return activated


def get_overall_risk(activated_rules: List[DiagnosisRule]) -> str:
    """Determina il livello di rischio globale dalla lista di regole attivate."""
    if not activated_rules:
        return RISK_NONE
    return max(
        (r.risk_level for r in activated_rules),
        key=lambda lvl: RISK_PRIORITY.get(lvl, 0),
    )
