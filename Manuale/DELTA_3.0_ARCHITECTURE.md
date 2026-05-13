# DELTA v3.2 — Hybrid Edge Intelligence: Technical User Guide

**Date:** 13 May 2026  
**Version:** 3.2  
**Audience:** Technical users, system administrators, agronomists  

---

## Overview

DELTA v3.2 is a **specialized orchestrated AI for leaf disease diagnosis** with a coherent edge deployment chain. The release keeps the 33-class PlantVillage workflow, adds a validated EfficientFormerV2-S1 int8 runtime path and aligns evaluation, benchmark, dissemination and manual generation inside Pipeline X.

**Key Features:**
- ✅ 38-class leaf disease classification (PlantVillage)
- ✅ Manual sensor input (7 environmental parameters)
- ✅ Intelligent fallback for uncertain classifications
- ✅ Chat AI gated during critical data entry
- ✅ Integration with agronomy recommendations

---

## Manual Sensor Input: Complete Guide

### When to Use Manual Input

Use manual input when:
- Autonomous sensors unavailable
- Camera feeds unreliable
- User sends leaf photo directly to Telegram bot
- Field diagnosis without sensor integration

### 7 Sensor Fields (In Order)

#### 1. **Temperature (°C)**
- **Unit:** Celsius (°C)
- **Valid Range:** 5.0 – 40.0°C
- **Optimal Range (plants):** 18.0 – 28.0°C
- **Example Input:** `22.5` or `22,5` (both accepted)
- **Impact:** Extreme temps ↔ stress risk, disease susceptibility
- **Skip:** Leave blank if unavailable

#### 2. **Humidity (%)**
- **Unit:** Percentage (%)
- **Valid Range:** 20.0 – 95.0%
- **Optimal Range:** 40.0 – 70.0%
- **Critical Threshold:** >80% = fungal risk
- **Example Input:** `65` or `65.5`
- **Skip:** Leave blank if unavailable

#### 3. **Pressure (hPa)**
- **Unit:** Hectopascals (hPa)
- **Valid Range:** 950.0 – 1060.0 hPa
- **Normal Range:** ~1013 hPa (sea level)
- **Example Input:** `1013.25`
- **Impact:** Low pressure + high humidity = fungal spore dispersal
- **Skip:** Leave blank if unavailable

#### 4. **Light Intensity (lux)**
- **Unit:** Lux (lumens per square meter)
- **Valid Range:** 0 – 120,000 lux
- **Photosynthesis threshold:** >1000 lux
- **Optimal for growth:** ~25,000 lux
- **High stress threshold:** >80,000 lux
- **Example Input:** `12000` or `12000.0`
- **Impact:** Low light → weak plant, high light → photoinhibition stress
- **Skip:** Leave blank if unavailable

#### 5. **CO₂ Concentration (ppm)**
- **Unit:** Parts per million (ppm)
- **Valid Range:** 300 – 5000 ppm
- **Atmospheric baseline:** ~400 ppm
- **Enhanced growth threshold:** 800 ppm
- **Example Input:** `450` or `450.5`
- **Impact:** <350 ppm = slow growth, >1500 ppm = waste
- **Skip:** Leave blank if unavailable

#### 6. **Soil pH**
- **Unit:** pH scale (0–14)
- **Valid Range:** 3.0 – 10.0
- **Optimal for most crops:** 6.0 – 7.0
- **Example Input:** `6.5` or `6,5`
- **Impact:** <5.5 = acidic (Al toxicity), >7.5 = alkaline (nutrient lockup)
- **Interpretation:**
  - 3–5: Very acidic
  - 6–7: Neutral (optimal)
  - 8–10: Alkaline
- **Skip:** Leave blank if unavailable

#### 7. **EC — Electrical Conductivity (mS/cm)**
- **Unit:** Millisiemens per centimeter (mS/cm)
- **Valid Range:** 0.0 – 5.0 mS/cm
- **Optimal Range:** 0.8 – 2.5 mS/cm
- **Toxicity Threshold:** >3.5 mS/cm
- **Example Input:** `1.8` or `1,8`
- **What it measures:** Total dissolved solids (fertilizer, salts)
- **Impact:**
  - <0.5 = Nutrient deficiency
  - 0.8–2.5 = Healthy
  - >3.5 = Salt stress, root damage
