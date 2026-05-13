"""
DELTA - core/config.py
Configurazione centralizzata del sistema.
Tutti i parametri operativi, soglie e percorsi sono definiti qui.
"""

import os
from pathlib import Path
from typing import Any
from pathlib import Path

try:
    import yaml  # type: ignore
except ImportError:
    yaml = None


def _deep_update(target: dict[str, Any], source: dict[str, Any]) -> dict[str, Any]:
    """Merge ricorsivo per override opzionali da config.yaml."""
    for key, value in source.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            _deep_update(target[key], value)
        else:
            target[key] = value
    return target


def _load_yaml_overrides(config_path: Path) -> dict[str, Any]:
    """Carica override runtime da config.yaml se disponibile."""
    if yaml is None or not config_path.exists():
        return {}
    try:
        payload = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}

# ─────────────────────────────────────────────
# PERCORSI BASE
# ─────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent
MODELS_DIR = BASE_DIR / "models"
DATASETS_DIR = BASE_DIR / "datasets"
EXPORTS_DIR = BASE_DIR / "exports"
LOGS_DIR = BASE_DIR / "logs"
INPUT_IMAGES_DIR = BASE_DIR / "input_images"   # Cartella immagini manuali (no camera)
LEARNING_BY_DOING_DIR = DATASETS_DIR / "learning_by_doing"

# Crea directory se non esistono
for d in [MODELS_DIR, DATASETS_DIR, EXPORTS_DIR, LOGS_DIR, INPUT_IMAGES_DIR, LEARNING_BY_DOING_DIR]:
    d.mkdir(parents=True, exist_ok=True)

SYSTEM_INFO = {
    "name": "DELTA Plant",
    "acronym": "DELTA",
    "version": "3.2",
    "release": "v3.2",
    "release_name": "Unified Edge Intelligence",
    "release_date": "2026-05-13",
    "manual_revision": "2026-05-13",
}

# ─────────────────────────────────────────────
# MODELLO AI
# ─────────────────────────────────────────────
MODEL_CONFIG = {
    "model_path": str(MODELS_DIR / "plant_disease_model_39classes.tflite"),
    "labels_path": str(MODELS_DIR / "labels_33classes_correct.txt"),
    "validation_image_path": str(MODELS_DIR / "validation_sample.jpg"),
    "preflight_min_confidence": 0.50,  # Soglia minima preflight gate di deploy
    "input_size": (224, 224),          # WxH
    "input_dtype": "float32",          # FP32 (TFLite v2.0.6 standard)
    "confidence_threshold": 0.65,      # Soglia minima confidenza
    "low_confidence_threshold": 0.50,  # Soglia active learning
    "num_threads": 4,                  # Thread inferenza NPU/CPU
    "use_edge_tpu": True,              # Raspberry Pi AI HAT 2+
    "model_version": "v3.2-33c-hybrid-edge",  # Stack 33 classi con backend edge validati
    "model_accuracy": 0.8390,          # Benchmark top-1 (2026-05-03)
    "leaf_only_mode": True,            # v3.0: Focus on leaf diseases only
}

