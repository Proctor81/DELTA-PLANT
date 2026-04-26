#!/usr/bin/env bash
# =============================================================================
# DELTA AI Agent — Diagnostica Autostart su Raspberry Pi
# =============================================================================
# Script per verificare e risolvere problemi di avvio automatico del servizio.
# Eseguire come root per test completi.
#
# Uso:
#   sudo bash diagnose_autostart.sh
#
# =============================================================================

set -euo pipefail

# ─── Colori ───────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; BOLD='\033[1m'; RESET='\033[0m'

info()   { echo -e "${BLUE}[INFO]${RESET}  $*"; }
ok()     { echo -e "${GREEN}[OK]${RESET}    $*"; }
warn()   { echo -e "${YELLOW}[WARN]${RESET}   $*"; }
err()    { echo -e "${RED}[ERROR]${RESET}  $*" >&2; }
header() { echo -e "\n${BOLD}${BLUE}══════════════════════════════════════════${RESET}"; \
           echo -e "${BOLD}${BLUE}  $*${RESET}"; \
           echo -e "${BOLD}${BLUE}══════════════════════════════════════════${RESET}"; }

# ─── Controllo root ───────────────────────────────────────────────────────────
if [[ $EUID -ne 0 ]]; then
    warn "Script eseguito senza permessi root. Alcuni test saranno limitati."
    warn "Per test completi: sudo bash diagnose_autostart.sh"
fi

# ─── Percorso progetto ─────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DELTA_DIR="$SCRIPT_DIR"
SERVICE_NAME="delta"

# =============================================================================
# TEST 1: Stato del servizio
# =============================================================================
header "TEST 1: Stato del servizio systemd"

if systemctl list-unit-files | grep -q "^${SERVICE_NAME}"; then
    ok "Servizio '${SERVICE_NAME}' registrato in systemd."
    
    if systemctl is-enabled --quiet "${SERVICE_NAME}" 2>/dev/null; then
        ok "Servizio ABILITATO per l'avvio automatico."
    else
        err "Servizio DISABILITATO! Eseguire:"
        echo "   sudo systemctl enable ${SERVICE_NAME}"
        echo ""
    fi
    
    if systemctl is-active --quiet "${SERVICE_NAME}" 2>/dev/null; then
        ok "Servizio ATTIVO e in esecuzione."
    else
        warn "Servizio NON ATTIVO. Ultime linee del log:"
        journalctl -u "${SERVICE_NAME}" -n 20 --no-pager 2>/dev/null || echo "  (Nessun log disponibile)"
    fi
else
    err "Servizio '${SERVICE_NAME}' NON TROVATO in systemd!"
    err "Eseguire prima: sudo bash install_service.sh"
    exit 1
fi

# =============================================================================
# TEST 2: Configurazione .env
# =============================================================================
header "TEST 2: Configurazione file .env"

if [[ ! -f "${DELTA_DIR}/.env" ]]; then
    err "File .env MANCANTE!"
    if [[ -f "${DELTA_DIR}/.env.example" ]]; then
        warn "Creare da .env.example: cp ${DELTA_DIR}/.env.example ${DELTA_DIR}/.env"
    fi
    exit 1
fi

TOKEN_VALUE=$(grep -E "^DELTA_TELEGRAM_TOKEN=" "${DELTA_DIR}/.env" | cut -d= -f2 | tr -d '[:space:]' || echo "")

if [[ -z "$TOKEN_VALUE" || "$TOKEN_VALUE" == "inserisci_qui_il_token_del_bot" ]]; then
    err "Token Telegram NON CONFIGURATO in .env!"
    echo "   Modifica:  ${DELTA_DIR}/.env"
    echo "   Imposta:   DELTA_TELEGRAM_TOKEN=<il_tuo_token>"
    echo "   Riavvia:   sudo systemctl restart ${SERVICE_NAME}"
    exit 1
else
    ok "Token Telegram configurato (ultime 10 caratteri: ...${TOKEN_VALUE: -10})"
fi

# =============================================================================
# TEST 3: Modello AI e labels
# =============================================================================
header "TEST 3: Artefatti del modello AI"

MODEL_PATH="${DELTA_DIR}/models/plant_disease_model.tflite"
LABELS_PATH="${DELTA_DIR}/models/labels.txt"
VALIDATION_IMAGE="${DELTA_DIR}/models/validation_sample.jpg"

[[ -f "$MODEL_PATH" ]] && ok "Modello TFLite: $MODEL_PATH" || err "MANCANTE: $MODEL_PATH"
[[ -f "$LABELS_PATH" ]] && ok "File labels: $LABELS_PATH" || err "MANCANTE: $LABELS_PATH"
[[ -f "$VALIDATION_IMAGE" ]] && ok "Immagine validazione: $VALIDATION_IMAGE" || warn "MANCANTE: $VALIDATION_IMAGE (opzionale)"

# =============================================================================
# TEST 4: Ambiente virtuale Python
# =============================================================================
header "TEST 4: Ambiente virtuale Python"

VENV_PYTHON="${DELTA_DIR}/.venv/bin/python"
VENV_PIP="${DELTA_DIR}/.venv/bin/pip"

