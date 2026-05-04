"""
DELTA - interface/cli.py
Interfaccia a riga di comando per interazione utente.
Gestisce menu principale, visualizzazione diagnosi e sessione fine-tuning.
"""

import logging
from typing import TYPE_CHECKING, Dict, Any, List
from core.config import FEATURE_FLAGS

if TYPE_CHECKING:
    from core.agent import DeltaAgent

logger = logging.getLogger("delta.interface.cli")

# Palette simboli per terminale
SYMBOL_OK = "✔"
SYMBOL_WARN = "⚠"
SYMBOL_ERR = "✘"
SYMBOL_INFO = "ℹ"
BATCH_DONE = object()

RISK_COLORS = {
    "nessuno":  "\033[92m",   # Verde
    "basso":    "\033[96m",   # Ciano
    "medio":    "\033[93m",   # Giallo
    "alto":     "\033[91m",   # Rosso chiaro
    "critico":  "\033[31;1m", # Rosso bold
}
RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"


class CLI:
    """Interfaccia testuale interattiva per l'operatore DELTA."""

    def __init__(self, agent: "DeltaAgent"):
        self.agent = agent

    # ─────────────────────────────────────────────
    # MENU PRINCIPALE
    # ─────────────────────────────────────────────

    def run(self):
        """Loop principale del menu interattivo."""
        self._print_banner()

        # PROTEZIONE: la chat NON deve mai partire senza scelta esplicita 'C'.
        # Se la chat parte subito, controllare che non ci siano chiamate a _run_free_chat() fuori da questo blocco!
        # Debug: se _run_free_chat viene chiamata fuori da qui, solleva eccezione.
        self._chat_started = False

        while True:
            finetune_enabled = FEATURE_FLAGS.get("enable_runtime_finetuning", False)
            print(f"\n{BOLD}═══ MENU PRINCIPALE ═══{RESET}")
            print("  [1] Avvia diagnosi pianta")
            if finetune_enabled:
                print("  [2] Fine-tuning modello AI")
            else:
                print("  [2] Fine-tuning modello AI (disabilitato)")
            print("  [3] Mostra dati sensori correnti")
            print("  [4] Esporta dati in Excel")
            print("  [5] Visualizza ultime diagnosi")
            print(f"  [6] {BOLD}DELTA Academy{RESET}  ← Formazione operatore")
            print(f"  [7] {BOLD}Pannello Amministratore{RESET}  🔐")
            print(f"  [8] Apri cartella immagini input  📂")
            print(f"  [9] Preflight AI (modello + labels + immagine test)")
            print(f"  [C] {BOLD}Chat domanda/risposta libera{RESET} 💬")
            print(f"  [L] {BOLD}Licenza Software DELTA Plant{RESET}  ©")
            print("  [0] Esci")

            scelta = input(f"\n{BOLD}> Scelta: {RESET}").strip().upper()

            if scelta == "1":
                self._run_diagnosis_flow()
            elif scelta == "2":
                if finetune_enabled:
                    self._run_finetuning_flow()
                else:
                    print(f"{SYMBOL_INFO} Fine-tuning runtime disabilitato a livello di sistema.")
            elif scelta == "3":
                self._show_sensor_data()
            elif scelta == "4":
                self._export_excel()
            elif scelta == "5":
                self._show_recent_diagnoses()
            elif scelta == "6":
                self._run_academy()
            elif scelta == "7":
                self._run_admin()
            elif scelta == "8":
                self._show_input_folder_info()
            elif scelta == "9":
                self._run_preflight_ai()
            elif scelta == "C":
                # Avvia la chat SOLO se l'utente sceglie 'C'
                self._chat_started = True
                self._run_free_chat()
                self._chat_started = False
            elif scelta == "L":
                self._show_license()
            elif scelta == "0":
                print(f"\n{DIM}Chiusura DELTA in corso...{RESET}")
                break
            else:
                print(f"{SYMBOL_WARN} Scelta non valida.")

    def _run_free_chat(self):
        """Modalità chat domanda/risposta libera con l'orchestrator DELTA."""
        # Protezione: questa funzione deve essere chiamata SOLO dal menu principale!
        if not getattr(self, '_chat_started', False):
            raise RuntimeError("_run_free_chat() chiamata fuori dal menu principale! Protezione attiva.")
        print("[DEBUG] Avvio modalità chat libera (_run_free_chat)")
        print(f"\n{BOLD}─── CHAT LIBERA CON DELTA ORCHESTRATOR ───{RESET}")
        print(f"Digita una domanda o un comando. Scrivi '/exit' per tornare al menu.")
        try:
            from delta_orchestrator.integration.delta_bridge import orchestrate_task
            from delta_orchestrator.state.schema import DeltaOrchestratorState
        except ImportError:
            print(f"{SYMBOL_ERR} Orchestrator non disponibile o non installato.")
            return
        state = DeltaOrchestratorState()
        while True:
            domanda = input(f"{BOLD}Tu:{RESET} ").strip()
            if domanda.lower() == "/exit":
                print(f"{DIM}Uscita dalla chat libera.{RESET}")
                break
            if not domanda:
                continue
            try:
                import asyncio
                result = asyncio.run(orchestrate_task(domanda, state))
                risposta = result.get("final_answer") or str(result)
                print(f"{BOLD}DELTA:{RESET} {risposta}")
            except Exception as exc:
                print(f"{SYMBOL_ERR} Errore nella chat: {exc}")

    # ─────────────────────────────────────────────
    # LICENZA SOFTWARE
    # ─────────────────────────────────────────────

    @staticmethod
    def _show_license():
        """Mostra la licenza software DELTA PLANT."""
        print(f"""
{BOLD}{'═' * 62}
    DELTA PLANT SOFTWARE LICENSE
{'═' * 62}{RESET}

{BOLD}Copyright © 2026 Paolo Ciccolella. All rights reserved.{RESET}
{BOLD}Software Release: v3.0{RESET}
{DIM}(This release field must be updated at each official software release.){RESET}

{'─' * 62}
{BOLD}1. CORE SYSTEM (PROPRIETARY){RESET}

The DELTA PLANT core system, including but not limited to:
  - main control software
  - sensor management system
  - automation engine
  - safety and execution modules

is proprietary software.

You are NOT permitted to:
  - copy, modify, distribute, or reverse engineer the core system
  - use the core system outside the authorized DELTA ecosystem
  - remove or alter copyright notices

Any unauthorized use of the core system is strictly prohibited.

{'─' * 62}
{BOLD}2. MODULES / EXTENSIONS (OPEN SOURCE COMPONENTS){RESET}

Certain modules, plugins, or SDK components of DELTA PLANT may be
released under open-source licenses (such as MIT or Apache 2.0).

These components are clearly marked in their respective directories.

For open-source modules:
  - you may use, modify, and distribute them
  - you must respect the license specified in each module
  - attribution to the original author is required

{'─' * 62}
{BOLD}3. AI SERVICES AND CLOUD FEATURES{RESET}

Any AI-related services, cloud APIs, or external model integrations
(including but not limited to language model processing) are provided
as a service layer and are NOT part of the open-source components.

These services may:
  - require authentication
  - be subject to usage limits
  - be modified or discontinued at any time

{'─' * 62}
{BOLD}4. LIABILITY DISCLAIMER{RESET}

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND.

The author is not responsible for:
  - hardware damage
  - data loss
  - incorrect automation behavior
  - misuse of the system

{'─' * 62}
{BOLD}5. SCIENTIFIC RESEARCH USE{RESET}

Scientific and academic research use of the DELTA PLANT core system
is allowed only for non-commercial purposes, subject to all terms in
this license.

For research use, you must:
    - keep all copyright and license notices intact
    - provide clear attribution to the author in publications and reports
    - use the software in compliance with applicable laws and ethical standards
    - avoid redistributing proprietary core code or derivative proprietary builds

Research use does NOT grant ownership or relicensing rights on the
DELTA PLANT proprietary core system.

{'─' * 62}
{BOLD}6. COMMERCIAL USE{RESET}

Commercial use of the DELTA PLANT core system requires a separate
written license agreement with the author.

Open-source modules may be used commercially according to their
respective licenses.

{'─' * 62}
{BOLD}7. FINAL TERMS{RESET}

By using any part of DELTA PLANT, you agree to these terms.

Violation of this license may result in termination of usage
rights and legal action.

{'─' * 62}
{DIM}END OF LICENSE{RESET}
{'═' * 62}
""")
        input(f"{DIM}Premi INVIO per tornare al menu...{RESET}")

    # ─────────────────────────────────────────────
    # CARTELLA IMMAGINI INPUT
    # ─────────────────────────────────────────────

    def _show_input_folder_info(self):
        """Mostra informazioni sulla cartella immagini di input e il suo contenuto."""
        from vision.camera import ImageFolderLoader
        from core.config import INPUT_IMAGES_DIR

        loader = ImageFolderLoader()
        folder = loader.get_folder_path()
        images = loader.list_images()

        print(f"\n{BOLD}─── CARTELLA IMMAGINI INPUT ───{RESET}")
        print(f"  Percorso: {folder}")
        print(f"  Formati supportati: JPG, PNG, BMP, TIFF, WEBP")

        if not images:
            print(f"\n  {SYMBOL_WARN} Cartella vuota.")
            print(f"  Copia le immagini in: {folder}")
        else:
            print(f"\n  {len(images)} immagine(i) presenti:")
            for p in images:
                size_kb = p.stat().st_size // 1024
                print(f"    • {p.name}  ({size_kb} KB)")

        print(f"\n  {SYMBOL_INFO} Avvia una diagnosi (menu [1]) per selezionare un'immagine.")

    def _run_preflight_ai(self):
        """Esegue validazione completa modello/labels/immagine test dal menu CLI."""
        from ai.preflight_validator import validate_model_artifacts
        from core.config import MODEL_CONFIG

        print(f"\n{BOLD}─── PREFLIGHT AI ───{RESET}")
        default_image = MODEL_CONFIG["validation_image_path"]
        user_image = input(
            f"Percorso immagine test (INVIO per default: {default_image}): "
        ).strip()
        image_path = user_image or default_image

        try:
            report = validate_model_artifacts(
                model_path=MODEL_CONFIG["model_path"],
                labels_path=MODEL_CONFIG["labels_path"],
                image_path=image_path,
                threads=MODEL_CONFIG["num_threads"],
                top_k=3,
            )
            print(f"{SYMBOL_OK} Preflight completato con successo")
            print(f"  Classe predetta: {report['predicted_class']}")
            print(f"  Confidenza: {report['confidence'] * 100:.2f}%")
            print(f"  Input shape: {report['input_shape']}")
            print(f"  Output shape: {report['output_shape']}")
        except Exception as exc:
            print(f"{SYMBOL_ERR} Preflight fallito: {exc}")
            logger.error("Preflight AI fallito da CLI: %s", exc, exc_info=True)

    # ─────────────────────────────────────────────
    # DELTA ACADEMY
    # ─────────────────────────────────────────────

    def _run_academy(self):
        """Avvia il modulo DELTA Academy per la formazione dell'operatore."""
        from interface.academy import DeltaAcademy
        academy = DeltaAcademy()
        academy.run()

    def _run_admin(self):
        """Avvia il Pannello Amministratore (richiede password)."""
        from interface.admin import AdminPanel
        panel = AdminPanel(self.agent)
        panel.run()

    # ─────────────────────────────────────────────
    # FLUSSO DIAGNOSI
    # ─────────────────────────────────────────────

    def _run_diagnosis_flow(self):
        """Gestisce il flusso completo di una diagnosi."""
        print(f"\n{BOLD}─── DIAGNOSI PIANTA ───{RESET}")

        # Opzione: sensori manuali
        use_manual = self._ask_yes_no("Inserire dati sensori manualmente?", default=False)
        sensor_data = None
        if use_manual:
            sensor_data = self.agent.sensor_reader.read_manual()

        # ── Selezione sorgente immagine ───────────────────────
        image = None
        camera_ok = self.agent.camera._backend is not None

        if not camera_ok:
            print(f"\n{SYMBOL_WARN} Camera non disponibile.")
            use_folder = True
        else:
            use_folder = self._ask_yes_no(
                "Caricare immagine da cartella di input invece della camera?",
                default=False,
            )

        if use_folder:
            image = self._select_image_from_folder()
            if image is BATCH_DONE:
                return
            if image is None:
                print(f"{SYMBOL_ERR} Nessuna immagine selezionata. Diagnosi annullata.")
                return
        else:
            print(f"{SYMBOL_INFO} Acquisizione immagine dalla camera...")

        print(f"{SYMBOL_INFO} Analisi in corso...")

        try:
            record = self.agent.run_diagnosis(sensor_data=sensor_data, image=image)
            self._print_diagnosis_result(record)

            # Active learning: confidenza bassa
            if record["diagnosis"].get("needs_human_review"):
                self._handle_low_confidence(record)

        except Exception as exc:
            print(f"\n{SYMBOL_ERR} Errore durante la diagnosi: {exc}")
            logger.error("Errore diagnosi CLI: %s", exc, exc_info=True)

    def _select_image_from_folder(self):
        """
        Mostra le immagini disponibili nella cartella di input e consente
        all'utente di selezionarne una. Restituisce l'array numpy BGR o None.
        """
        from vision.camera import ImageFolderLoader
        import numpy as np

        loader = ImageFolderLoader()
        folder = loader.get_folder_path()
        images = loader.list_images()

        print(f"\n{BOLD}─── SELEZIONE IMMAGINE DA CARTELLA ───{RESET}")
        print(f"  Cartella: {folder}")

        if not images:
            print(f"\n{SYMBOL_WARN} La cartella è vuota.")
            print(f"  Inserire immagini in: {folder}")
            print(f"  Formati supportati: JPG, PNG, BMP, TIFF, WEBP")
            return None

        print(f"\n  {len(images)} immagine(i) disponibile(i):\n")
        for i, p in enumerate(images):
            size_kb = p.stat().st_size // 1024
            print(f"  [{i}] {p.name}  ({size_kb} KB)")

        print(f"  [A] Analizza tutte in sequenza")
        scelta = input(f"\n{BOLD}> Seleziona immagine (indice o A): {RESET}").strip().lower()

        if scelta == "a":
            # Modalita batch: il ciclo viene gestito internamente e il flusso termina qui.
            print(f"{SYMBOL_INFO} Modalità sequenziale: verrà analizzata ogni immagine.")
            return self._analyze_all_images(images, loader)

        if scelta.isdigit():
            idx = int(scelta)
            if 0 <= idx < len(images):
                frame = loader.load_image(images[idx])
                if frame is None:
                    print(f"{SYMBOL_ERR} Impossibile caricare l'immagine.")
                return frame

        print(f"{SYMBOL_WARN} Selezione non valida.")
        return None

    def _analyze_all_images(self, images, loader):
        """
        Analizza tutte le immagini nella cartella in sequenza.
        Restituisce BATCH_DONE per chiudere il flusso diagnosi corrente senza errori.
        """
        from vision.camera import ImageFolderLoader

        print(f"\n{BOLD}Analisi sequenziale di {len(images)} immagine(i)...{RESET}\n")
        for i, img_path in enumerate(images, 1):
            print(f"{'─'*50}")
            print(f"[{i}/{len(images)}] {img_path.name}")
            frame = loader.load_image(img_path)
            if frame is None:
                print(f"  {SYMBOL_ERR} Impossibile caricare — saltata.")
                continue
            try:
                record = self.agent.run_diagnosis(image=frame)
                dx = record.get("diagnosis", {})
                risk = dx.get("overall_risk", "?")
                color = RISK_COLORS.get(risk, "")
                print(f"  Stato: {dx.get('plant_status','N/A')}")
                print(f"  Rischio: {color}{risk.upper()}{RESET}")
                ai = record.get("ai_result", {})
                print(f"  AI: {ai.get('class','N/A')} ({ai.get('confidence',0)*100:.1f}%)")
            except Exception as exc:
                print(f"  {SYMBOL_ERR} Errore diagnosi: {exc}")
                logger.error("Errore diagnosi immagine %s: %s", img_path.name, exc, exc_info=True)

        print(f"\n{SYMBOL_OK} Analisi sequenziale completata. Risultati salvati nel database.")
        return BATCH_DONE

    def _handle_low_confidence(self, record: Dict[str, Any]):
        """Gestisce il caso di confidenza AI bassa: chiede feedback all'utente."""
        print(f"\n{SYMBOL_WARN} {BOLD}Confidenza AI bassa!{RESET}")
        print("Il sistema richiede la tua supervisione per migliorare le diagnosi future.")

        labels = self.agent.model_loader.labels
        print("\nClassi disponibili:")
        for i, lbl in enumerate(labels):
            print(f"  [{i}] {lbl}")

        idx_str = input("Inserisci l'indice della classe corretta (Enter per saltare): ").strip()
        if idx_str.isdigit() and int(idx_str) < len(labels):
            idx = int(idx_str)
            label = labels[idx]
            print(f"{SYMBOL_OK} Etichetta '{label}' registrata per il training futuro.")
            # Salva campione nel dataset fine-tuning (richiede immagine)
            logger.info("Active learning: classe corretta '%s' fornita dall'utente.", label)
        else:
            print(f"{DIM}Nessuna etichetta fornita.{RESET}")

    # ─────────────────────────────────────────────
    # FLUSSO FINE-TUNING
    # ─────────────────────────────────────────────

    def _run_finetuning_flow(self):
        """Gestisce la sessione di fine-tuning del modello."""
        print(f"\n{BOLD}─── FINE-TUNING MODELLO ───{RESET}")

        from ai.fine_tuning import FineTuner
        tuner = FineTuner(self.agent.model_loader)

        stats = tuner.get_dataset_stats()
        print(f"\n{SYMBOL_INFO} Dataset attuale: {stats['total']} campioni")
        for cls, cnt in stats["classes"].items():
            print(f"  • {cls}: {cnt} immagini")

        if stats["total"] == 0:
            print(f"\n{SYMBOL_WARN} Nessun campione nel dataset.")
            print("Esegui prima alcune diagnosi con etichettatura manuale.")
            return

        if not self._ask_yes_no("Avviare fine-tuning ora?", default=True):
            return

        print(f"\n{SYMBOL_INFO} Fine-tuning in corso (potrebbe richiedere alcuni minuti)...")
        success = tuner.run_finetuning()

        if success:
            print(f"{SYMBOL_OK} Fine-tuning completato con successo!")
            if self._ask_yes_no("Caricare il nuovo modello ora?", default=True):
                from core.config import FINETUNING_CONFIG
                self.agent.model_loader.reload(FINETUNING_CONFIG["model_save_path"])
                print(f"{SYMBOL_OK} Nuovo modello caricato.")
        else:
            print(f"{SYMBOL_ERR} Fine-tuning fallito. Controllare il log per dettagli.")

    # ─────────────────────────────────────────────
    # VISUALIZZAZIONE DATI
    # ─────────────────────────────────────────────

    def _show_sensor_data(self):
        """Mostra i dati sensori correnti."""
        print(f"\n{BOLD}─── DATI SENSORI CORRENTI ───{RESET}")
        data = self.agent.get_latest_sensor_data()

        if not data:
            print(f"{SYMBOL_WARN} Nessun dato disponibile (thread sensori non attivo?).")
            return

        fields = [
            ("temperature_c",  "Temperatura",    "°C"),
            ("humidity_pct",   "Umidità",         "%"),
            ("pressure_hpa",   "Pressione",       "hPa"),
            ("light_lux",      "Luminosità",      "lux"),
            ("co2_ppm",        "CO₂",             "ppm"),
            ("ph",             "pH",              ""),
            ("ec_ms_cm",       "EC",              "mS/cm"),
        ]

        for key, label, unit in fields:
            val = data.get(key)
            val_str = f"{val:.2f} {unit}".strip() if val is not None else "N/D"
            print(f"  {label:20s}: {val_str}")

        source = data.get("source", "?")
        ts = data.get("timestamp", "?")
        anomalies = data.get("_anomalies", [])

        print(f"\n  Fonte: {source} | Timestamp: {ts}")
        if anomalies:
            print(f"\n  {SYMBOL_WARN} Anomalie: {len(anomalies)}")
            for a in anomalies:
                print(f"    • {a}")

    def _show_recent_diagnoses(self):
        """Mostra le ultime diagnosi dal database."""
        print(f"\n{BOLD}─── ULTIME DIAGNOSI ───{RESET}")
        records = self.agent.database.get_recent(limit=10)

        if not records:
            print(f"{SYMBOL_WARN} Nessuna diagnosi disponibile.")
            return

        for rec in records:
            risk = rec.get("overall_risk", "?")
            color = RISK_COLORS.get(risk, "")
            print(
                f"  [{rec['id']:4d}] {rec['timestamp'][:19]} | "
                f"{rec.get('plant_status','?'):25s} | "
                f"Rischio: {color}{risk.upper()}{RESET}"
            )

    def _export_excel(self):
        """Esporta tutte le diagnosi in Excel."""
        print(f"\n{SYMBOL_INFO} Esportazione in Excel...")
        records_db = self.agent.database.get_recent(limit=10000)

        if not records_db:
            print(f"{SYMBOL_WARN} Nessun dato da esportare.")
            return

        # Adatta formato DB a formato record agent
        converted = []
        for r in records_db:
            import json as _json
            converted.append({
                "timestamp": r.get("timestamp"),
                "sensor_data": {"source": r.get("sensor_source")},
                "ai_result": {
                    "class": r.get("ai_class"),
                    "confidence": r.get("ai_confidence", 0) / 100,
                    "simulated": bool(r.get("ai_simulated")),
                    "top3": _json.loads(r.get("ai_top3_json") or "[]"),
                },
                "diagnosis": {
                    "plant_status": r.get("plant_status"),
                    "overall_risk": r.get("overall_risk"),
                    "needs_human_review": bool(r.get("needs_review")),
                    "summary": r.get("summary"),
                    "explanation": r.get("explanation"),
                    "activated_rules": _json.loads(r.get("activated_rules") or "[]"),
                    "sensor_snapshot": {
                        "temperature_c": r.get("temperature_c"),
                        "humidity_pct":  r.get("humidity_pct"),
                        "pressure_hpa":  r.get("pressure_hpa"),
                        "light_lux":     r.get("light_lux"),
                        "co2_ppm":       r.get("co2_ppm"),
                        "ph":            r.get("ph"),
                        "ec_ms_cm":      r.get("ec_ms_cm"),
                        "source":        r.get("sensor_source"),
                    },
                },
                "recommendations": _json.loads(r.get("recommendations") or "[]"),
            })

        ok = self.agent.exporter.export_all(converted)
        if ok:
            from core.config import EXPORTS_DIR
            print(f"{SYMBOL_OK} Esportati {len(converted)} record in {EXPORTS_DIR}/")
        else:
            print(f"{SYMBOL_ERR} Errore durante l'esportazione.")

    # ─────────────────────────────────────────────
    # VISUALIZZAZIONE RISULTATO DIAGNOSI
    # ─────────────────────────────────────────────

    def _print_diagnosis_result(self, record: Dict[str, Any]):
        """Stampa in modo leggibile il risultato di una diagnosi."""
        dx   = record.get("diagnosis", {})
        ai   = record.get("ai_result", {})
        recs = record.get("recommendations", [])
        risk = dx.get("overall_risk", "?")
        color = RISK_COLORS.get(risk, "")

        # Analisi organi
        organ_results   = record.get("organ_results", {})
        organ_analyses  = dx.get("organ_analyses", {})
        quantum_risk    = dx.get("quantum_risk", {})

        print(f"\n{'═' * 60}")
        print(f"{BOLD}RISULTATO DIAGNOSI DELTA{RESET}")
        print(f"{'═' * 60}")

        # ── Stato generale ────────────────────────────────────
        print(f"\n{BOLD}Stato pianta:{RESET}  {dx.get('plant_status', 'N/A')}")
        print(f"{BOLD}Rischio:{RESET}       {color}{risk.upper()}{RESET}")

        # ── Analisi foglia ────────────────────────────────────
        print(f"\n{BOLD}Analisi foglia:{RESET}")
        print(f"  Classe AI:    {ai.get('class', 'N/A')} "
              f"({ai.get('confidence', 0) * 100:.1f}%)"
              + (" [SIM]" if ai.get("simulated") else ""))

        # ── Analisi fiore ─────────────────────────────────────
        if "fiore" in organ_analyses:
            fa = organ_analyses["fiore"]
            print(f"\n{BOLD}Analisi fiore:{RESET}")
            print(f"  Classe AI:    {fa.get('class', 'N/A')} "
                  f"({fa.get('confidence', 0) * 100:.1f}%)"
                  + (" [SIM]" if fa.get("simulated") else ""))
        elif organ_results.get("fiore", {}).get("detected"):
            print(f"\n{BOLD}Analisi fiore:{RESET}  Rilevato — analisi AI non disponibile")

        # ── Analisi frutto ────────────────────────────────────
        if "frutto" in organ_analyses:
            fra = organ_analyses["frutto"]
            print(f"\n{BOLD}Analisi frutto:{RESET}")
            print(f"  Classe AI:    {fra.get('class', 'N/A')} "
                  f"({fra.get('confidence', 0) * 100:.1f}%)"
                  + (" [SIM]" if fra.get("simulated") else ""))
        elif organ_results.get("frutto", {}).get("detected"):
            print(f"\n{BOLD}Analisi frutto:{RESET}  Rilevato — analisi AI non disponibile")

        # ── Oracolo Quantistico ───────────────────────────────
        if quantum_risk:
            qrs   = quantum_risk.get("quantum_risk_score", 0.0)
            qlvl  = quantum_risk.get("risk_level", "nessuno")
            qdom  = quantum_risk.get("dominant_description", "N/A")
            qgain = quantum_risk.get("amplification_gain", 1.0)
            qitr  = quantum_risk.get("grover_iterations", 0)
            qcolor = RISK_COLORS.get(qlvl, "")

            print(f"\n{BOLD}Oracolo Quantistico di Grover:{RESET}")
            print(f"  QRS:           {qcolor}{qrs:.4f} [{qlvl.upper()}]{RESET}")
            print(f"  Evento dom.:   {qdom}")
            print(f"  Amplific.:     {qgain:.1f}x  |  Iterazioni Grover: {qitr}")

        # ── Spiegazione ───────────────────────────────────────
        print(f"\n{BOLD}Diagnosi:{RESET}")
        print(dx.get("explanation", "N/A"))

        # ── Raccomandazioni ───────────────────────────────────
        if recs:
            print(f"\n{BOLD}Raccomandazioni:{RESET}")
            for i, rec in enumerate(recs, 1):
                cat = rec.get("category", "?").upper()
                priority = rec.get("priority", "?")
                print(f"\n  [{i}] [{cat}] (Priorità: {priority})")
                print(f"      Problema: {rec.get('problem','')}")
                print(f"      Azione:   {rec.get('action','')}")

        print(f"\n{'═' * 60}")

    # ─────────────────────────────────────────────
    # BANNER
    # ─────────────────────────────────────────────

    @staticmethod
    def _print_banner():
        """Stampa il banner DELTA all'avvio."""
        print(f"""
{BOLD}
╔══════════════════════════════════════════════════════╗
║         DELTA Plant - AI & Robotics Orchestrator     ║
║            per la Salute delle Piante                ║
║               Raspberry Pi 5 + AI HAT 2+             ║
╚══════════════════════════════════════════════════════╝
{DIM}Copyright © 2026 Paolo Ciccolella. All rights reserved.{RESET}
""")

    # ─────────────────────────────────────────────
    # UTILITÀ
    # ─────────────────────────────────────────────

    @staticmethod
    def _ask_yes_no(question: str, default: bool = True) -> bool:
        """Chiede una conferma sì/no all'utente."""
        hint = "[S/n]" if default else "[s/N]"
        risposta = input(f"{question} {hint}: ").strip().lower()
        if risposta == "":
            return default
        return risposta in ("s", "si", "sì", "y", "yes")