# ─────────────────────────────────────────────
# REGISTRO MODELLI SPECIALIZZATI
# ─────────────────────────────────────────────
# Ogni entry può essere passata a ModelLoader per sostituire il modello di default.
# Usare la chiave come identificatore (es. "dipladenia", "generale").
MODELS_REGISTRY: dict = {
    "generale": {
        "backend":      "mobilenet",
        "model_path":   str(MODELS_DIR / "plant_disease_model_39classes.tflite"),
        "labels_path":  str(MODELS_DIR / "labels_33classes_correct.txt"),
        "description":  "Classificatore generale fogliare PlantVillage (33 classi)",
        "input_size":   (224, 224),
        "num_classes":  33,
        "quantization": "float16",
    },
    "dipladenia": {
        "backend":      "mobilenet",
        "model_path":   str(MODELS_DIR / "dipladenia" / "dipladenia_model.tflite"),
        "labels_path":  str(MODELS_DIR / "dipladenia" / "labels.txt"),
        "description":  "Classificatore specializzato Dipladenia/Mandevilla (3 classi)",
        "input_size":   (224, 224),
        "num_classes":  3,
        "quantization": "float16",
        "classes": [
            "Dipladenia_Malata",
            "Dipladenia_Parassiti",
            "Dipladenia_Sano",
        ],
    },
    "efficientformer": {
        "backend": "efficientformer",
        "display_name": "EfficientFormerV2-S1",
        "description": "Classificatore ibrido CNN/ViT EfficientFormerV2-S1 per 33 classi PlantVillage con profilo int8 edge validato",
        "labels_path": str(MODELS_DIR / "labels_33classes_correct.txt"),
        "input_size": (224, 224),
        "num_classes": 33,
        "num_threads": 6,
        "quantization": "int8",
        "top_k": 3,
        "enable_delegate": True,
        "enable_ensemble": True,
        "ensemble_model_key": "generale",
        "ensemble_weights": [0.70, 0.30],
        "enable_explainability": True,
        "explainability_method": "layercam",
        "torch_model_name": "efficientformerv2_s1",
        "pytorch_checkpoint": str(MODELS_DIR / "efficientformer_v2_s1_33classes.pth"),
        "torch_input_mean": [0.5, 0.5, 0.5],
        "torch_input_std": [0.5, 0.5, 0.5],
        "colormap": "jet",
        "overlay_alpha": 0.42,
        "variants": {
            "float16": {
                "model_path": str(MODELS_DIR / "efficientformer_v2_s1_33classes_float16.tflite"),
            },
            "float32": {
                "model_path": str(
                    MODELS_DIR / "efficientformer_v2_s1_saved_model" / "efficientformer_v2_s1_33classes_float32.tflite"
                ),
            },
            "int8": {
                "model_path": str(MODELS_DIR / "efficientformer_v2_s1_33classes_int8.tflite"),
            },
        },
        "model_path": str(MODELS_DIR / "efficientformer_v2_s1_33classes_int8.tflite"),
    },
}

# Modello attivo di default — modificabile a runtime o da .env (DELTA_ACTIVE_MODEL)
ACTIVE_MODEL = os.environ.get("DELTA_ACTIVE_MODEL", "generale")

# Etichette fogliare fallback allineate al modello 33-classi.
DEFAULT_LABELS = [
    "Apple_Apple_scab",
    "Apple_Black_rot",
    "Apple_Cedar_apple_rust",
    "Apple_healthy",
    "Bell_pepper_Bacterial_spot",
    "Bell_pepper_healthy",
    "Blueberry_healthy",
    "Cherry_Powdery_mildew",
    "Cherry_healthy",
    "Corn_Cercospora",
    "Corn_Common_rust",
    "Corn_Northern_Leaf_Blight",
    "Corn_healthy",
    "Grape_Black_rot",
    "Grape_Esca",
    "Grape_Leaf_blight",
    "Grape_healthy",
    "Peach_healthy",
    "Potato_Early_blight",
    "Potato_Late_blight",
    "Potato_healthy",
    "Squash_Powdery_mildew",
    "Strawberry_Leaf_scorch",
    "Strawberry_healthy",
    "Tomato_Bacterial_spot",
    "Tomato_Early_blight",
    "Tomato_Late_blight",
    "Tomato_Leaf_Mold",
    "Tomato_Septoria_leaf_spot",
    "Tomato_Target_Spot",
    "Tomato_Yellow_Leaf_Curl",
    "Tomato_healthy",
    "Tomato_mosaic_virus",
]

# Etichette patologie fiore
FLOWER_LABELS = [
    "Fiore_sano",
    "Caduta_prematura_fiore",
    "Aborto_floreale",
    "Mancata_allegagione",
    "Oidio_fiore",
    "Muffa_grigia_fiore",
    "Bruciatura_petali",
    "Deformazione_fiore",
]

