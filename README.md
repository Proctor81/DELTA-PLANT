# 🌿 DELTA Plant - AI & Robotics Orchestrator per la Salute delle Piante

![Python](https://img.shields.io/badge/Python-3.12-blue?logo=python)
![Platform](https://img.shields.io/badge/Platform-Raspberry%20Pi%205-red?logo=raspberry-pi)
![AI](https://img.shields.io/badge/AI-TFLite%20float16-orange)
![License](https://img.shields.io/badge/License-Proprietary-lightgrey)
![Version](https://img.shields.io/badge/Version-v3.0--LEAF--ONLY-green)
![Classes](https://img.shields.io/badge/Classes-33%20Classi-blue)
![Accuracy](https://img.shields.io/badge/Accuracy-83.9%25%20top--1%20%7C%2096.1%25%20top--3-success)


> **DELTA Plant** — *AI & Robotics Orchestrator per la Salute delle Piante*  
> **DELTA** (Detection and Evaluation of Leaf Troubles and Anomalies)  
> Sistema AI orchestrato specializzato nella diagnostica fitosanitaria fogliare su **Raspberry Pi 5** — v3.0 Leaf-Only Architecture

---

## 📋 Indice

- [Caratteristiche principali](#-caratteristiche-principali)
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

## ✨ Caratteristiche principali

| Funzionalità | Descrizione |
|---|---|
| **Analisi fogliare esclusiva** | Diagnostica 33 classi di malattie/patologie fogliari via MobileNetV2 transfer learning |
| **Input sensori manuale** | Utente invia foto + 7 dati sensori (TEMP, UMID, PRESS, LUMI, CO₂, pH, EC) |
| **21 regole esperte** | 12 foglia + 4 fiore + 5 frutto — valutazione in parallelo |
| **Oracolo Quantistico di Grover** | 4 qubit, 3 iterazioni, 16 stati di rischio — Quantum Risk Score [0,1] |
| **7 sensori ambientali** | Temperatura, Umidità, Pressione, Luce, CO₂, pH, EC via I2C |
| **DELTA Academy** | Formazione interattiva con quiz, simulazioni e badge |
| **Pannello Amministratore** | Protetto PBKDF2-SHA256 — backup, statistiche, pubblicazione GitHub |
| **API REST opzionale** | Flask — 7 endpoint per integrazione esterna |
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
| Formato | TensorFlow Lite float16 (MobileNetV2 transfer learning) |
| Dimensione Keras | 14 MB |
| Dimensione TFLite | 5.0 MB (float16) |
| Input shape | `(224, 224, 3)` — preprocessing MobileNetV2: `(x/127.5)−1.0` |
| Classi output | 33 classi PlantVillage |
| Accuracy top-1 | **83.9%** (554/660 img, benchmark PlantVillage) |
| Accuracy top-3 | **96.1%** (634/660 img, benchmark PlantVillage) |
| Inferenza (RPi5) | ~180ms (XNNPACK delegate) |
| Soglia confidenza | 50% (fallback Classe_NonClassificato) |
| Thread inferenza | 4 |

### Classi diagnostiche — 33 classi PlantVillage

| Crop Type | Classi | Accuracy benchmark | Priorità |
|-----------|--------|--------------------|----------|
| **Bell Pepper** | 2 (Bacterial Spot, Healthy) | 100% / 95% | 🔴 **HIGH** |
| **Tomato** | 9 (Bacterial Spot, Early Blight, Late Blight, Leaf Mold, Mosaic Virus, Septoria, Target Spot, Yellow Leaf Curl, Healthy) | 15%–100% | 🟡 Medium |
| **Grape** | 4 (Black Rot, Esca, Leaf Blight, Healthy) | 65%–100% | 🟡 Medium |
| **Apple** | 4 (Apple Scab, Black Rot, Cedar Rust, Healthy) | 55%–90% | 🟢 Low |
| **Corn** | 4 (Cercospora, Common Rust, Northern Leaf Blight, Healthy) | 70%–95% | 🟢 Low |
| **Potato** | 3 (Early Blight, Late Blight, Healthy) | 85%–90% | 🟡 Medium |
| **Strawberry** | 2 (Leaf Scorch, Healthy) | 100% | 🟢 Low |
| **Squash** | 1 (Powdery Mildew) | 100% | 🟢 Low |
| **Blueberry** | 1 (Healthy) | 100% | 🟢 Low |
| **Cherry** | 2 (Powdery Mildew, Healthy) | 95% | 🟢 Low |
| **Peach** | 1 (Healthy) | 100% | 🟢 Low |

**Totale:** 33 classi — benchmark reale su 660 immagini PlantVillage (20/classe, 2026-05-03)

> ℹ️ Le classi con bassa accuratezza (es. Tomato_Bacterial_spot 15%, Tomato_Early_blight 40%) presentano
> confusioni morfologiche inter-classe tipiche di macchie fogliari visivamente simili.
> L'accuratezza top-3 è **96.1%** — la classe corretta appare quasi sempre tra le prime 3 predizioni.

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
├── models/                  # plant_disease_model.tflite + labels.txt
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
- `flask>=3.0.0`
- `python-telegram-bot[job-queue]>=20.7`
- `requests>=2.31.0`

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

**DELTA PLANT SOFTWARE LICENSE** — Software Release: **v3.0**  
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

## 📈 Model Training Details (v2.0.6)

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

*README aggiornato con risultati benchmark reale — 03/05/2026*
