#!/usr/bin/env bash
# =============================================================================
# DELTA Plant — Quick Recovery / Reset del servizio
# =============================================================================
# Script rapido per risolvere problemi di autostart senza riconfigurare tutto.
# Utile quando il servizio è già installato ma non si avvia correttamente.
#
# Uso:
#   sudo bash fix_autostart.sh [--hard-reset]
#
# Options:
#   --hard-reset : Rimuove il servizio, ripulisce e reinstalla da zero
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
    err "Eseguire come root: sudo bash fix_autostart.sh"
    exit 1
fi

# ─── Percorsi ─────────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DELTA_DIR="$SCRIPT_DIR"
DELTA_USER="${SUDO_USER:-pi}"
SERVICE_NAME="delta"
PID_FILE="${DELTA_DIR}/delta.pid"

# ─── Modalità hard-reset ──────────────────────────────────────────────────────
HARD_RESET=false
if [[ "${1:-}" == "--hard-reset" ]]; then
    HARD_RESET=true
fi

# =============================================================================
# STEP 1: Fermare il servizio attuale
# =============================================================================
header "Arresto servizio attuale"

if systemctl is-active --quiet "${SERVICE_NAME}" 2>/dev/null; then
    info "Arresto ${SERVICE_NAME}..."
    systemctl stop "${SERVICE_NAME}" || true
    sleep 2
    ok "Servizio arrestato."
else
    info "Servizio ${SERVICE_NAME} non è attivo."
fi

# =============================================================================
# STEP 2: Pulizia PID stale
# =============================================================================
header "Pulizia file temporanei"

if [[ -f "$PID_FILE" ]]; then
    rm -f "$PID_FILE"
    ok "PID file rimosso."
fi

# Uccidi eventuali processi Python DELTA rimasti
pkill -f "main.py.*--enable-telegram" 2>/dev/null || true
pkill -f "main.py.*--enable-api" 2>/dev/null || true

# =============================================================================
# STEP 3: Hard reset se richiesto
# =============================================================================
if [[ "$HARD_RESET" == true ]]; then
    header "HARD RESET: Rimozione servizio"
    
    systemctl disable "${SERVICE_NAME}" 2>/dev/null || true
    rm -f "/etc/systemd/system/${SERVICE_NAME}.service"
    systemctl daemon-reload
    
    ok "Servizio rimosso da systemd."
fi

# =============================================================================
# STEP 4: Reinstallazione servizio
# =============================================================================
header "Reinstallazione servizio"

if [[ ! -f "${DELTA_DIR}/install_service.sh" ]]; then
    err "install_service.sh non trovato!"
    exit 1
fi

info "Eseguendo install_service.sh..."
bash "${DELTA_DIR}/install_service.sh"

# =============================================================================
# STEP 5: Verifica finale
# =============================================================================
header "Verifica finale"

sleep 3

if systemctl is-active --quiet "${SERVICE_NAME}"; then
    ok "DELTA è ATTIVO e in esecuzione! ✓"
    echo ""
    echo "Per monitorare il bot Telegram in tempo reale:"
    echo "  sudo journalctl -u delta -f"
    echo ""
else
    warn "Il servizio non risulta attivo. Controllare i log:"
    echo ""
    journalctl -u "${SERVICE_NAME}" -n 20 --no-pager
    echo ""
    err "Eseguire per diagnosticare:"
    echo "  sudo bash diagnose_autostart.sh"
fi

ok "Recovery completato!"
