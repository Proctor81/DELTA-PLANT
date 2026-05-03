"""
DELTA - interface/github_publisher.py
======================================
Pubblicazione automatica di DELTA Plant su GitHub con un solo click.

Raccoglie automaticamente dal software:
  - Versione, descrizione e feature dal codice sorgente
  - Ultima versione dei modelli AI (labels, shape)
  - Dipendenze da requirements.txt
  - Changelog dall'ultimo tag git

NOTA PRIVACY: i dati operativi locali (diagnosi, statistiche DB, timestamps)
  NON vengono mai inclusi nei file pubblicati su GitHub.
  Rimangono esclusivamente sull'installazione locale.

Aggiorna (o crea):
  - README.md    — descrizione, funzionalità, installazione, badge
  - RELEASE.md   — changelog automatico dall'ultimo commit
  - Tag git      — es. v2.0.1 con timestamp
  - git commit + push → GitHub

Accesso: Pannello Amministratore → [7] Pubblica su GitHub
"""

from __future__ import annotations

import ast
import importlib.util
import json
import logging
import os
import re
import sqlite3
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional

logger = logging.getLogger("delta.interface.github_publisher")

BOLD   = "\033[1m"
DIM    = "\033[2m"
GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
BLUE   = "\033[94m"
RESET  = "\033[0m"

_ROOT = Path(__file__).resolve().parent.parent


# ─────────────────────────────────────────────────────────────
# RACCOLTA DATI AUTOMATICA DAL SOFTWARE
# ─────────────────────────────────────────────────────────────