# Etichette patologie frutto
FRUIT_LABELS = [
    "Frutto_sano",
    "Marciume_apicale",
    "Spaccatura_frutto",
    "Scottatura_solare",
    "Muffa_grigia_frutto",
    "Alternaria_frutto",
    "Rugginosità",
    "Deformazione_frutto",
    "Carenza_calcio_frutto",
]

# ─────────────────────────────────────────────
# SENSORI - SOGLIE AGRONOMICHE
# ─────────────────────────────────────────────
SENSOR_CONFIG = {
    # Intervalli lettura
    "read_interval_sec": 30,
    "smoothing_window": 5,             # Campioni per media mobile

    # Soglie temperatura (°C)
    "temp_min": 5.0,
    "temp_max": 40.0,
    "temp_optimal_min": 18.0,
    "temp_optimal_max": 28.0,

    # Soglie umidità relativa (%)
    "humidity_min": 20.0,
    "humidity_max": 95.0,
    "humidity_optimal_min": 40.0,
    "humidity_optimal_max": 70.0,
    "humidity_fungal_risk": 80.0,      # Soglia rischio fungino

    # Soglie pressione (hPa)
    "pressure_min": 950.0,
    "pressure_max": 1060.0,

    # Soglie luminosità (lux)
    "light_min": 0.0,
    "light_max": 120000.0,
    "light_photosynthesis_min": 1000.0,
    "light_photosynthesis_optimal": 25000.0,
    "light_stress_high": 80000.0,

    # Soglie CO2 (ppm)
    "co2_min": 300.0,
    "co2_max": 5000.0,
    "co2_optimal_min": 400.0,
    "co2_optimal_max": 1500.0,
    "co2_enhanced_growth": 800.0,

    # Soglie pH suolo
    "ph_min": 3.0,
    "ph_max": 10.0,
    "ph_optimal_min": 6.0,
    "ph_optimal_max": 7.0,

    # Soglie EC - Conducibilità elettrica (mS/cm)
    "ec_min": 0.0,
    "ec_max": 5.0,
    "ec_optimal_min": 0.8,
    "ec_optimal_max": 2.5,
    "ec_toxic": 3.5,

    # Indirizzi I2C sensori Adafruit (aggiornare secondo hardware)
    "i2c_bus": 1,
    "bme680_address": 0x76,            # Temp/Umidità/Pressione/Gas
    "veml7700_address": 0x10,          # Luminosità
    "scd41_address": 0x62,             # CO2
    "ads1115_address": 0x48,           # ADC per pH/EC
    "ph_adc_channel": 0,
    "ec_adc_channel": 1,
}

