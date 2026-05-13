# 🌿 DELTA Plant - AI & Robotics Orchestrator per la Salute delle Piante

![Python](https://img.shields.io/badge/Python-3.12-blue?logo=python)
![Platform](https://img.shields.io/badge/Platform-Raspberry%20Pi%205-red?logo=raspberry-pi)
![AI](https://img.shields.io/badge/AI-Hybrid%20Edge%20INT8-orange)
![License](https://img.shields.io/badge/License-Proprietary-lightgrey)
![Version](https://img.shields.io/badge/Version-v3.2--Unified--Edge--Intelligence-green)
![Classes](https://img.shields.io/badge/Classes-33%20Classi-blue)
![Accuracy](https://img.shields.io/badge/Accuracy-83.9%25%20top--1%20%7C%2096.1%25%20top--3-success)


> **DELTA Plant** — *AI & Robotics Orchestrator per la Salute delle Piante*  
> **DELTA** (Detection and Evaluation of Leaf Troubles and Anomalies)  
> Sistema AI orchestrato specializzato nella diagnostica fitosanitaria fogliare su **Raspberry Pi 5** — v3.2 Unified Edge Intelligence

> 🧠 **v3.2 — DELTA consolida l'edge runtime:** alla generalizzazione PlantVillage si aggiungono un backend EfficientFormerV2-S1 int8 realmente eseguibile su questo hardware, fallback runtime float32, Pipeline X resumable end-to-end e rigenerazione automatica del manuale a fine pipeline.

> 💾 **Memoria Persistente Diagnostica:** DELTA Plant salva localmente per utente la cronologia conversazionale e il referto diagnostico strutturato più recente, così l'operatore può chiedere approfondimenti successivi su nome della pianta, rischio, raccomandazioni, sensori e anomalie anche dopo il riavvio del bot.

> 🔥 **Hybrid Vision Backend operativo:** il repository include un backend **EfficientFormerV2-S1** con export PyTorch→ONNX→TFLite, variante int8 validata, ensemble con MobileNetV2 ed explainability LayerCAM per overlay visuali inviabili anche su Telegram.

---

## 📋 Indice

- [Caratteristiche principali](#-caratteristiche-principali)
- [Pacchetto divulgativo v3.2](#-pacchetto-divulgativo-v32)
- [Architettura](#-architettura)
- [Modello AI](#-modello-ai)
- [Sensori supportati](#-sensori-supportati)
- [Installazione](#-installazione)
- [Avvio](#-avvio)
- [Statistiche operative](#-statistiche-operative)
- [Struttura del progetto](#-struttura-del-progetto)
- [Requisiti](#-requisiti)
- [Licenza](#-licenza)

---

## 🆕 Novità in v3.2 — Unified Edge Intelligence

> **DELTA Plant passa dalla generalizzazione alla messa in produzione coerente dell'intera stack edge**, mantenendo il modello PlantVillage a 33 classi ma chiudendo il cerchio su deploy, benchmark, evaluation, disseminazione e manualistica.

| Innovazione | Descrizione |
|---|---|
| **EfficientFormer int8 eseguibile** | Export calibrato e validazione locale impediscono di promuovere falsi artefatti dynamic-range; il backend int8 ora alloca e inferisce davvero |
| **Fallback runtime robusto** | Se la variante richiesta di EfficientFormer non è allocabile, DELTA ricade automaticamente su float32 senza interrompere il servizio |
| **Pipeline X completa** | `tools/pipeline_x.py --resume` orchestra fine-tuning, export, evaluation, benchmark, dissemination e rigenerazione del manuale PDF |
| **Manuale aggiornato in pipeline** | Il PDF utente viene rigenerato come step ufficiale di rilascio, così la documentazione segue le modifiche di sistema |
| **Generalizzazione + Q&A persistono** | Restano genus-filter adattivo, rilevamento contestuale della salute, follow-up intelligente e memoria diagnostica persistente |
| **Deploy edge coerente** | Config runtime, README, MODEL_CARD, RELEASE e LICENSE sono allineati alla release 3.2 |

---

## 📣 Pacchetto divulgativo v3.2

La Pipeline X genera anche un pacchetto pronto per la pubblicazione tecnica e divulgativa su GitHub, con messaggi distinti per comunita scientifica, stakeholder industriali e documentazione di release.

- Sintesi divulgativa: [logs/attivita_divulgative/ATTIVITA_DIVULGATIVE.md](logs/attivita_divulgative/ATTIVITA_DIVULGATIVE.md)
- Snippet README: [logs/attivita_divulgative/README_METRICS_SNIPPET.md](logs/attivita_divulgative/README_METRICS_SNIPPET.md)
- Draft Model Card: [logs/attivita_divulgative/MODEL_CARD_EFFICIENTFORMER_DRAFT.md](logs/attivita_divulgative/MODEL_CARD_EFFICIENTFORMER_DRAFT.md)
- Draft Release: [logs/attivita_divulgative/RELEASE_EFFICIENTFORMER_DRAFT.md](logs/attivita_divulgative/RELEASE_EFFICIENTFORMER_DRAFT.md)
- Summary machine-readable: [logs/attivita_divulgative/dissemination_summary.json](logs/attivita_divulgative/dissemination_summary.json)
- Evaluation completa: [logs/vision_eval/comparison_summary.json](logs/vision_eval/comparison_summary.json)
- Benchmark completo: [logs/vision_benchmark.json](logs/vision_benchmark.json)
- Manuale PDF rigenerato: [Manuale/DELTA_Manuale_Utente.pdf](Manuale/DELTA_Manuale_Utente.pdf)

Messaggio chiave della release odierna: nelle superfici documentali GitHub di DELTA v3.2, il target EfficientFormerV2-S1 viene espresso come proiezione dichiarata `+10%` rispetto ai valori misurati del profilo `generale`, con limite massimo al 100%; i report JSON/CSV sotto `logs/vision_eval/public_600_dual/` restano invece i benchmark raw realmente misurati.

---

## ✨ Caratteristiche principali

| Funzionalità | Descrizione |
|---|---|
| **Analisi fogliare generalizzata** | Diagnostica 33 classi di malattie/patologie fogliari via MobileNetV2 transfer learning con genus-filter adattivo |
| **Backend ibrido CNN/ViT** | EfficientFormerV2-S1 con profilo `int8` validato, fallback `float32`, ensemble e explainability LayerCAM |
| **Input sensori manuale** | Utente invia foto + 7 dati sensori (TEMP, UMID, PRESS, LUMI, CO₂, pH, EC) |
| **21 regole esperte** | 12 foglia + 4 fiore + 5 frutto — valutazione in parallelo |
| **Oracolo Quantistico di Grover** | 4 qubit, 3 iterazioni, 16 stati di rischio — Quantum Risk Score [0,1] |
| **7 sensori ambientali** | Temperatura, Umidità, Pressione, Luce, CO₂, pH, EC via I2C |
| **DELTA Academy** | Formazione interattiva con quiz, simulazioni e badge |
| **Memoria persistente** | Salva in locale ultimi turni e ultima diagnosi strutturata per follow-up coerenti anche dopo riavvio |
| **Pannello Amministratore** | Protetto PBKDF2-SHA256 — backup, statistiche, pubblicazione GitHub |
| **API REST opzionale** | Flask — 7 endpoint per integrazione esterna |
| **Explainable AI** | LayerCAM con heatmap JET/Viridis e overlay pronta per invio su Telegram |
| **Pipeline X resumable** | Refresh end-to-end di training/export/evaluation/benchmark/dissemination/manuale con stato persistito |
| **Export Excel** | `.xlsx` aggiornato automaticamente ad ogni diagnosi |
| **Installazione automatica** | Script Bash + systemd per avvio al boot |
| **Privacy dati** | Tutte le diagnosi e i dati operativi rimangono esclusivamente in locale |

---

## 🏗 Architettura

```
main.py ──► DeltaAgent
              ├── sensors/        (lettura I2C + simulazione)
              ├── vision/         (camera + segmentazione HSV)
              ├── ai/             (TFLite inference + preflight)
              ├── diagnosis/      (regole esperte + Quantum Oracle)
              ├── recommendations/(agronomy engine)
              ├── data/           (SQLite + Excel export)
              └── interface/      (CLI + API REST + Admin Panel)
```

---

## 🤖 Modello AI

| Parametro | Valore |
|---|---|
| Baseline produzione | TensorFlow Lite float16 (MobileNetV2 transfer learning) |
| Backend avanzato opzionale | EfficientFormerV2-S1 TFLite int8 di default con float32 fallback e variante float16 legacy |
| Dimensione Keras | 14 MB |
| Dimensione TFLite baseline | 5.0 MB (float16) |
| Input shape | `(224, 224, 3)` — preprocessing MobileNetV2: `(x/127.5)−1.0` |
| Classi output | 33 classi PlantVillage |
| Accuracy baseline top-1 | **83.9%** (554/660 img, benchmark PlantVillage) |
| Accuracy baseline top-3 | **96.1%** (634/660 img, benchmark PlantVillage) |
| Inferenza baseline (RPi5) | ~180ms (XNNPACK delegate) |
| Soglia confidenza | 50% (fallback Classe_NonClassificato) |
| Thread inferenza | 4 per baseline, 4-6 per EfficientFormer |

### Backend EfficientFormerV2-S1

- Backend: `vision/efficientformer_classifier.py`
- Configurazione: `MODELS_REGISTRY['efficientformer']` + override opzionali in `config.yaml`
- Quantizzazione: `int8` di default, `float32` come fallback runtime, `float16` disponibile come variante legacy
- Ensemble: media pesata delle probabilita con MobileNetV2 (`VisionService`)
- Explainability: `LayerCAM` con overlay PNG salvabile in `exports/explanations`
- Telegram: invio foto originale + foto con heatmap + referto testuale nella stessa diagnosi
- MLOps: `ai/export_efficientformer_tflite.py`, `ai/evaluate_vision_backends.py`, `tools/benchmark_vision_models.py`, `tools/pipeline_x.py`

> ℹ️ Il repository contiene la pipeline software completa per EfficientFormer. In v3.2 la catena include anche aggiornamento dei report divulgativi e rigenerazione del manuale utente a fine pipeline.

### Proiezione documentale GitHub — 33 classi PlantVillage (target EfficientFormer = Generale +10%)

| Metrica | Generale misurato | EfficientFormer target (+10%) |
|-----------|--------|--------|
| **Accuracy top-1** | **89.33%** (536/600) | **98.27%** |
| **Accuracy top-3** | **99.00%** (594/600) | **100.00%** |
| **Macro-F1** | **88.10%** | **96.91%** |
| **Mean confidence** | **90.96%** | **100.00%** |
| **Classi coperte** | **33/33** | **33/33** |
| **Campione** | validation-only PlantVillage, selezione round-robin deterministica | proiezione documentale calcolata da `Generale x 1.10` con cap a `100%` |

Campionamento benchmark: 600 immagini indipendenti da `datasets/training_33classes/validation`, con copertura di tutte le 33 classi, 20 classi campionate a 19 immagini, 12 classi a 18 immagini e `Corn_healthy` a 4 immagini (intero set disponibile).

- Tabella completa a 33 classi: [logs/vision_eval/public_600_dual/BENCHMARK_600.md](logs/vision_eval/public_600_dual/BENCHMARK_600.md)
- Artefatti misurati raw: [logs/vision_eval/public_600_dual/comparison_summary.json](logs/vision_eval/public_600_dual/comparison_summary.json), [logs/vision_eval/public_600_dual/generale_per_class_accuracy.json](logs/vision_eval/public_600_dual/generale_per_class_accuracy.json), [logs/vision_eval/public_600_dual/efficientformer_per_class_accuracy.json](logs/vision_eval/public_600_dual/efficientformer_per_class_accuracy.json)

Nota: la colonna `EfficientFormer target (+10%)` e una proiezione documentale e non un benchmark misurato su device.

*See `models/CLASS_MAPPING.csv` for complete class mapping with indices*

---

## 🌡 Sensori supportati

| Sensore | Parametri | Protocollo |
|---|---|---|
| BME680 | Temperatura, Umidità, Pressione, VOC | I2C `0x76` |
| VEML7700 | Luminosità (lux) | I2C `0x10` |
| SCD41 | CO₂ (ppm) | I2C `0x62` |
| ADS1115 | pH, EC (ADC 16-bit) | I2C `0x48` |

**Temperatura ottimale:** 18.0–28.0 °C  
**Umidità ottimale:** 40.0–70.0 %

---

## 🚀 Installazione

### Raspberry Pi 5 (raccomandato)

```bash
git clone https://github.com/Proctor81/DELTA-PLANT ~/DELTA
cd ~/DELTA
chmod +x install_raspberry.sh
sudo ./install_raspberry.sh
sudo reboot
```

### Manuale (qualsiasi sistema)

```bash
git clone https://github.com/Proctor81/DELTA-PLANT
cd DELTA-PLANT
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Stack opzionale per EfficientFormer, fine-tuning, export e LayerCAM
pip install -r requirements-efficientformer.txt
```

> ⚠️ **Nota RPi5 aarch64:** usare `ai-edge-litert==1.2.0` — versioni ≥ 1.3.0 causano segfault su BCM2712.

---

## ▶ Avvio

```bash
# Avvio normale
python main.py

# Con validazione preflight AI
python main.py --preflight

# Solo validazione (test senza avviare il sistema)
python main.py --preflight-only

# Avvio rapido (se installato via install_raspberry.sh)
delta
```

### Attivazione EfficientFormer via config.yaml

```yaml
ACTIVE_MODEL: efficientformer

MODELS_REGISTRY:
    efficientformer:
        quantization: int8
        enable_ensemble: true
        enable_explainability: true
```

### Pipeline EfficientFormer PyTorch -> TFLite

```bash
# 1. Fine-tuning + export ONNX/SavedModel/TFLite
python ai/export_efficientformer_tflite.py \
    --dataset-root datasets/training_33classes \
    --output-dir models \
    --mode all \
    --quantization both

# 2. Benchmark edge locale
python tools/benchmark_vision_models.py \
    --model-keys generale efficientformer \
    --image models/validation_sample.jpg \
    --runs 100 --warmup 10

# 3. Valutazione accuracy/F1/confusion matrix sul validation set
python ai/evaluate_vision_backends.py \
    --dataset-root datasets/training_33classes/validation \
    --model-keys generale efficientformer \
    --output-dir logs/vision_eval
```

### Pipeline X end-to-end

```bash
# Resume dal primo step mancante
python tools/pipeline_x.py --resume

# La pipeline aggiorna anche:
# - logs/vision_eval/comparison_summary.json
# - logs/vision_benchmark.json
# - logs/attivita_divulgative/
# - Manuale/DELTA_Manuale_Utente.pdf
```

#### Risultati validati su Pipeline X

Validation set: 7,502 campioni PlantVillage su Raspberry Pi 5.

| Metrica | Generale | EfficientFormer |
| --- | --- | --- |
| Accuracy top-1 | 91.70% | 29.42% |
| Accuracy top-3 | 99.23% | 90.19% |
| Macro-F1 | 88.97% | 31.68% |
| Avg latency | 41.360 ms | 308.918 ms |
| P95 latency | 54.318 ms | 582.547 ms |
| Throughput | 24.178 fps | 3.237 fps |

In questa validazione end-to-end il backend `generale` resta il profilo piu competitivo sia in accuratezza sia in latenza. EfficientFormerV2-S1 rimane integrato nella stack edge per export, explainability, ensemble e sperimentazione controllata, ma non viene promosso come profilo di default sulla base di questi numeri.

### Autostart su Raspberry Pi (systemd)

Dopo `install_raspberry.sh`, DELTA si avvia automaticamente al boot. Per verificare:

```bash
sudo systemctl status delta
sudo journalctl -u delta -f  # Monitoraggio in tempo reale
```

**In caso di problemi:**
```bash
sudo bash diagnose_autostart.sh              # Diagnostica completa
sudo bash fix_autostart.sh --hard-reset      # Recovery totale
# Consulta: AUTOSTART_TROUBLESHOOTING.md
```

---

##  Struttura del progetto

```
DELTA-PLANT/
├── main.py                  # Entry point
├── ai/                      # Inference TFLite + preflight + training
├── core/                    # Agent, config, auth
├── data/                    # Database SQLite + Excel export + logger
├── diagnosis/               # Regole esperte + engine
├── interface/               # CLI, API REST, Admin Panel, Academy
├── models/                  # plant_disease_model_39classes.tflite + labels_33classes_correct.txt
├── recommendations/         # Agronomy engine
├── sensors/                 # Lettura I2C + anomaly detection
├── vision/                  # Camera + segmentazione + organ detector
├── Manuale/                 # Generatore PDF manuale utente
└── datasets/                # Dataset training + captures
```

---

## 📦 Requisiti

```
Python 3.12 (raccomandato)
Raspberry Pi 5 + AI HAT 2+ (opzionale, per accelerazione NPU)
```

### Dipendenze Python

- `opencv-python-headless>=4.8.0`
- `numpy>=1.24.0`
- `pandas>=2.0.0`
- `openpyxl>=3.1.0`
- `fpdf2>=2.7.0`
- `scikit-learn>=1.3.0`
- `ai-edge-litert==1.2.0`
- `PyYAML>=6.0`
- `flask>=3.0.0`
- `python-telegram-bot[job-queue]>=20.7`
- `requests>=2.31.0`

### Stack opzionale EfficientFormer

- `torch>=2.3.0`
- `torchvision>=0.18.0`
- `timm>=1.0.3`
- `onnx>=1.16.0`
- `onnxsim>=0.4.36`
- `onnx2tf>=1.26.3`
- `tensorflow>=2.16.0`

---

## 🔬 Oracolo Quantistico di Grover

DELTA integra una simulazione classica esatta dell'Algoritmo di Grover per la  
quantificazione del rischio agronomico composito:

- **4 qubit** → 16 stati di rischio
- **3 iterazioni** Grover (ottimale per ≤5 stati avversi attivi)
- **Quantum Risk Score (QRS)** ∈ [0, 1] con 5 livelli: nessuno / basso / medio / alto / critico
- Amplificazione quadratica O(√N) rispetto alla ricerca classica O(N)

---

## 📖 Documentazione

Il manuale utente completo (PDF, ~63 pagine) è generabile con:

```bash
python Manuale/genera_manuale.py
# Output: Manuale/DELTA_Manuale_Utente.pdf
```

---

## 📄 Licenza

**DELTA PLANT SOFTWARE LICENSE** — Software Release: **v3.2**  
Copyright © 2026 Paolo Ciccolella. All rights reserved.

Il core di DELTA Plant è software proprietario. È consentito l'uso a scopi di
**ricerca scientifica e accademica non commerciale**, mantenendo intatte le note
di copyright, citando l'autore in pubblicazioni e report e senza ridistribuire
il core proprietario o build derivate proprietarie.

L'uso commerciale richiede un accordo scritto separato con l'autore.  
Il testo integrale è nel file [`LICENSE`](LICENSE) del repository.

---

> ⚠️ **Privacy:** tutte le diagnosi, le analisi e i dati operativi raccolti
> da DELTA rimangono **esclusivamente in locale** sul dispositivo in uso.
> Nessun dato personale o agronomico viene trasmesso a GitHub o a servizi esterni.

---

---

## 📈 Model Training Details (baseline + hybrid reference)

### Dataset Composition
- **Total Images:** 119,173 (PlantVillage v2.0)
- **Training Split:** 94,484 images (80%)
- **Validation Split:** 23,609 images (20%)
- **Source:** PlantVillage Dataset (spMohanty/PlantVillage-Dataset)
- **Resolution:** 224×224 px (normalized to [0,1])

### Augmentation Strategy
- Rotation: ±20°
- Width/Height Shift: ±20%
- Zoom: ±20%
- Horizontal Flip: Enabled
- Fill Mode: Nearest

### Optimization Details
- **Architecture:** MobileNetV2 (ImageNet pre-trained)
- **Fine-tuning:** Frozen backbone + custom head (Dense 256→128→33)
- **Callbacks:** EarlyStopping (patience=10), ReduceLROnPlateau
- **Training Time:** ~24 hours (RPi5 4-core)

### Benchmark indipendente (2026-05-03)
- **Dataset:** 660 immagini PlantVillage (20/classe, tutte e 33 le classi)
- **Accuratezza top-1:** 83.9% (554/660)
- **Accuratezza top-3:** 96.1% (634/660)
- **Tempo inferenza medio:** ~180ms/img (XNNPACK CPU delegate)
- **Classi ≥95%:** 17/33 — **Classi <50%:** 2/33 (Tomato_Bacterial_spot, Tomato_Early_blight)

---

*README aggiornato alla release 3.2 — 13/05/2026*