if [[ ! -f "$VENV_PYTHON" ]]; then
    err "Ambiente virtuale NON TROVATO: ${DELTA_DIR}/.venv"
    echo "   Creare con:  python3 -m venv '${DELTA_DIR}/.venv'"
    exit 1
fi

ok "Ambiente virtuale trovato: ${DELTA_DIR}/.venv"

# Controllo dipendenze critiche
CRITICAL_PACKAGES=("tensorflow" "python-telegram-bot" "requests" "flask")
MISSING_PACKAGES=()

for pkg in "${CRITICAL_PACKAGES[@]}"; do
    if "$VENV_PYTHON" -c "import ${pkg//-/_}" 2>/dev/null; then
        ok "Modulo installato: ${pkg}"
    else
        MISSING_PACKAGES+=("$pkg")
        err "Modulo MANCANTE: ${pkg}"
    fi
done

if [[ ${#MISSING_PACKAGES[@]} -gt 0 ]]; then
    echo ""
    echo "   Installare dipendenze mancanti:"
    echo "   ${VENV_PIP} install ${MISSING_PACKAGES[@]}"
    echo ""
fi

# =============================================================================
# TEST 5: Permessi file
# =============================================================================
header "TEST 5: Permessi di accesso ai file"

DELTA_USER="${SUDO_USER:-pi}"

if [[ $EUID -eq 0 ]]; then
    # Verificare permessi directory
    PERMS=$(stat -c "%U:%G" "${DELTA_DIR}" 2>/dev/null || echo "unknown")
    
    if [[ "$PERMS" == "${DELTA_USER}:"* ]]; then
        ok "Directory ${DELTA_DIR} appartiene a ${DELTA_USER}"
    else
        warn "Directory appartiene a: $PERMS (atteso: ${DELTA_USER})"
    fi
    
    # Verificare lettura/scrittura logs
    if [[ -d "${DELTA_DIR}/logs" ]]; then
        if touch "${DELTA_DIR}/logs/.test" 2>/dev/null && rm "${DELTA_DIR}/logs/.test" 2>/dev/null; then
            ok "Directory logs scrivibile"
        else
            err "Directory logs NON scrivibile! Eseguire:"
            echo "   sudo chown -R ${DELTA_USER}:${DELTA_USER} '${DELTA_DIR}/logs'"
        fi
    fi
fi

# =============================================================================
# TEST 6: Connettività di rete
# =============================================================================
header "TEST 6: Connettività di rete"

if ping -c 1 -W 2 8.8.8.8 &>/dev/null; then
    ok "Connessione Internet disponibile (ping 8.8.8.8)"
else
    warn "Connessione Internet NON disponibile. Il bot Telegram non funzionerà."
fi

# Verificare server Telegram
if timeout 3 bash -c "</dev/tcp/api.telegram.org/443" 2>/dev/null; then
    ok "Server Telegram (api.telegram.org:443) raggiungibile"
else
    warn "Server Telegram non raggiungibile. Verifica firewall e connessione."
fi

# =============================================================================
# TEST 7: Porta API (5000)
# =============================================================================
header "TEST 7: Porta API Flask (5000)"

if [[ $EUID -eq 0 ]]; then
    if netstat -tuln 2>/dev/null | grep -q ":5000 "; then
        ok "Porta 5000 in ascolto (API attiva)"
    else
        info "Porta 5000 non occupata (normale se servizio non è attivo)"
    fi
fi

# =============================================================================
# TEST 8: PID file stale
# =============================================================================
header "TEST 8: Verifica PID file"

PID_FILE="${DELTA_DIR}/delta.pid"
if [[ -f "$PID_FILE" ]]; then
    PID=$(cat "$PID_FILE")
    if ps -p "$PID" > /dev/null 2>&1; then
        warn "PID file contiene processo attivo (PID $PID). OK."
    else
        warn "PID file contiene processo TERMINATO (PID $PID)"
        warn "Ripulire con: rm '${PID_FILE}'"
    fi
else
    info "Nessun PID file (normale se servizio non è attivo)"
fi

# =============================================================================
# TEST 9: Ultima linea del log
# =============================================================================
header "TEST 9: Ultime linee di log"

if journalctl -u "${SERVICE_NAME}" -n 1 --no-pager 2>/dev/null | grep -q "."; then
    echo ""
    journalctl -u "${SERVICE_NAME}" -n 10 --no-pager
else
    warn "Nessun log disponibile per il servizio ${SERVICE_NAME}."
fi

# =============================================================================
# RIEPILOGO E AZIONI CONSIGLIATE
# =============================================================================
header "Riepilogo"

echo ""
echo -e "${BOLD}Se il servizio NON si avvia, eseguire questi comandi in ordine:${RESET}"
echo ""
echo "1. ${BOLD}Reinstallare il servizio:${RESET}"
echo "   sudo bash install_service.sh"
echo ""
echo "2. ${BOLD}Verificare i log:${RESET}"
echo "   sudo journalctl -u delta -f"
echo ""
echo "3. ${BOLD}Controllare manualmente (debug):${RESET}"
echo "   cd '${DELTA_DIR}'"
echo "   ./.venv/bin/python main.py --enable-api --enable-telegram --daemon"
echo ""
echo "4. ${BOLD}Se ancora non funziona, aprire issue con output di:${RESET}"
echo "   sudo bash diagnose_autostart.sh 2>&1 | head -100"
echo ""