# ─────────────────────────────────────────────
# VISION
# ─────────────────────────────────────────────
VISION_CONFIG = {
    "camera_index": 0,
    "capture_width": 1920,
    "capture_height": 1080,
    "preview_width": 640,
    "preview_height": 480,
    "capture_format": "MJPG",
    "fps": 30,
    "segmentation_method": "hsv",      # 'hsv' o 'grabcut'
    "hsv_lower": [25, 40, 40],         # Intervallo verde HSV foglia (lower)
    "hsv_upper": [85, 255, 255],       # Intervallo verde HSV foglia (upper)
    "min_leaf_area": 500,              # Area minima pixel foglia
    "save_captures": True,
    "captures_dir": str(DATASETS_DIR / "captures"),
    # ── Input manuale da cartella (alternativa camera) ────────
    "input_images_dir": str(INPUT_IMAGES_DIR),
    "input_image_extensions": [".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".webp"],
    "explainability": {
        "enabled": True,
        "method": "layercam",
        "save_overlay": True,
        "save_heatmap": True,
        "output_dir": str(EXPORTS_DIR / "explanations"),
        "send_original": True,
        "send_overlay": True,
    },
}

# ─────────────────────────────────────────────
# ANALISI MULTI-ORGANO (foglia / fiore / frutto)
# ─────────────────────────────────────────────
ORGAN_CONFIG = {
    # Segmentazione foglia (verde)
    "leaf": {
        "hsv_lower": [25, 40, 40],
        "hsv_upper": [85, 255, 255],
        "min_area": 500,
    },
    # Segmentazione fiore (giallo, bianco, rosa, rosso, viola)
    "flower": {
        "ranges": [
            # Giallo
            {"lower": [20, 80, 100], "upper": [35, 255, 255]},
            # Bianco/crema
            {"lower": [0, 0, 180], "upper": [180, 40, 255]},
            # Rosa/magenta
            {"lower": [140, 50, 100], "upper": [175, 255, 255]},
            # Rosso-fiore (es. papavero)
            {"lower": [0, 100, 100], "upper": [10, 255, 255]},
            {"lower": [170, 100, 100], "upper": [180, 255, 255]},
        ],
        "min_area": 300,
    },
    # Segmentazione frutto (rosso, arancione, giallo-maturo, verde-frutto)
    "fruit": {
        "ranges": [
            # Rosso maturo (pomodoro, peperone)
            {"lower": [0, 120, 80], "upper": [10, 255, 255]},
            {"lower": [170, 120, 80], "upper": [180, 255, 255]},
            # Arancione (agrumi, albicocca)
            {"lower": [10, 150, 100], "upper": [20, 255, 255]},
            # Giallo maturo (banana, limone)
            {"lower": [22, 100, 100], "upper": [32, 255, 255]},
            # Verde-frutto (uva verde, kiwi)
            {"lower": [50, 60, 60], "upper": [80, 200, 200]},
        ],
        "min_area": 400,
    },
    # Soglie confidenza rilevamento organo
    "detection_confidence": 0.15,   # % area immagine minima per rilevare organo
    "enable_flower_analysis": False,  # DISABLED in v3.0 (leaf-only focus)
    "enable_fruit_analysis": False,   # DISABLED in v3.0 (leaf-only focus)
}

# ─────────────────────────────────────────────
# ORACOLO QUANTISTICO DI GROVER
# ─────────────────────────────────────────────
QUANTUM_CONFIG = {
    # Numero di qubit per il registro dei rischi (2^n stati)
    "n_qubits": 4,                  # 16 stati di rischio possibili
    # Numero iterazioni Grover (ottimale: π/4 * √N)
    "grover_iterations": 3,
    # Soglie risk score quantistico [0,1]
    "risk_threshold_low": 0.25,
    "risk_threshold_medium": 0.45,
    "risk_threshold_high": 0.65,
    "risk_threshold_critical": 0.80,
    # Pesi per ogni categoria di rischio nel vettore di stato
    "risk_weights": {
        "fungal": 0.8,
        "bacterial": 0.7,
        "viral": 0.9,
        "nutrient": 0.5,
        "water": 0.6,
        "environmental": 0.4,
        "flower_abort": 0.7,
        "fruit_rot": 0.85,
        "fruit_crack": 0.65,
        "pest": 0.75,
        "light_stress": 0.4,
        "temp_stress": 0.55,
        "ph_imbalance": 0.6,
        "salinity": 0.9,
        "ai_detection": 0.85,
        "compound": 0.95,          # Rischio composto (combinazione fattori)
    },
}

# ─────────────────────────────────────────────
# DATABASE
# ─────────────────────────────────────────────
DATABASE_CONFIG = {
    "db_path": str(BASE_DIR / "delta.db"),
    "max_records": 10000,              # Records massimi prima di pulizia
}

# ─────────────────────────────────────────────
# LOGGING
# ─────────────────────────────────────────────
LOGGING_CONFIG = {
    "level": "DEBUG",
    "log_file": str(LOGS_DIR / "delta.log"),
    "max_bytes": 10 * 1024 * 1024,    # 10 MB
    "backup_count": 5,
    "format": "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    "date_format": "%Y-%m-%dT%H:%M:%S",
}

# ─────────────────────────────────────────────
# FEATURE FLAGS DI SISTEMA
# ─────────────────────────────────────────────
FEATURE_FLAGS: dict = {}

# ─────────────────────────────────────────────
# API FLASK
# ─────────────────────────────────────────────
API_CONFIG = {
    "host": "0.0.0.0",
    "port": 5000,
    "debug": False,
    "enable_api": False,               # Abilitare manualmente
}

# ─────────────────────────────────────────────
# TELEGRAM BOT (OPZIONALE)
# ─────────────────────────────────────────────
TELEGRAM_CONFIG = {
    "enable_telegram": True,           # Abilitato di default
    "token_env": "DELTA_TELEGRAM_TOKEN",
    "authorized_users": [],            # Lista ID Telegram (vuota = accesso aperto)
    "authorized_usernames": [],        # Lista nickname (con @) (vuota = accesso aperto)
    "authorized_usernames_file": str(BASE_DIR / "data" / "telegram_scientists.local.json"),
    "api_base_url": "http://localhost:5000",
    "request_timeout_sec": 5,
    "conversation_timeout_sec": 300,   # 5 minuti
    "poll_interval_sec": 1.0,
}

# ─────────────────────────────────────────────────────────────────────────────
# MODELLO RICERCA 33 CLASSI (v3.0 - MobileNetV2 Leaf-Only)
# ─────────────────────────────────────────────────────────────────────────────
MODELS_REGISTRY_RESEARCH = {
    "ricerca_33classi": {
        "model_keras":  str(MODELS_DIR / "plant_disease_model_39classes.keras"),
        "model_tflite": str(MODELS_DIR / "plant_disease_model_39classes.tflite"),
        "labels_path":  str(MODELS_DIR / "labels_33classes_correct.txt"),
        "class_mapping": str(MODELS_DIR / "CLASS_MAPPING.csv"),
        "description":  "PlantVillage 33 classi (MobileNetV2, benchmark top-1 83.9%, RPi5 optimized)",
        "dataset_path": "datasets/training_39classes",
        "num_classes":  33,
        "accuracy":     0.839,
        "validation_accuracy": 0.961,
        "inference_time_ms": 180,
        "model_size_kb": 14000,
        "tflite_size_kb": 5000,
    },
}

CONFIG_YAML_PATH = Path(os.environ.get("DELTA_CONFIG_YAML", str(BASE_DIR / "config.yaml")))
CONFIG_YAML_OVERRIDES = _load_yaml_overrides(CONFIG_YAML_PATH)

_SECTION_OVERRIDES = (
    ("MODEL_CONFIG", MODEL_CONFIG),
    ("MODELS_REGISTRY", MODELS_REGISTRY),
    ("VISION_CONFIG", VISION_CONFIG),
    ("ORGAN_CONFIG", ORGAN_CONFIG),
    ("QUANTUM_CONFIG", QUANTUM_CONFIG),
    ("DATABASE_CONFIG", DATABASE_CONFIG),
    ("LOGGING_CONFIG", LOGGING_CONFIG),
    ("FEATURE_FLAGS", FEATURE_FLAGS),
    ("API_CONFIG", API_CONFIG),
    ("TELEGRAM_CONFIG", TELEGRAM_CONFIG),
    ("MODELS_REGISTRY_RESEARCH", MODELS_REGISTRY_RESEARCH),
)

for section_name, target in _SECTION_OVERRIDES:
    section_override = CONFIG_YAML_OVERRIDES.get(section_name)
    if isinstance(section_override, dict):
        _deep_update(target, section_override)

if not os.environ.get("DELTA_ACTIVE_MODEL") and isinstance(CONFIG_YAML_OVERRIDES.get("ACTIVE_MODEL"), str):
    ACTIVE_MODEL = CONFIG_YAML_OVERRIDES["ACTIVE_MODEL"]

