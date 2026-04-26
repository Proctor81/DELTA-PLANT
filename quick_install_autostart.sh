#!/usr/bin/env bash
# =============================================================================
# DELTA Autostart Fix — Quick Install
# =============================================================================
# Script rapido per installare/aggiornare il servizio DELTA su Raspberry Pi.
# Eseguire DOPO aver fatto git pull della versione 2.0.5+
#
# Uso:
#   sudo bash quick_install_autostart.sh
#
# =============================================================================

set -euo pipefail

# Colori
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'
BOLD='\033[1m'; RESET='\033[0m'

info()   { echo -e "${BLUE}[i]${RESET}  $*"; }
ok()     { echo -e "${GREEN}[✓]${RESET}  $*"; }
err()    { echo -e "${RED}[✗]${RESET}  $*" >&2; }

if [[ $EUID -ne 0 ]]; then
    err "Eseguire come root: sudo bash quick_install_autostart.sh"
    exit 1
fi

DELTA_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo ""
echo -e "${BOLD}${BLUE}═══════════════════════════════════════${RESET}"
echo -e "${BOLD}${BLUE} DELTA 2.0.5+ Autostart Setup${RESET}"
echo -e "${BOLD}${BLUE}═══════════════════════════════════════${RESET}"
echo ""
info "Directory: ${DELTA_DIR}"
echo ""

# Passo 1: Installa il servizio
info "Installando servizio systemd..."
bash "${DELTA_DIR}/install_service.sh"

# Passo 2: Diagnostica rapida
echo ""
echo -e "${BOLD}${BLUE}═══════════════════════════════════════${RESET}"
echo -e "Eseguendo diagnostica..."
echo -e "${BOLD}${BLUE}═══════════════════════════════════════${RESET}"
echo ""

if bash "${DELTA_DIR}/diagnose_autostart.sh" 2>&1 | tail -20; then
    ok "Setup completato! ✨"
    echo ""
    echo -e "${BOLD}Prossimi passi:${RESET}"
    echo "1. Attendi il prossimo boot (o riavvia ora: sudo reboot)"
    echo "2. Accedi a @DELTAPLANO_bot su Telegram"
    echo "3. Se problemi: sudo bash diagnose_autostart.sh"
    echo ""
else
    err "Errori durante la diagnostica. Controlla sopra."
    exit 1
fi
