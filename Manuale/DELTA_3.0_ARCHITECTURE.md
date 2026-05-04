# DELTA v3.1 — Intelligent PlantVillage Generalization: Technical User Guide

**Date:** 4 May 2026  
**Version:** 3.1  
**Audience:** Technical users, system administrators, agronomists  

---

## Overview

DELTA v3.0 is a **specialized orchestrated AI** focused exclusively on **leaf disease diagnosis**. Unlike v2.0 (multi-organ), v3.0 removes flower and fruit analysis to streamline diagnostics and improve leaf classification accuracy.

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

## What's New in v3.1 — Intelligent PlantVillage Generalization

### Overview

DELTA v3.1 evolves the Computer Vision model by introducing **contextual generalization over PlantVillage classes**. The system now understands which plant genus the operator is working with and restricts AI classification to that genus only — eliminating cross-genus confusion and dramatically improving diagnostic accuracy for plants whose visual symptoms overlap across species.

---

### Key Innovations

#### 1. Genus Detection (Programmatic, Zero-LLM)

When the operator describes the plant, DELTA extracts the **genus** using a prioritized keyword map:

```python
_GENUS_KEYWORD_MAP = [
    (["bell pepper", "peperone", "pepper", "capsicum"], "Bell_pepper"),
    (["apple", "mela"],                                  "Apple"),
    (["blueberry", "mirtillo"],                          "Blueberry"),
    (["cherry", "ciliegio", "ciliegia"],                 "Cherry"),
    (["corn", "mais", "granturco"],                      "Corn"),
    (["grape", "uva", "vite", "vitis"],                  "Grape"),
    (["peach", "pesca", "pesco"],                        "Peach"),
    (["potato", "patata"],                               "Potato"),
    (["squash", "zucca"],                                "Squash"),
    (["strawberry", "fragola"],                          "Strawberry"),
    (["tomato", "pomodoro"],                             "Tomato"),
]
```

**Two-phase matching:**
1. Multi-word keywords first (e.g. `"bell pepper"` before `"pepper"`)
2. Single-word keywords second

This ensures `"bell pepper"` is never mistaken for `"pepper"` (Tomato genus).

#### 2. Class Filtering

Once the genus is detected, the LLM receives **only the classes belonging to that genus**:

| Operator says | Genus detected | Classes offered to LLM |
|---|---|---|
| "peperone con macchie" | Bell_pepper | Bell_pepper_Bacterial_spot, Bell_pepper_healthy |
| "pomodoro con macchie" | Tomato | Tomato_Bacterial_spot, Tomato_Early_blight, … |
| "vite sembra sana" | Grape | Grape_Black_rot, Grape_Esca, Grape_Leaf_blight, Grape_healthy |

Without filtering, `Bell_pepper_Bacterial_spot` and `Tomato_Bacterial_spot` share very similar visual features — the model would frequently misclassify.

#### 3. Contextual Health Detection (LLM Stateless)

The health check no longer relies on the single keyword `"sano"`. Instead, an LLM call evaluates the **entire operator sentence**:

- Input: `"la vite sembra stare benone"`
- LLM prompt: binary classification → `SANO` / `NON_SANO` / `INCERTO`
- If `SANO`: skip disease flow, produce wellness assessment
- Uses `chat_internal()` (stateless, no ConversationMemory read/write)

#### 4. Q&A Follow-up Loop Fix

Previously, `free_chat_handler` (PTB group 99) would intercept operator answers during the Q&A phase, generating a double response. Fixed with dedicated flag `diag_qa_active`:

```
START follow-up → diag_qa_active = True
  operator answers → ConversationHandler handles it (group 0)
  free_chat_handler skips (diag_qa_active is True)
END follow-up → diag_qa_active = False
```

#### 5. No-Photo-Loop Fix

The LLM was occasionally appending "send a photo for further analysis" to the diagnosis, causing the bot to restart the photo upload flow. Fixed at two levels:

1. **Prompt constraint:** `"Do not ask the user to send photos — image acquisition phase is complete."`
2. **Post-processing filter:** `_PHOTO_REQUEST_PATTERNS` regex removes any residual photo-request sentences from LLM output before delivery.

#### 6. Paginated Messages — Inline Button

Long diagnosis messages (>4096 chars) are split into chunks. The continuation button is now an **inline keyboard button** (`📄 Continua lettura`) registered as a global handler — works even after `ConversationHandler.END`.

---

### Telegram Menu Layout (v3.1)

```
[ 🆕 Diagnosi                              ]
[ 🌡 Sensori        ]  [ 📤 Report Excel  ]
[ 🧪 Preflight      ]  [ ✅ Health        ]
[ 🎓 Academy        ]  [ 📄 Licenza       ]
```

---

**DELTA v3.1 — Orchestrated AI for Leaf Health | 4 May 2026**