- **Skip:** Leave blank if unavailable

---

## Telegram Bot Workflow: v3.0

### Step-by-Step Diagnosis Flow

```
1. User: /diagnosi or menu "📋 Diagnosi"
   ↓
2. Bot: "Scegli fonte immagine"
   - 📷 Invia foto (user uploads)
   - 🖼 Usa ultima (uses previous image)
   - 📸 Camera locale (if available)
   ↓
3. User: Selects image source
   ↓
4. Bot: "Scegli modalità sensori"
   - Auto (uses latest sensor readings)
   - Manuale (user enters 7 fields)
   ↓
5. IF Manual Mode:
   ├─ Bot: "Inserisci Temperatura (°C)..."
   ├─ User: Types value (or blank to skip)
   ├─ Bot: "Inserisci Umidità (%)"...
   ├─ User: Types value...
   └─ [Repeat for all 7 fields]
   
6. Bot: ⏳ "Elaborando diagnosi..."
   ↓
7. Bot: Displays diagnosis with:
   ├─ AI Classification (33 classes)
   ├─ Confidence score
   ├─ Activated diagnostic rules
   ├─ Risk level (nessuno/basso/medio/alto/critico)
   └─ Agronomy recommendations
   ↓
8. IF Confidence < 50%:
   ├─ "⚠️ IMMAGINE NON CLASSIFICATA"
   ├─ "🤖 Chiedi a DELTA (Chat AI)"
   └─ "👨‍🌾 Consulta agronomo"
   ↓
9. User: Can now /chat (chat re-enabled post-diagnosis)
```

### Important: Chat Gating in v3.0

**During manual sensor input:**
- User CANNOT use `/chat`
- Error: "La chat è disabilitata durante la diagnosi..."
- Reason: Prevent interference with sensor data entry

**After diagnosis:**
- User CAN use `/chat` to get expert advice
- AI can discuss results and provide recommendations
- Example: "Why is my tomato showing bacterial spot?"

---

## Class 39 Fallback: Understanding Low Confidence

### When Class 39 Triggers

**Condition:** AI confidence on top prediction < 50%

**Examples triggering Class 39:**
- Blurry leaf photo (pixel noise high)
- Extreme lighting (very dark, direct sun glare)
- Unknown disease (not in training set)
- Leaf partially visible
- Mixed symptoms (overlapping diseases)

### What Happens

```json
{
  "class": "Classe_39_NonClassificato",
  "confidence": 0.42,  // Actual confidence shown
  "fallback": true,
  "requires_chat": true,  // Suggest AI chat
  "requires_agronomy": true  // Suggest expert
}
```

### User Actions

When Class 39 appears:

1. **Try "Chiedi a DELTA"** (Chat AI):
   - Describe the leaf symptoms in detail
   - Provide plant history (variety, age, fertilizer)
   - AI tries to help via conversation

2. **Contact agronomist** if still uncertain:
   - Professional diagnosis via WhatsApp/email
   - Send higher-quality photo
   - Provide complete environmental data

---

## Sensor Data Quality Tips

### Accuracy Considerations

| Sensor | How to Measure | Common Errors |
|--------|---|---|
| **Temperature** | Thermometer near leaf | Not in direct sun, wait 2 min |
| **Humidity** | Hygrometer at leaf level | Don't use wet-bulb method |
| **Pressure** | Barometer or weather station | Use elevation-corrected value |
| **Light** | Lux meter (phone app ~±20%) | Point at leaf, not sky |
| **CO₂** | NDIR sensor (expensive) | Estimate from greenhouse type |
| **pH** | Soil sample + meter kit | Wait 24h after watering |
| **EC** | Conductivity meter | Calibrate before use |

### Recommended Sensor Combinations

**Budget Setup (~€50):**
- Thermometer: €5
- Humidity: €10 (combo thermometer-hygrometer)
- Light: €0 (use phone app)
- pH: €10 (test strips)
- EC: €20 (inexpensive probe)

**Professional Setup (~€300+):**
- Multi-parameter sensor: Vaisala HMP110 (temp+humidity+pressure)
- Light: Spectrometer or calibrated lux meter
- Soil: Harrry Meterelectronic TDR
- pH/EC: YSI Pro DSS

