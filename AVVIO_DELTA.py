#!/usr/bin/env python3
"""
DELTA — AVVIO_DELTA.py
Launcher ufficiale per l'operatore DELTA.

Questo file è il punto di accesso sicuro al sistema DELTA.
• Non richiede password per l'avvio.
• Non espone il codice sorgente.
• Supporta tutte le funzionalità hardware (sensori, camera, NPU).
• Il Pannello Amministratore (password protetto) è accessibile
  dall'interno del menu principale selezionando l'opzione [7].

Uso:
    python3 "AVVIO_DELTA.py"
    oppure doppio clic su "AVVIO DELTA.command" (macOS)
"""

import sys
import os

# ── Auto-rilancio con venv se si sta usando il Python di sistema ─
_DELTA_ROOT = os.path.dirname(os.path.abspath(__file__))
_VENV_PYTHON = os.path.join(_DELTA_ROOT, ".venv", "bin", "python")
if os.path.isfile(_VENV_PYTHON) and os.path.abspath(sys.executable) != os.path.abspath(_VENV_PYTHON):
    import subprocess
    sys.exit(subprocess.call([_VENV_PYTHON] + sys.argv))

# Aggiunge la directory del progetto al sys.path
if _DELTA_ROOT not in sys.path:
    sys.path.insert(0, _DELTA_ROOT)


def _print_splash() -> None:
    G = "\033[92m"
    W = "\033[97;1m"
    D = "\033[2m"
    R = "\033[0m"
    print(f"\n{G}")
    print(r"  ██████╗ ███████╗██╗  ████████╗ █████╗ ")
    print(r"  ██╔══██╗██╔════╝██║  ╚══██╔══╝██╔══██╗")
    print(r"  ██║  ██║█████╗  ██║     ██║   ███████║")
    print(r"  ██║  ██║██╔══╝  ██║     ██║   ██╔══██║")
    print(r"  ██████╔╝███████╗███████╗██║   ██║  ██║")
    print(r"  ╚═════╝ ╚══════╝╚══════╝╚═╝   ╚═╝  ╚═╝")
    print(f"{R}")
    print(f"  {W}Detection and Evaluation of Leaf Troubles and Anomalies{R}")
    print(f"  {D}DELTA Plant - AI & Robotics Orchestrator per la Salute delle Piante{R}")
    print(f"  {D}Versione 3.0  |  Raspberry Pi 5 + AI HAT 2+{R}")
    print(f"  {'─' * 65}\n")


def main() -> None:
    _print_splash()

    # Inizializza il sistema di autenticazione (crea auth.json se assente)
    try:
        from core.auth import initialize_password
        initialize_password()
    except Exception as exc:
        print(f"⚠ Inizializzazione auth: {exc}")

    # Avvia il sistema principale
    try:
        from main import main as _run_delta
        _run_delta()
    except ImportError as exc:
        print(f"\n✘ Impossibile importare i moduli DELTA: {exc}")
        print("\nAssicurarsi che le dipendenze siano installate:")
        print("  pip install -r requirements.txt\n")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n\nOperatore ha interrotto il sistema. Arrivederci!")
    except Exception as exc:
        print(f"\n✘ Errore critico: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
