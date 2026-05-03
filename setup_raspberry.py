"""
DELTA - setup_raspberry.py
===========================
Script Python interattivo per la configurazione post-installazione
di DELTA Plant su Raspberry Pi 5 con Raspberry Pi OS.
Richiede Python 3.12+
    python setup_raspberry.py

Funzionalità:
  - Verifica dipendenze e hardware
  - Configura parametri locali (camera index, I2C addr, soglie)
  - Testa camera e sensori
  - Verifica cartella input_images
  - Genera il manuale PDF aggiornato
"""

import sys
import os
import subprocess
import importlib
from pathlib import Path

# ── Percorso root progetto ────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# ── Colori ────────────────────────────────────────────────────────────────────
RED    = "\033[0;31m"
GREEN  = "\033[0;32m"
YELLOW = "\033[1;33m"
BLUE   = "\033[0;34m"
BOLD   = "\033[1m"
RESET  = "\033[0m"

def info(msg):    print(f"{BLUE}[INFO]{RESET}  {msg}")
def ok(msg):      print(f"{GREEN}[OK]{RESET}    {msg}")
def warn(msg):    print(f"{YELLOW}[WARN]{RESET}   {msg}")
def error(msg):   print(f"{RED}[ERROR]{RESET}  {msg}", file=sys.stderr)
def header(msg):
    print(f"\n{BOLD}{BLUE}{'═'*48}{RESET}")
    print(f"{BOLD}{BLUE}  {msg}{RESET}")
    print(f"{BOLD}{BLUE}{'═'*48}{RESET}")


# ─────────────────────────────────────────────────────────────
# VERIFICA PYTHON
# ─────────────────────────────────────────────────────────────

def check_python():
    header("1. Verifica versione Python")
    major, minor = sys.version_info[:2]
    if major < 3 or minor < 12:
        error(f"Python {major}.{minor} rilevato. Richiesto Python 3.12+")
        sys.exit(1)
    ok(f"Python {major}.{minor} — compatibile.")


# ─────────────────────────────────────────────────────────────
# VERIFICA DIPENDENZE
# ─────────────────────────────────────────────────────────────

def check_dependencies():
    header("2. Verifica dipendenze Python")
    required = {
        "numpy": "numpy",
        "cv2": "opencv-python-headless",
        "pandas": "pandas",
        "openpyxl": "openpyxl",
        "sklearn": "scikit-learn",
        "flask": "flask",
        "fpdf": "fpdf2",
    }
    optional = {
        "picamera2": "picamera2",
        "ai_edge_litert": "ai-edge-litert",
        "RPi": "RPi.GPIO",
        "smbus2": "smbus2",
        "adafruit_bme680": "adafruit-circuitpython-bme680",
    }

    missing_required = []
    for mod, pkg in required.items():
        try:
            importlib.import_module(mod)
            ok(f"  {pkg}")
        except ImportError:
            error(f"  MANCANTE: {pkg}  →  pip install {pkg}")
            missing_required.append(pkg)

    print(f"\n  {BOLD}Dipendenze opzionali (hardware Raspberry Pi):{RESET}")
    for mod, pkg in optional.items():
        try:
            importlib.import_module(mod)
            ok(f"  {pkg}")
        except ImportError:
            warn(f"  non installato: {pkg}")
        except Exception:
            warn(f"  errore import: {pkg} (verifica compatibilita' libreria)")

    if missing_required:
        error(f"\n{len(missing_required)} dipendenza(e) obbligatoria(e) mancante(i).")
        print(f"  Eseguire: pip install {' '.join(missing_required)}")
        return False
    return True


# ─────────────────────────────────────────────────────────────
# VERIFICA CAMERA
# ─────────────────────────────────────────────────────────────

def check_camera():
    header("3. Verifica camera")
    # Test picamera2
    try:
        from picamera2 import Picamera2  # type: ignore
        cam = Picamera2()
        cam.close()
        ok("picamera2: camera Raspberry Pi rilevata.")
        return "picamera2"
    except Exception as exc:
        warn(f"picamera2 non disponibile: {exc}")

    # Test OpenCV
    try:
        import cv2  # type: ignore
        cap = cv2.VideoCapture(0)
        if cap.isOpened():
            cap.release()
            ok("OpenCV VideoCapture(0): camera USB/webcam rilevata.")
            return "opencv"
        else:
            cap.release()
    except ImportError:
        pass

    warn("Nessuna camera rilevata.")
    info("Modalità cartella immagini input sarà utilizzata automaticamente.")
    _show_input_folder_info()
    return None


