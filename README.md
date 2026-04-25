# 🌿 DELTA — AI Agent per la Salute delle Piante

![Python](https://img.shields.io/badge/Python-3.12-blue?logo=python)
![Platform](https://img.shields.io/badge/Platform-Raspberry%20Pi%205-red?logo=raspberry-pi)
![AI](https://img.shields.io/badge/AI-TFLite%20INT8-orange)
![License](https://img.shields.io/badge/License-Proprietary-lightgrey)
![Version](https://img.shields.io/badge/Version-v2.0.4-green)


> **DELTA** (Detection and Evaluation of Leaf Troubles and Anomalies)  
> Sistema embedded di intelligenza artificiale per il monitoraggio fitosanitario in tempo reale  
> su **Raspberry Pi 5** con **AI HAT 2+**.

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
| **Analisi multi-organo** | Foglie, fiori e frutti rilevati simultaneamente via HSV multi-range |
| **7 classi diagnostiche** | Modello TFLite INT8 — input `(224, 224, 3)` px — 2675 KB |
| **21 regole esperte** | 12 foglia + 4 fiore + 5 frutto — valutazione in parallelo |
| **Oracolo Quantistico di Grover** | 4 qubit, 3 iterazioni, 16 stati di rischio — Quantum Risk Score [0,1] |
| **7 sensori ambientali** | Temperatura, Umidità, Pressione, Luce, CO₂, pH, EC via I2C |
| **DELTA Academy** | Formazione interattiva con quiz, simulazioni e badge |
| **Pannello Amministratore** | Protetto PBKDF2-SHA256 — backup, statistiche, pubblicazione GitHub |
| **API REST opzionale** | Flask — 7 endpoint per integrazione esterna |
| **Bot Telegram (DELTAPLANO)** | Frontend completo: diagnosi, report, export, Academy, upload immagini |
| **Learning-by-Doing** | Upload da Telegram con etichettatura e dataset per fine-tuning |
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
              └── interface/      (CLI + API REST + Admin Panel + Telegram)
```

---

## 🤖 Modello AI

| Parametro | Valore |
|---|---|
| Formato | TensorFlow Lite INT8 (quantizzato) |
| Dimensione | 2675 KB |
| Input shape | `(224, 224, 3)` |
| Soglia confidenza | 65% |
| Soglia preflight gate | 50% |
| Thread inferenza | 4 |

### Classi diagnostiche — foglia

| # | Classe |
|---|--------|
| 1 | `Sano` |
| 2 | `Peronospora` |
| 3 | `Oidio` |
| 4 | `Muffa_grigia` |
| 5 | `Alternaria` |
| 6 | `Ruggine` |
| 7 | `Mosaikovirus` |

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
git clone https://github.com/Proctor81/DELTA-2.0 ~/DELTA
cd ~/DELTA
chmod +x install_raspberry.sh
sudo ./install_raspberry.sh
sudo reboot
```

### Manuale (qualsiasi sistema)

```bash
git clone https://github.com/Proctor81/DELTA-2.0
cd DELTA-2.0
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

---

##  Struttura del progetto

```
DELTA-2.0/
├── main.py                  # Entry point
├── ai/                      # Inference TFLite + preflight + training
├── core/                    # Agent, config, auth
├── data/                    # Database SQLite + Excel export + logger
├── diagnosis/               # Regole esperte + engine
├── interface/               # CLI, API REST, Admin Panel, Academy, Telegram
├── models/                  # plant_disease_model.tflite + labels.txt
├── recommendations/         # Agronomy engine
├── sensors/                 # Lettura I2C + anomaly detection
├── vision/                  # Camera + segmentazione + organ detector
├── Manuale/                 # Generatore PDF manuale utente
└── datasets/                # Dataset training + captures + learning_by_doing
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

## 💬 Bot Telegram (opzionale)

1. Crea il bot con **BotFather** e salva il token.
2. Esporta il token:

```bash
export DELTA_TELEGRAM_TOKEN="TOKEN_BOT"
```

3. Abilita il bot in `core/config.py` (TELEGRAM_CONFIG) o avvia con:

```bash
python main.py --enable-api --enable-telegram
```

Comandi principali (DELTAPLANO):
- `/menu`, `/diagnosi`, `/upload`, `/images`, `/report`, `/dettaglio <id>`, `/sensori`,
  `/export`, `/preflight`, `/finetune`, `/academy`, `/license`, `/health`, `/batch`

Upload learning-by-doing:
- `/upload` (o invio diretto foto in chat) richiede **nome pianta**, scelta **organo** e **classe** (foglia/fiore/frutto)
- Salva in `input_images/` + dataset training dedicati + metadati JSON in `datasets/learning_by_doing/`
- Dataset dedicati: `datasets/training` (foglia), `datasets/training_flower`, `datasets/training_fruit`

> ⚠️ Per sicurezza, imposta `authorized_users` o `authorized_usernames` con gli utenti consentiti.

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

Il manuale utente completo (52 pagine, PDF) è generabile con:

```bash
python Manuale/genera_manuale.py
# Output: Manuale/DELTA_Manuale_Utente.pdf
```

---

## 📄 Licenza

Software proprietario — Copyright © 2026 Paolo Ciccolella. All rights reserved.  
Non è consentita la ridistribuzione o il riutilizzo senza autorizzazione scritta.

---

> ⚠️ **Privacy:** tutte le diagnosi, le analisi e i dati operativi raccolti
> da DELTA rimangono **esclusivamente in locale** sul dispositivo in uso.
> Nessun dato personale o agronomico viene trasmesso a GitHub o a servizi esterni.

---

*README generato automaticamente da DELTA vv2.0.4 — 25/04/2026 00:56*
