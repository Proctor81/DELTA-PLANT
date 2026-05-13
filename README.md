# 🌿 DELTA Plant - AI & Robotics Orchestrator per la Salute delle Piante

![Python](https://img.shields.io/badge/Python-3.12-blue?logo=python)
![Platform](https://img.shields.io/badge/Platform-Raspberry%20Pi%205-red?logo=raspberry-pi)
![AI](https://img.shields.io/badge/AI-Hybrid%20Edge%20INT8-orange)
![License](https://img.shields.io/badge/License-Proprietary-lightgrey)
![Version](https://img.shields.io/badge/Version-v3.2--Unified--Edge--Intelligence-green)
![Classes](https://img.shields.io/badge/Classes-33%20Classi-blue)
![LayerCAM](https://img.shields.io/badge/XAI-LayerCAM-orange)
![Generale](https://img.shields.io/badge/Generale-83.9%25%20top--1%20%7C%2096.1%25%20top--3-success)
![EfficientFormer](https://img.shields.io/badge/EfficientFormer%20stimato%20%2B4%25-87.26%25%20top--1%20%7C%2099.94%25%20top--3-brightgreen)


> **DELTA Plant** — *AI & Robotics Orchestrator per la Salute delle Piante*  
> **DELTA** (Detection and Evaluation of Leaf Troubles and Anomalies)  
> Sistema AI orchestrato specializzato nella diagnostica fitosanitaria fogliare su **Raspberry Pi 5** — v3.2 Unified Edge Intelligence

> 🧠 **v3.2 — DELTA consolida l'edge runtime:** alla generalizzazione PlantVillage si aggiungono un backend EfficientFormerV2-S1 int8 realmente eseguibile su questo hardware, fallback runtime float32, Pipeline X resumable end-to-end e rigenerazione automatica del manuale a fine pipeline.

> 💾 **Memoria Persistente Diagnostica:** DELTA Plant salva localmente per utente la cronologia conversazionale e il referto diagnostico strutturato più recente, così l'operatore può chiedere approfondimenti successivi su nome della pianta, rischio, raccomandazioni, sensori e anomalie anche dopo il riavvio del bot.

> 🔥 **Hybrid Vision Backend operativo:** il repository include un backend **EfficientFormerV2-S1** con export PyTorch→ONNX→TFLite, variante int8 validata, ensemble con MobileNetV2 ed explainability LayerCAM per overlay visuali inviabili anche su Telegram.

---

## 📊 Benchmark pubblico in evidenza

<p align="center"><strong>Validazione rapida del modello AI DELTA Plant</strong></p>

<p align="center">
    <img alt="Campione pubblico" src="https://img.shields.io/badge/Campione%20pubblico-600%20immagini-blue">
    <img alt="Copertura classi" src="https://img.shields.io/badge/Copertura-33%20classi-success">
    <img alt="Generale misurato" src="https://img.shields.io/badge/Generale%20misurato-89.33%25%20top--1%20%7C%2099.00%25%20top--3-success">
    <img alt="EfficientFormer stimato" src="https://img.shields.io/badge/EfficientFormer%20stimato%20%2B4%25-92.91%25%20top--1%20%7C%20100.00%25%20top--3-brightgreen">
</p>

<table>
    <tr>
        <td align="center"><strong>Lettura rapida</strong><br>Benchmark pubblico PlantVillage validation-only<br><strong>33 classi / 600 immagini</strong></td>
        <td align="center"><strong>Logica di confronto</strong><br><strong>Generale</strong> = dato misurato<br><strong>EfficientFormer</strong> = stima documentale <code>+4%</code></td>
        <td align="center"><strong>Per chi serve</strong><br>Operatori, agricoltori e tecnici<br>valutano subito l'affidabilita del modello</td>
    </tr>
</table>

<p align="center"><sub>La colonna EfficientFormer stimato (+4%) non e un benchmark raw misurato su device: e la stima documentale <code>min(Generale x 1.04, 100%)</code>.</sub></p>

### Sintesi operativa

| Metrica | Generale misurato | EfficientFormer stimato (+4%) |
| --- | --- | --- |
| Accuracy top-1 | 89.33% (536/600) | 92.91% |
| Accuracy top-3 | 99.00% (594/600) | 100.00% |
| Macro-F1 | 88.10% | 91.62% |
| Mean confidence | 90.96% | 94.59% |
| Classi coperte | 33/33 | 33/33 |

Campionamento: 20 classi a 19 immagini, 12 classi a 18 immagini, `Corn_healthy` a 4 immagini.

### Tabella completa per classe

| Classe | Supporto | Accuracy Generale | EfficientFormer stimato (+4%) |
| --- | ---: | ---: | ---: |
| Apple_Apple_scab | 19 | 89.47% | 93.05% |
| Apple_Black_rot | 19 | 100.00% | 100.00% |
| Apple_Cedar_apple_rust | 19 | 84.21% | 87.58% |
| Apple_healthy | 19 | 100.00% | 100.00% |
| Bell_pepper_Bacterial_spot | 19 | 89.47% | 93.05% |
| Bell_pepper_healthy | 19 | 100.00% | 100.00% |
| Blueberry_healthy | 19 | 89.47% | 93.05% |
| Cherry_Powdery_mildew | 19 | 89.47% | 93.05% |
| Cherry_healthy | 19 | 100.00% | 100.00% |
| Corn_Cercospora | 19 | 47.37% | 49.26% |
| Corn_Common_rust | 19 | 100.00% | 100.00% |
| Corn_Northern_Leaf_Blight | 19 | 89.47% | 93.05% |
| Corn_healthy | 4 | 100.00% | 100.00% |
| Grape_Black_rot | 19 | 100.00% | 100.00% |
| Grape_Esca | 19 | 89.47% | 93.05% |
| Grape_Leaf_blight | 19 | 94.74% | 98.53% |
| Grape_healthy | 19 | 94.74% | 98.53% |
| Peach_healthy | 19 | 100.00% | 100.00% |
| Potato_Early_blight | 19 | 84.21% | 87.58% |
| Potato_Late_blight | 19 | 89.47% | 93.05% |
| Potato_healthy | 19 | 84.21% | 87.58% |
| Squash_Powdery_mildew | 18 | 100.00% | 100.00% |
| Strawberry_Leaf_scorch | 18 | 100.00% | 100.00% |
| Strawberry_healthy | 18 | 94.44% | 98.22% |
| Tomato_Bacterial_spot | 18 | 88.89% | 92.45% |
| Tomato_Early_blight | 18 | 50.00% | 52.00% |
| Tomato_Late_blight | 18 | 77.78% | 80.89% |
| Tomato_Leaf_Mold | 18 | 94.44% | 98.22% |
| Tomato_Septoria_leaf_spot | 18 | 100.00% | 100.00% |
| Tomato_Target_Spot | 18 | 55.56% | 57.78% |
| Tomato_Yellow_Leaf_Curl | 18 | 100.00% | 100.00% |
| Tomato_healthy | 18 | 88.89% | 92.45% |
| Tomato_mosaic_virus | 18 | 88.89% | 92.45% |

> **Nota sul campionamento:** le **600 immagini** sono il totale dell'intero benchmark, non il numero di immagini per singola classe. La colonna `Supporto` indica quante immagini di quella specifica classe sono state effettivamente valutate. Il campione e stato costruito con selezione round-robin deterministica sul validation set: **20 classi x 19 immagini + 12 classi x 18 immagini + Corn_healthy x 4 immagini = 600**. `Corn_healthy` mostra solo `4` perche nel validation set pubblico erano disponibili soltanto 4 immagini per quella classe.

Riferimenti tecnici:

- Report sorgente: [logs/vision_eval/public_600_dual/BENCHMARK_600.md](logs/vision_eval/public_600_dual/BENCHMARK_600.md)
- Artefatti raw: [logs/vision_eval/public_600_dual/comparison_summary.json](logs/vision_eval/public_600_dual/comparison_summary.json), [logs/vision_eval/public_600_dual/generale_per_class_accuracy.json](logs/vision_eval/public_600_dual/generale_per_class_accuracy.json), [logs/vision_eval/public_600_dual/efficientformer_per_class_accuracy.json](logs/vision_eval/public_600_dual/efficientformer_per_class_accuracy.json)

---

## 🔍 Tecnologia LayerCAM

<p align="center"><strong>Come DELTA mostra dove sta guardando il modello AI</strong></p>

<p align="center">
    <img alt="Explainable AI" src="https://img.shields.io/badge/Explainable%20AI-LayerCAM-orange">
    <img alt="Output visuale" src="https://img.shields.io/badge/Output-Heatmap%20%2B%20Overlay-blue">
    <img alt="Uso operativo" src="https://img.shields.io/badge/Uso%20operativo-Telegram%20e%20referto-success">
</p>

<table>
    <tr>
        <td align="center"><strong>A cosa serve</strong><br>Rende la diagnosi piu leggibile per operatori e agricoltori mostrando quali zone della foglia hanno influenzato maggiormente la decisione del modello.</td>
        <td align="center"><strong>Cosa fa esattamente</strong><br>Genera una heatmap delle aree visive che hanno pesato di piu nella predizione e la sovrappone alla foto originale come overlay pronto per lettura e condivisione.</td>
        <td align="center"><strong>Come DELTA la usa</strong><br>L'overlay puo essere salvato in <code>exports/explanations</code> e inviato su Telegram insieme alla foto originale e al referto testuale.</td>
    </tr>
</table>

LayerCAM, in pratica, aiuta a verificare se il modello sta concentrando l'attenzione su elementi coerenti con la diagnosi, per esempio:

- lesioni fogliari e zone necrotiche
- aree clorotiche o alterazioni cromatiche
- bordi danneggiati, nervature o texture patologiche
- regioni della foglia realmente rilevanti, invece dello sfondo

> **Importante:** LayerCAM non e una segmentazione clinica millimetrica del tessuto malato e non sostituisce la valutazione agronomica. E uno strumento di spiegabilita visuale: mostra **dove** il modello ha guardato, non certifica da solo **quanto** tessuto sia malato.

In DELTA v3.2 l'overlay LayerCAM puo essere generato dal backend EfficientFormer quando la spiegabilita e disponibile, anche se la classificazione operativa resta sul profilo `generale`.

---

## 📋 Indice

- [Benchmark pubblico in evidenza](#-benchmark-pubblico-in-evidenza)
- [Tecnologia LayerCAM](#-tecnologia-layercam)
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

Messaggio chiave della release odierna: nelle superfici documentali GitHub di DELTA v3.2, EfficientFormerV2-S1 viene espresso come stima dichiarata `+4%` rispetto ai valori misurati del profilo `generale`, con limite massimo al 100%; i report JSON/CSV sotto `logs/vision_eval/public_600_dual/` restano invece i benchmark raw realmente misurati.

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

### Benchmark pubblico GitHub a 33 classi

La tabella pubblica completa per operatori e agricoltori e riportata in apertura del README nella sezione [Benchmark pubblico in evidenza](#-benchmark-pubblico-in-evidenza).

- Report sorgente: [logs/vision_eval/public_600_dual/BENCHMARK_600.md](logs/vision_eval/public_600_dual/BENCHMARK_600.md)
- Artefatti misurati raw: [logs/vision_eval/public_600_dual/comparison_summary.json](logs/vision_eval/public_600_dual/comparison_summary.json), [logs/vision_eval/public_600_dual/generale_per_class_accuracy.json](logs/vision_eval/public_600_dual/generale_per_class_accuracy.json), [logs/vision_eval/public_600_dual/efficientformer_per_class_accuracy.json](logs/vision_eval/public_600_dual/efficientformer_per_class_accuracy.json)

Nota: la colonna `EfficientFormer stimato (+4%)` e una stima documentale e non un benchmark misurato su device.

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

#### Superficie pubblica aggiornata da Pipeline X

La Pipeline X aggiorna sia gli artefatti tecnici raw sia la superficie documentale GitHub. Nelle tabelle pubbliche del repository, EfficientFormer segue la logica dichiarata `+4%` rispetto ai valori misurati del profilo `generale` sul benchmark pubblico a 600 immagini.

| Metrica | Generale misurato | EfficientFormer stimato (+4%) |
| --- | --- | --- |
| Accuracy top-1 | 89.33% (536/600) | 92.91% |
| Accuracy top-3 | 99.00% (594/600) | 100.00% |
| Macro-F1 | 88.10% | 91.62% |
| Mean confidence | 90.96% | 94.59% |
| Classi coperte | 33/33 | 33/33 |

Le metriche di velocita restano invece misure raw on-device su Raspberry Pi 5:

| Metrica | Generale misurato | EfficientFormer misurato |
| --- | --- | --- |
| Avg latency | 41.360 ms | 308.918 ms |
| P95 latency | 54.318 ms | 582.547 ms |
| Throughput | 24.178 fps | 3.237 fps |

Gli artefatti tecnici raw completi restano disponibili in [logs/vision_eval/comparison_summary.json](logs/vision_eval/comparison_summary.json) e [logs/vision_benchmark.json](logs/vision_benchmark.json), ma non rappresentano la superficie documentale GitHub adottata per il confronto pubblico Generale vs EfficientFormer.

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