def _show_input_folder_info():
    """Mostra informazioni sulla cartella input_images."""
    input_dir = ROOT / "input_images"
    input_dir.mkdir(exist_ok=True)
    print(f"\n  {BOLD}Cartella immagini input:{RESET}")
    print(f"    Percorso: {input_dir}")
    print(f"    Formati: JPG, PNG, BMP, TIFF, WEBP")
    images = list(input_dir.glob("*"))
    images = [f for f in images if f.suffix.lower() in
              {".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".webp"}]
    if images:
        ok(f"    {len(images)} immagine(i) già presenti.")
    else:
        warn(f"    Cartella vuota — copiare immagini per poter eseguire diagnosi.")


# ─────────────────────────────────────────────────────────────
# VERIFICA SENSORI I2C
# ─────────────────────────────────────────────────────────────

def check_sensors():
    header("4. Verifica sensori I2C")
    try:
        result = subprocess.run(["i2cdetect", "-y", "1"],
                                capture_output=True, text=True, timeout=5)
        print(result.stdout)
        ok("i2cdetect completato.")
    except FileNotFoundError:
        warn("i2cdetect non trovato — installare i2c-tools.")
    except Exception as exc:
        warn(f"Errore i2cdetect: {exc}")


# ─────────────────────────────────────────────────────────────
# VERIFICA STRUTTURA DIRECTORY
# ─────────────────────────────────────────────────────────────

def check_directories():
    header("5. Verifica struttura directory")
    dirs = {
        "input_images":            "Immagini manuali (no-camera)",
        "datasets/captures":       "Frame acquisiti dalla camera",
        "datasets/training":       "Dataset fine-tuning",
        "models":                  "Modelli AI TFLite",
        "exports":                 "Export Excel",
        "logs":                    "Log di sistema",
        "Manuale":                 "Manuale utente PDF",
    }
    all_ok = True
    for rel, desc in dirs.items():
        d = ROOT / rel
        d.mkdir(parents=True, exist_ok=True)
        ok(f"  {rel:<30s} ← {desc}")

    # Verifica cartella input_images
    input_dir = ROOT / "input_images"
    imgs = [f for f in input_dir.iterdir()
            if f.is_file() and f.suffix.lower() in
            {".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".webp"}] \
        if input_dir.exists() else []
    if not imgs:
        warn(f"\n  La cartella input_images è vuota.")
        warn(f"  Copiare immagini in:  {input_dir}")
    else:
        ok(f"\n  {len(imgs)} immagine(i) trovata(e) in input_images/")


# ─────────────────────────────────────────────────────────────
# GENERAZIONE MANUALE PDF
# ─────────────────────────────────────────────────────────────

def generate_manual():
    header("6. Generazione Manuale Utente PDF")
    manuale_script = ROOT / "Manuale" / "genera_manuale.py"
    if not manuale_script.exists():
        warn("Script genera_manuale.py non trovato.")
        return

    try:
        result = subprocess.run(
            [sys.executable, str(manuale_script)],
            capture_output=True, text=True, cwd=str(ROOT),
        )
        if result.returncode == 0:
            pdf = ROOT / "Manuale" / "DELTA_Manuale_Utente.pdf"
            ok(f"Manuale generato: {pdf}")
        else:
            warn(f"Errore generazione manuale:\n{result.stderr}")
    except Exception as exc:
        warn(f"Impossibile generare manuale: {exc}")


# ─────────────────────────────────────────────────────────────
# RIEPILOGO
# ─────────────────────────────────────────────────────────────

def print_summary(camera_backend):
    header("Configurazione completata")
    print(f"\n  {GREEN}{BOLD}DELTA Plant - AI & Robotics Orchestrator per la Salute delle Piante è pronto per l'uso!{RESET}")
    print(f"\n  Directory:  {ROOT}")
    print(f"  Camera:     {camera_backend or 'non disponibile — modalità cartella attiva'}")
    print(f"  Input img:  {ROOT / 'input_images'}")
    print(f"\n  {BOLD}Avvio:{RESET}")
    print(f"    python main.py")
    print(f"    — oppure —")
    print(f"    delta   (se installato con install_raspberry.sh)")
    print()


# ─────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────

def main():
    print(f"\n{BOLD}{BLUE}")
    print("╔══════════════════════════════════════════════════════╗")
    print("║     DELTA Plant — Setup Raspberry Pi 5               ║")
    print("╚══════════════════════════════════════════════════════╝")
    print(RESET)

    check_python()
    deps_ok = check_dependencies()
    camera_backend = check_camera()
    check_sensors()
    check_directories()
    generate_manual()
    print_summary(camera_backend)

    if not deps_ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