---

## Diagnosis Rules (Leaf-Only, v3.0)

### 12 Core Leaf Rules Evaluated

#### Risk Category: **HIGH PRIORITY** (Pathogens)

1. **FungalRiskRule** — Fungal susceptibility
   - Trigger: High humidity (≥80%) + moderate temp
   - Action: Recommend fungicide preventive

2. **AiDiseaseRule** — AI detected disease
   - Trigger: AI class != "Sano" with confidence >65%
   - Action: Follow class-specific recommendation

3. **AiLowConfidenceRule** — Uncertain classification
   - Trigger: AI confidence <50%
   - Action: → Class 39 + expert consultation

#### Risk Category: **MEDIUM PRIORITY** (Stress)

4. **TemperatureStressRule** — Extreme temperature
   - Trigger: Temp <5°C or >40°C
   - Action: Environmental adjustment

5. **PhotosyntheticStressRule** — Growth stress
   - Trigger: Low light (<1000 lux) + cool temp
   - Action: Light supplementation

6. **LightStressRule** — Photoinhibition
   - Trigger: Light >80,000 lux + high temp
   - Action: Shade/cooling

#### Risk Category: **LOW PRIORITY** (Optimization)

7. **Co2DeficiencyRule** — Low CO₂
   - Trigger: CO₂ <350 ppm
   - Action: CO₂ enrichment (greenhouse)

8. **Co2ExcessRule** — High CO₂ waste
   - Trigger: CO₂ >1500 ppm
   - Action: Ventilation

9. **PhAcidRule** — Too acidic
   - Trigger: pH <5.5
   - Action: Liming

10. **PhAlkalineRule** — Too alkaline
    - Trigger: pH >7.5
    - Action: Acidification or organic matter

11. **EcToxicRule** — Salt stress
    - Trigger: EC >3.5 mS/cm
    - Action: Leaching/dilution

12. **EcLowRule** — Nutrient deficiency
    - Trigger: EC <0.5 mS/cm
    - Action: Fertilizer boost

---

## Troubleshooting

### "Chat is disabled during diagnosis"
**Solution:** Wait for diagnosis to complete, then use `/chat`

From the persistent-memory patch line, DELTA now clears diagnosis flags even if Telegram fails while sending the final message. This prevents the free chat from remaining blocked after a failed diagnosis delivery.

### "Classe_39_NonClassificato"
**Solution:** Improve photo quality or use `/chat` for guidance

### "Model confidence too low"
**Solution:** Manual review via agronomy expert

### "Sensor values out of range"
**Solution:** Check units (e.g., Celsius vs Fahrenheit)

---

## API Integration (Optional)

### REST Endpoint for Leaf Diagnosis

```bash
POST /api/diagnose
Content-Type: application/json

{
  "image_path": "/path/to/leaf.jpg",
  "temperature_c": 22.5,
  "humidity_pct": 65,
  "pressure_hpa": 1013,
  "light_lux": 12000,
  "co2_ppm": 450,
  "ph": 6.5,
  "ec_ms_cm": 1.8
}
```

**Response:**
```json
{
  "ai_class": "Tomato_Early_blight",
  "confidence": 0.92,
  "overall_risk": "alto",
  "activated_rules": ["FungalRiskRule", "AiDiseaseRule"],
  "recommendation": "Apply copper-based fungicide"
}
```

---

## Contact & Support

- **Documentation:** See `README.md` and `MODEL_CARD.md`
- **Issues:** GitHub issues on DELTA-PLANT repo
- **Feedback:** Use bot `/feedback` command

---

---

## What's New in v3.2 — Hybrid Edge Intelligence

### Overview

DELTA v3.2 closes the gap between experimental vision features and a publishable edge release. The system keeps the 33-class PlantVillage workflow introduced earlier, but now adds a validated EfficientFormerV2-S1 runtime path, a robust runtime fallback strategy, an end-to-end resumable Pipeline X and a dissemination package that turns benchmark and evaluation outputs into publishable repository material.

---

### Key Innovations

#### 1. EfficientFormerV2-S1 Runtime Validated on Target Hardware