def _run_git(*args: str) -> str:
    """Esegue un comando git e restituisce l'output (stringa)."""
    result = subprocess.run(
        ["git"] + list(args),
        cwd=str(_ROOT),
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _collect_git_info() -> Dict[str, Any]:
    """Raccoglie informazioni git: branch, remote, tag, commit recenti."""
    info = {
        "branch":      _run_git("rev-parse", "--abbrev-ref", "HEAD") or "main",
        "remote_url":  _run_git("remote", "get-url", "origin") or "",
        "last_commit": _run_git("log", "-1", "--format=%H %s") or "",
        "last_tag":    _run_git("describe", "--tags", "--abbrev=0") or "",
        "commit_count":_run_git("rev-list", "--count", "HEAD") or "0",
        "status_clean":_run_git("status", "--porcelain") == "",
    }
    # Url del repository (es. https://github.com/Owner/Repo)
    url = info["remote_url"]
    if url.endswith(".git"):
        url = url[:-4]
    info["repo_url"] = url
    # Owner e nome repo
    parts = url.rstrip("/").split("/")
    info["repo_name"] = parts[-1] if parts else "DELTA-PLANT"
    info["owner"]     = parts[-2] if len(parts) >= 2 else "Proctor81"
    return info


def _collect_changelog(since_tag: str = "") -> List[str]:
    """Raccoglie i commit dall'ultimo tag (o tutti se nessun tag)."""
    if since_tag:
        raw = _run_git("log", f"{since_tag}..HEAD", "--format=%s", "--no-merges")
    else:
        raw = _run_git("log", "--format=%s", "--no-merges", "-30")
    lines = [l.strip() for l in raw.splitlines() if l.strip()]
    return lines


def _collect_model_info() -> Dict[str, Any]:
    """Raccoglie informazioni sul modello AI (labels, shape)."""
    info: Dict[str, Any] = {
        "labels":       [],
        "n_classes":    0,
        "model_size_kb": 0,
        "tflite_ok":    False,
        "input_shape":  None,
    }
    labels_path = _ROOT / "models" / "labels_33classes_correct.txt"
    tflite_path = _ROOT / "models" / "plant_disease_model_39classes.tflite"
    try:
        from core.config import MODEL_CONFIG  # type: ignore
        labels_path = Path(MODEL_CONFIG.get("labels_path", labels_path))
        tflite_path = Path(MODEL_CONFIG.get("model_path", tflite_path))
    except Exception:
        pass
    if labels_path.exists():
        info["labels"] = [
            l.strip() for l in labels_path.read_text(encoding="utf-8").splitlines()
            if l.strip()
        ]
        info["n_classes"] = len(info["labels"])

    if tflite_path.exists():
        info["model_size_kb"] = tflite_path.stat().st_size // 1024
        info["tflite_ok"] = True
        try:
            try:
                import ai_edge_litert.interpreter as tflite_mod  # type: ignore
            except ImportError:
                import tensorflow.lite as tflite_mod  # type: ignore
            interp = tflite_mod.Interpreter(
                model_path=str(tflite_path), num_threads=1
            )
            interp.allocate_tensors()
            info["input_shape"] = tuple(
                int(v) for v in interp.get_input_details()[0]["shape"][1:4]
            )
        except Exception:
            pass
    return info


def _collect_db_stats() -> Dict[str, Any]:
    """Raccoglie statistiche dal database SQLite."""
    stats: Dict[str, Any] = {
        "total_diagnoses":  0,
        "real_diagnoses":   0,
        "top_classes":      [],
        "last_diagnosis":   "",
        "overall_risks":    {},
    }
    db_path = _ROOT / "delta.db"
    if not db_path.exists():
        return stats
    try:
        con = sqlite3.connect(str(db_path))
        cur = con.cursor()
        # Totale diagnosi
        cur.execute("SELECT COUNT(*) FROM diagnoses")
        stats["total_diagnoses"] = cur.fetchone()[0]
        # Solo diagnosi reali (non simulate)
        cur.execute(
            "SELECT COUNT(*) FROM diagnoses WHERE simulated = 0 OR simulated IS NULL"
        )
        stats["real_diagnoses"] = cur.fetchone()[0]
        # Top classi
        cur.execute(
            "SELECT ai_class, COUNT(*) AS cnt FROM diagnoses "
            "GROUP BY ai_class ORDER BY cnt DESC LIMIT 5"
        )
        stats["top_classes"] = cur.fetchall()
        # Ultima diagnosi
        cur.execute(
            "SELECT timestamp FROM diagnoses ORDER BY id DESC LIMIT 1"
        )
        row = cur.fetchone()
        stats["last_diagnosis"] = row[0] if row else ""
        # Distribuzione rischi
        cur.execute(
            "SELECT overall_risk, COUNT(*) FROM diagnoses GROUP BY overall_risk"
        )
        stats["overall_risks"] = dict(cur.fetchall())
        con.close()
    except Exception as exc:
        logger.debug("Errore raccolta stats DB: %s", exc)
    return stats


def _collect_requirements() -> List[str]:
    """Legge requirements.txt (solo righe attive)."""
    req_path = _ROOT / "requirements.txt"
    reqs = []
    if req_path.exists():
        for line in req_path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                reqs.append(stripped)
    return reqs


def _collect_config_summary() -> Dict[str, Any]:
    """Importa core/config.py e raccoglie parametri chiave."""
    summary: Dict[str, Any] = {}
    config_path = _ROOT / "core" / "config.py"
    spec = importlib.util.spec_from_file_location("delta_cfg_pub", config_path)
    mod  = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
        mc = getattr(mod, "MODEL_CONFIG", {})
        sc = getattr(mod, "SENSOR_CONFIG", {})
        qc = getattr(mod, "QUANTUM_CONFIG", {})
        summary["confidence_threshold"]    = mc.get("confidence_threshold", 0.65)
        summary["preflight_min_confidence"]= mc.get("preflight_min_confidence", 0.50)
        summary["num_threads"]             = mc.get("num_threads", 4)
        summary["temp_optimal"]            = f"{sc.get('temp_optimal_min','?')}–{sc.get('temp_optimal_max','?')} °C"
        summary["humidity_optimal"]        = f"{sc.get('humidity_optimal_min','?')}–{sc.get('humidity_optimal_max','?')} %"
        summary["n_qubits"]                = qc.get("n_qubits", 4)
        summary["grover_iterations"]       = qc.get("grover_iterations", 3)
    except Exception as exc:
        logger.debug("Errore lettura config: %s", exc)
    return summary


# ─────────────────────────────────────────────────────────────
# GENERAZIONE README
# ─────────────────────────────────────────────────────────────

def _generate_readme(
    git:    Dict[str, Any],
    model:  Dict[str, Any],
    reqs:   List[str],
    cfg:    Dict[str, Any],
    version: str,
) -> str:
    """Genera il contenuto del README.md.

    Non include dati operativi locali (diagnosi, statistiche DB):
    rimangono esclusivamente sull'installazione locale.
    """
    repo_url  = git.get("repo_url",  "https://github.com/Proctor81/DELTA-PLANT")
    owner     = git.get("owner",     "Proctor81")
    repo_name = git.get("repo_name", "DELTA-PLANT")
    now       = datetime.now().strftime("%d/%m/%Y %H:%M")
    labels    = model.get("labels", [])
    n_classes = model.get("n_classes", len(labels))
    shape_str = str(model.get("input_shape", "224\u00d7224\u00d73"))
    size_kb   = model.get("model_size_kb", 0)

    # Badge — solo metadati tecnici, nessun dato operativo
    badges = (
        f"![Python](https://img.shields.io/badge/Python-3.12-blue?logo=python)\n"
        f"![Platform](https://img.shields.io/badge/Platform-Raspberry%20Pi%205-red?logo=raspberry-pi)\n"
        f"![AI](https://img.shields.io/badge/AI-TFLite%20float16-orange)\n"
        f"![License](https://img.shields.io/badge/License-Proprietary-lightgrey)\n"
        f"![Version](https://img.shields.io/badge/Version-{version}-green)\n"
    )

    # Sezione classi diagnostiche
    labels_md = "\n".join(f"| {i+1} | `{lbl}` |" for i, lbl in enumerate(labels))
    if not labels_md:
        labels_md = "| — | *(nessuna label trovata)* |"

    # Dipendenze
    reqs_md = "\n".join(f"- `{r}`" for r in reqs) or "- *(requirements.txt non trovato)*"

    readme = f"""# 🌿 DELTA Plant - AI & Robotics Orchestrator per la Salute delle Piante

{badges}

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
| **Analisi fogliare (default)** | Architettura v3.0 leaf-only (fiore/frutto opzionali via config) |
| **{n_classes} classi diagnostiche** | Modello TFLite float16 — input `{shape_str}` px — {size_kb} KB |
| **21 regole esperte** | 12 foglia + 4 fiore + 5 frutto — valutazione in parallelo |
| **Oracolo Quantistico di Grover** | {cfg.get('n_qubits', 4)} qubit, {cfg.get('grover_iterations', 3)} iterazioni, 16 stati di rischio — Quantum Risk Score [0,1] |
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
| Formato | TensorFlow Lite float16 (input float32) |
| Dimensione | {size_kb} KB |
| Input shape | `{shape_str}` |
| Soglia confidenza | {int(cfg.get('confidence_threshold', 0.65) * 100)}% |
| Soglia preflight gate | {int(cfg.get('preflight_min_confidence', 0.50) * 100)}% |
| Thread inferenza | {cfg.get('num_threads', 4)} |

### Classi diagnostiche — foglia

| # | Classe |
|---|--------|
{labels_md}

---

## 🌡 Sensori supportati

| Sensore | Parametri | Protocollo |
|---|---|---|
| BME680 | Temperatura, Umidità, Pressione, VOC | I2C `0x76` |
| VEML7700 | Luminosità (lux) | I2C `0x10` |
| SCD41 | CO₂ (ppm) | I2C `0x62` |
| ADS1115 | pH, EC (ADC 16-bit) | I2C `0x48` |

**Temperatura ottimale:** {cfg.get('temp_optimal', '18\u201328 \u00b0C')}  
**Umidità ottimale:** {cfg.get('humidity_optimal', '40\u201370 %')}

---

## 🚀 Installazione

### Raspberry Pi 5 (raccomandato)

```bash
git clone {repo_url} ~/DELTA
cd ~/DELTA
chmod +x install_raspberry.sh
sudo ./install_raspberry.sh
sudo reboot
```

### Manuale (qualsiasi sistema)

```bash
git clone {repo_url}
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

{reqs_md}

---

## 🔬 Oracolo Quantistico di Grover

DELTA integra una simulazione classica esatta dell'Algoritmo di Grover per la  
quantificazione del rischio agronomico composito:

- **{cfg.get('n_qubits', 4)} qubit** → 16 stati di rischio
- **{cfg.get('grover_iterations', 3)} iterazioni** Grover (ottimale per ≤5 stati avversi attivi)
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

Software proprietario — Copyright © 2026 Paolo Ciccolella. All rights reserved.  
Non è consentita la ridistribuzione o il riutilizzo senza autorizzazione scritta.

---

> ⚠️ **Privacy:** tutte le diagnosi, le analisi e i dati operativi raccolti
> da DELTA rimangono **esclusivamente in locale** sul dispositivo in uso.
> Nessun dato personale o agronomico viene trasmesso a GitHub o a servizi esterni.

---

*README generato automaticamente da DELTA v{version} — {now}*
"""
    return readme


# ─────────────────────────────────────────────────────────────
# GENERAZIONE RELEASE NOTES
# ─────────────────────────────────────────────────────────────

def _generate_release_notes(
    version: str,
    changelog: List[str],
    git: Dict[str, Any],
    model: Dict[str, Any],
) -> str:
    """Genera RELEASE.md con changelog automatico.

    Non include dati operativi locali (diagnosi, statistiche DB).
    """
    now = datetime.now().strftime("%d/%m/%Y %H:%M")
    commits_md = "\n".join(f"- {c}" for c in changelog) or "- Nessun commit nuovo dall'ultimo tag."
    last_tag = git.get("last_tag", "primo rilascio")
    return f"""# Release {version} — {datetime.now().strftime('%d %B %Y')}

> Generato automaticamente da DELTA il {now}

## Changelog

{commits_md}

## Informazioni tecniche

| | |
|---|---|
| Classi modello AI | {model.get('n_classes', 0)} |
| Dimensione modello | {model.get('model_size_kb', 0)} KB |
| Branch | `{git.get('branch', 'main')}` |
| Tag precedente | `{last_tag or 'N/A'}` |

## Note di installazione

- Raspberry Pi 5 (aarch64): `pip install ai-edge-litert==1.2.0`
- Versioni `ai-edge-litert >= 1.3.0` causano segfault su BCM2712 — **non aggiornare**
- Python 3.12 richiesto — Python ≥ 3.13 non supportato da TensorFlow/TFLite

---
*Pubblicato con DELTA GitHub Publisher — `interface/github_publisher.py`*
"""


# ─────────────────────────────────────────────────────────────
# PIPELINE DI PUBBLICAZIONE
# ─────────────────────────────────────────────────────────────

class GitHubPublisher:
    """Gestisce la pubblicazione automatica su GitHub."""

    def __init__(self):
        self._git = _collect_git_info()

    # ── Interfaccia principale ────────────────────────────────

    def run(self):
        """Menu interattivo di pubblicazione."""
        print(f"\n{BOLD}{'═' * 54}{RESET}")
        print(f"{BOLD}  {BLUE}🚀  DELTA — PUBBLICA SU GITHUB{RESET}{BOLD}  {RESET}")
        print(f"{BOLD}{'═' * 54}{RESET}")
        print(f"  Repository: {CYAN}{self._git.get('repo_url', 'N/A')}{RESET}")
        print(f"  Branch:     {CYAN}{self._git.get('branch', 'main')}{RESET}")
        print(f"  Commit tot: {CYAN}{self._git.get('commit_count', '?')}{RESET}")
        clean = self._git.get("status_clean", False)
        print(f"  Working dir: {'✔ pulita' if clean else f'{YELLOW}⚠ modifiche non committate{RESET}'}")
        print()

        # Determina versione suggerita
        last_tag = self._git.get("last_tag", "")
        suggested = self._suggest_version(last_tag)
        print(f"  Ultimo tag:  {CYAN}{last_tag or '(nessuno)'}{RESET}")
        print(f"  Nuova versione suggerita: {GREEN}{suggested}{RESET}")
        print()

        print(f"  {BOLD}[1]{RESET} Pubblicazione rapida         (README + RELEASE + commit + tag + push)")
        print(f"  {BOLD}[2]{RESET} Solo aggiorna README.md      (commit + push, senza nuovo tag)")
        print(f"  {BOLD}[3]{RESET} Anteprima dati raccolti       (nessuna modifica)")
        print(f"  {BOLD}[0]{RESET} Annulla")
        print()

        scelta = input(f"{BOLD}> Scelta: {RESET}").strip()
        print()

        if scelta == "1":
            self._full_publish(suggested)
        elif scelta == "2":
            self._readme_only()
        elif scelta == "3":
            self._preview()
        else:
            print(f"{DIM}Operazione annullata.{RESET}")

    # ── Pubblicazione completa ────────────────────────────────

    def _full_publish(self, suggested_version: str):
        """Raccoglie dati, aggiorna README + RELEASE, crea tag, push."""
        # Chiede conferma versione
        version = input(
            f"  Versione da pubblicare [{CYAN}{suggested_version}{RESET}]: "
        ).strip() or suggested_version

        if not re.match(r'^v?\d+\.\d+(\.\d+)?(-\w+)?$', version):
            print(f"{RED}✘ Formato versione non valido (es. v2.0.1).{RESET}")
            return

        if not version.startswith("v"):
            version = "v" + version

        print(f"\n{BOLD}Raccolta dati dal software...{RESET}")
        data = self._collect_all()
        self._show_summary(data)
        print()

        confirm = input(
            f"{YELLOW}⚠ Pubblicare {BOLD}{version}{RESET}{YELLOW} su GitHub? [s/N]: {RESET}"
        ).strip().lower()
        if confirm != "s":
            print(f"{DIM}Pubblicazione annullata.{RESET}")
            return

        self._do_publish(version, data, create_tag=True)

    def _readme_only(self):
        """Aggiorna solo il README e fa push, senza nuovo tag."""
        print(f"\n{BOLD}Raccolta dati dal software...{RESET}")
        data = self._collect_all()
        self._do_publish(
            version=self._git.get("last_tag", "v2.0"),
            data=data,
            create_tag=False,
        )

    def _do_publish(self, version: str, data: Dict[str, Any], create_tag: bool):
        """Esegue la pubblicazione: scrive file, commit, tag, push."""
        print(f"\n{BOLD}{'─' * 40}{RESET}")

        # ── 1. Genera e scrive README.md ──────────────────────
        self._step("Generazione README.md")
        readme_content = _generate_readme(
            git=data["git"],
            model=data["model"],
            reqs=data["reqs"],
            cfg=data["cfg"],
            version=version,
        )
        readme_path = _ROOT / "README.md"
        readme_path.write_text(readme_content, encoding="utf-8")
        self._ok(f"README.md aggiornato ({len(readme_content)} caratteri)")

        # ── 2. Genera e scrive RELEASE.md ─────────────────────
        self._step("Generazione RELEASE.md")
        changelog = _collect_changelog(data["git"].get("last_tag", ""))
        release_content = _generate_release_notes(
            version=version,
            changelog=changelog,
            git=data["git"],
            model=data["model"],
        )
        release_path = _ROOT / "RELEASE.md"
        release_path.write_text(release_content, encoding="utf-8")
        self._ok(f"RELEASE.md scritto ({len(changelog)} commit nel changelog)")

        # ── 3. Rigenera manuale PDF ───────────────────────────
        self._step("Rigenerazione manuale PDF")
        try:
            result = subprocess.run(
                [sys.executable, str(_ROOT / "Manuale" / "genera_manuale.py")],
                cwd=str(_ROOT),
                capture_output=True,
                text=True,
                timeout=120,
            )
            if result.returncode == 0:
                self._ok("Manuale/DELTA_Manuale_Utente.pdf rigenerato")
            else:
                self._warn(f"Manuale non rigenerato: {result.stderr.strip()[:80]}")
        except Exception as exc:
            self._warn(f"Manuale non rigenerato: {exc}")

        # ── 4. Stage e commit ─────────────────────────────────
        self._step("Stage file modificati")
        files_to_add = ["README.md", "RELEASE.md", "Manuale/DELTA_Manuale_Utente.pdf"]
        result = subprocess.run(
            ["git", "add"] + files_to_add,
            cwd=str(_ROOT),
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            self._fail(f"git add fallito: {result.stderr.strip()}")
            return

        # Verifica se c'è qualcosa da committare
        staged = subprocess.run(
            ["git", "diff", "--cached", "--name-only"],
            cwd=str(_ROOT),
            capture_output=True,
            text=True,
        ).stdout.strip()

        if staged:
            self._step("Commit")
            msg = (
                f"docs: pubblica {version} — README + RELEASE + manuale aggiornati\n\n"
                f"- README.md generato automaticamente (metadati tecnici)\n"
                f"- RELEASE.md con changelog da git log\n"
                f"- Manuale PDF rigenerato ({data['model'].get('n_classes', '?')} classi)\n"
                f"- Pubblicato con DELTA GitHub Publisher\n"
                f"- Dati operativi locali NON inclusi (privacy garantita)"
            )
            result = subprocess.run(
                ["git", "commit", "-m", msg],
                cwd=str(_ROOT),
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                self._fail(f"git commit fallito: {result.stderr.strip()}")
                return
            self._ok(f"Commit creato: docs: pubblica {version}")
        else:
            self._ok("Nessuna modifica da committare (file già aggiornati)")

        # ── 5. Tag ────────────────────────────────────────────
        if create_tag:
            self._step(f"Creazione tag {version}")
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
            result = subprocess.run(
                ["git", "tag", "-a", version, "-m",
                 f"DELTA {version} — {now_str}"],
                cwd=str(_ROOT),
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                self._ok(f"Tag {version} creato")
            else:
                self._warn(f"Tag non creato (già esistente?): {result.stderr.strip()[:60]}")

        # ── 6. Push ───────────────────────────────────────────
        self._step("Push su GitHub")

        # Configura gh come credential helper se disponibile e non già impostato
        import shutil as _shutil
        if _shutil.which("gh"):
            _cred_check = subprocess.run(
                ["git", "config", "--global", "credential.https://github.com.helper"],
                capture_output=True, text=True,
            )
            if "gh" not in _cred_check.stdout:
                subprocess.run(
                    ["gh", "auth", "setup-git"],
                    capture_output=True, text=True,
                )

        push_args = ["git", "push", "origin", data["git"]["branch"]]
        if create_tag:
            push_args += ["--tags"]
        result = subprocess.run(
            push_args,
            cwd=str(_ROOT),
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            self._ok("Push completato")
        else:
            stderr = result.stderr.strip()
            hint = ""
            if "authentication" in stderr.lower() or "credentials" in stderr.lower() or "403" in stderr or "401" in stderr:
                hint = (
                    "\n\n  💡 Suggerimento: eseguire da terminale:\n"
                    "     gh auth login\n"
                    "     gh auth setup-git"
                )
            self._fail(
                f"Push fallito:\n{stderr}\n"
                f"Verificare connessione internet e credenziali GitHub.{hint}"
            )
            return

        # ── 7. Riepilogo finale ───────────────────────────────
        print(f"\n{GREEN}{BOLD}{'═' * 54}{RESET}")
        print(f"{GREEN}{BOLD}  ✔ PUBBLICAZIONE COMPLETATA{RESET}")
        print(f"{GREEN}{BOLD}{'═' * 54}{RESET}")
        repo_url = data["git"].get("repo_url", "")
        if repo_url:
            print(f"\n  🔗 {CYAN}{repo_url}{RESET}")
            if create_tag:
                print(f"  🏷  {CYAN}{repo_url}/releases/tag/{version}{RESET}")
        print()

        logger.info(
            "Pubblicazione GitHub completata: versione=%s tag=%s",
            version, create_tag,
        )

    # ── Preview ───────────────────────────────────────────────

    def _preview(self):
        """Mostra un riepilogo dei dati che verrebbero pubblicati."""
        print(f"\n{BOLD}Raccolta dati in corso...{RESET}")
        data = self._collect_all()
        self._show_summary(data)
        print()

    def _show_summary(self, data: Dict[str, Any]):
        git   = data["git"]
        model = data["model"]
        db    = data["db"]
        cfg   = data["cfg"]
        reqs  = data["reqs"]

        print(f"\n  {BOLD}{CYAN}── GIT ───────────────────────────────────{RESET}")
        print(f"  Branch:        {git.get('branch')}")
        print(f"  Repository:    {git.get('repo_url')}")
        print(f"  Ultimo tag:    {git.get('last_tag') or '(nessuno)'}")
        print(f"  Commit totali: {git.get('commit_count')}")

        print(f"\n  {BOLD}{CYAN}── MODELLO AI ────────────────────────────{RESET}")
        print(f"  Classi:        {model.get('n_classes')} ({', '.join(model.get('labels', [])[:4])}...)")
        print(f"  Input shape:   {model.get('input_shape', 'N/A')}")
        print(f"  Dimensione:    {model.get('model_size_kb')} KB")
        print(f"  TFLite OK:     {'✔' if model.get('tflite_ok') else '✘'}")

        print(f"\n  {BOLD}{CYAN}── DATABASE ──────────────────────────────{RESET}")
        print(f"  Diagnosi tot:  {db.get('total_diagnoses')}")
        print(f"  Diagnosi reali:{db.get('real_diagnoses')}")
        print(f"  Ultima:        {db.get('last_diagnosis') or 'N/A'}")
        for cls, cnt in db.get("top_classes", [])[:3]:
            print(f"    • {cls:<25} {cnt} diagnosi")

        print(f"\n  {BOLD}{CYAN}── CONFIG ────────────────────────────────{RESET}")
        print(f"  Confidenza:    {int(cfg.get('confidence_threshold', 0.65)*100)}%")
        print(f"  T ottimale:    {cfg.get('temp_optimal')}")
        print(f"  Grover:        {cfg.get('n_qubits')} qubit × {cfg.get('grover_iterations')} iter.")

        print(f"\n  {BOLD}{CYAN}── DIPENDENZE ────────────────────────────{RESET}")
        for r in reqs:
            print(f"    {r}")

    # ── Helpers ───────────────────────────────────────────────

    @staticmethod
    def _collect_all() -> Dict[str, Any]:
        return {
            "git":   _collect_git_info(),
            "model": _collect_model_info(),
            "db":    _collect_db_stats(),
            "reqs":  _collect_requirements(),
            "cfg":   _collect_config_summary(),
        }

    @staticmethod
    def _suggest_version(last_tag: str) -> str:
        """Incrementa il patch number dell'ultimo tag."""
        if not last_tag:
            return "v2.0.0"
        m = re.match(r"v?(\d+)\.(\d+)(?:\.(\d+))?", last_tag)
        if not m:
            return "v2.0.0"
        major, minor, patch = int(m.group(1)), int(m.group(2)), int(m.group(3) or 0)
        return f"v{major}.{minor}.{patch + 1}"

    @staticmethod
    def _step(msg: str):
        print(f"  {DIM}»{RESET} {msg}...", end="", flush=True)

    @staticmethod
    def _ok(msg: str = ""):
        print(f"\r  {GREEN}✔{RESET} {msg}" if msg else f" {GREEN}✔{RESET}")

    @staticmethod
    def _warn(msg: str):
        print(f"\r  {YELLOW}⚠{RESET} {msg}")

    @staticmethod
    def _fail(msg: str):
        print(f"\r  {RED}✘{RESET} {msg}")
        logger.error("GitHub Publisher: %s", msg)