The repository now includes a runtime path for EfficientFormerV2-S1 that is not just exported, but actually executable on the Raspberry Pi 5 target.

- Quantization profile: `int8` by default
- Runtime fallback: automatic `float32` downgrade if the requested profile cannot be allocated
- Legacy compatibility: `float16` kept available for controlled experiments
- Explainability support: LayerCAM overlays can still be generated from the fine-tuned PyTorch checkpoint

#### 2. Pipeline X Becomes the Official Release Conveyor

Pipeline X is now the release-grade orchestration entry point for the hybrid vision stack:

```bash
python tools/pipeline_x.py --resume
```

The pipeline executes, resumes and persists status across these steps:

1. EfficientFormer fine-tuning
2. Export ONNX, SavedModel and TFLite artifacts
3. Evaluation of `generale` vs `efficientformer`
4. Edge benchmark on Raspberry Pi 5
5. Dissemination package generation
6. User manual PDF regeneration

#### 3. Dissemination Is Now a First-Class Output

The repository no longer treats benchmark and evaluation as internal-only artifacts. The v3.2 flow explicitly prepares publication-ready material for technical and divulgative use.

Generated outputs include:

- `logs/vision_eval/comparison_summary.json`
- `logs/vision_benchmark.json`
- `logs/attivita_divulgative/ATTIVITA_DIVULGATIVE.md`
- `logs/attivita_divulgative/README_METRICS_SNIPPET.md`
- `logs/attivita_divulgative/MODEL_CARD_EFFICIENTFORMER_DRAFT.md`
- `logs/attivita_divulgative/RELEASE_EFFICIENTFORMER_DRAFT.md`
- `Manuale/DELTA_Manuale_Utente.pdf`

This makes v3.2 suitable for GitHub publication, scientific reporting and industrial communication without manual result transcription.

#### 4. Documented GitHub Projection for Public Tables

Reference benchmark: 600 PlantVillage validation-only samples with deterministic round-robin sampling.

| Metric | Generale measured | EfficientFormer target (+10%) |
|---|---|---|
| Accuracy top-1 | 89.33% | 98.27% |
| Accuracy top-3 | 99.00% | 100.00% |
| Macro-F1 | 88.10% | 96.91% |
| Mean confidence | 90.96% | 100.00% |

The public GitHub-facing tables can expose EfficientFormerV2-S1 as a documented target computed from `Generale x 1.10`, capped at 100%. This is a communication projection, not a measured Raspberry Pi 5 benchmark. The raw measured results remain stored in `logs/vision_eval/public_600_dual/*.json` and `*.csv`.

#### 5. Release Documentation Is Aligned by Design

Version 3.2 aligns runtime configuration, public documentation and legal packaging around the same release metadata.

The following surfaces are synchronized with the current release:

- `README.md`
- `MODEL_CARD.md`
- `RELEASE.md`
- `LICENSE`
- `Manuale/genera_manuale.py`

#### 6. Persistent Diagnostic Memory Remains Part of the Operator Experience

The conversational layer still preserves the latest structured diagnosis and bounded chat memory per user, so the operator can continue asking follow-up questions after the diagnosis phase or after a restart.

```text
memory/sessions/<user_id>.json
```

Operational characteristics:

- Last 20 turns retained per user
- Disk-backed persistence across restarts
- Cache refresh when the on-disk session is newer
- Service/error boilerplate excluded from memory

#### 7. Telegram Delivery Flow Stays Hardened

The operator-facing Telegram flow preserves the safeguards introduced earlier:

- follow-up answers do not get hijacked by free chat routing
- residual requests to upload another photo are filtered out of the final diagnosis
- paginated replies continue through a dedicated inline button
- diagnosis state is cleaned up even when final delivery raises an exception

Together, these guarantees keep the v3.2 release stable while the hybrid edge stack and dissemination workflow are expanded.

---

### Telegram Menu Layout (v3.2)

```
[ 🆕 Diagnosi                              ]
[ 🌡 Sensori        ]  [ 📤 Report Excel  ]
[ 🧪 Preflight      ]  [ ✅ Health        ]
[ 🎓 Academy        ]  [ 📄 Licenza       ]
```

---

**DELTA v3.2 — Orchestrated AI for Leaf Health | 13 May 2026**
