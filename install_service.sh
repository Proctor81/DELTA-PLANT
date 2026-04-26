#!/usr/bin/env bash
# =============================================================================
# DELTA AI Agent — Installazione servizio systemd (autostart al boot)
# =============================================================================
# Installa e abilita il servizio systemd che avvia automaticamente DELTA
# (incluso il bot Telegram @DELTAPLANO_bot) ad ogni accensione del Raspberry Pi.
#
# Uso:
#   sudo bash install_service.sh
#
# Per disinstallare il servizio:
#   sudo bash install_service.sh --remove
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
    err "Eseguire come root:  sudo bash install_service.sh"
    exit 1
fi

# ─── Percorsi rilevati automaticamente ───────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DELTA_DIR="$SCRIPT_DIR"
DELTA_USER="${SUDO_USER:-pi}"
VENV_PYTHON="${DELTA_DIR}/.venv/bin/python"
SERVICE_NAME="delta"
SERVICE_DST="/etc/systemd/system/${SERVICE_NAME}.service"
SERVICE_SRC="${DELTA_DIR}/delta.service"

# ─── Modalità rimozione ───────────────────────────────────────────────────────
if [[ "${1:-}" == "--remove" ]]; then
    header "Rimozione servizio DELTA"
    systemctl stop  "${SERVICE_NAME}" 2>/dev/null || true
    systemctl disable "${SERVICE_NAME}" 2>/dev/null || true
    rm -f "$SERVICE_DST"
    systemctl daemon-reload
    ok "Servizio '${SERVICE_NAME}' rimosso. DELTA non verrà più avviato al boot."
    exit 0
fi

# ─── Banner ───────────────────────────────────────────────────────────────────
header "DELTA AI Agent — Installazione autostart"
info "Directory progetto:  ${DELTA_DIR}"
info "Utente di esecuzione: ${DELTA_USER}"
info "Python venv:         ${VENV_PYTHON}"

# ─── Verifica prerequisiti ────────────────────────────────────────────────────
if [[ ! -f "${DELTA_DIR}/main.py" ]]; then
    err "main.py non trovato in ${DELTA_DIR}. Eseguire lo script dalla directory del progetto."
    exit 1
fi

if [[ ! -f "$VENV_PYTHON" ]]; then
    err "Ambiente virtuale non trovato: ${VENV_PYTHON}"
    err "Creare il venv prima:  python3 -m venv '${DELTA_DIR}/.venv' && '${DELTA_DIR}/.venv/bin/pip' install -r '${DELTA_DIR}/requirements.txt'"
    exit 1
fi

# ─── Verifica token Telegram ──────────────────────────────────────────────────
ENV_FILE="${DELTA_DIR}/.env"
if [[ ! -f "$ENV_FILE" ]]; then
    if [[ -f "${DELTA_DIR}/.env.example" ]]; then
        cp "${DELTA_DIR}/.env.example" "$ENV_FILE"
        chown "${DELTA_USER}:${DELTA_USER}" "$ENV_FILE"
        chmod 600 "$ENV_FILE"
        warn "File .env creato da .env.example."
    fi
fi

TOKEN_VALUE=""
if [[ -f "$ENV_FILE" ]]; then
    TOKEN_VALUE=$(grep -E "^DELTA_TELEGRAM_TOKEN=" "$ENV_FILE" | cut -d= -f2 | tr -d '[:space:]')
fi
# Controlla anche la variabile d'ambiente di sistema
[[ -z "$TOKEN_VALUE" ]] && TOKEN_VALUE="${DELTA_TELEGRAM_TOKEN:-}"

if [[ -z "$TOKEN_VALUE" || "$TOKEN_VALUE" == "inserisci_qui_il_token_del_bot" ]]; then
    echo ""
    echo -e "${YELLOW}${BOLD}⚠  Token Telegram non configurato!${RESET}"
    echo -e "   Il bot @DELTAPLANO_bot non sarà operativo finché non imposti il token."
    echo ""
    echo -e "   1. Ottieni il token da ${BOLD}@BotFather${RESET} su Telegram"
    echo -e "   2. Modifica il file:  ${BOLD}${ENV_FILE}${RESET}"
    echo -e "      Imposta:  DELTA_TELEGRAM_TOKEN=<il_tuo_token>"
    echo -e "   3. Riavvia il servizio:  sudo systemctl restart delta"
    echo ""
else
    ok "Token Telegram presente nel file .env."
fi

# ─── systemd-networkd-wait-online (necessario per After=network-online.target) ─
if ! systemctl list-unit-files | grep -q "NetworkManager-wait-online\|systemd-networkd-wait-online"; then
    warn "Nessun servizio 'wait-online' rilevato. Il bot potrebbe avviarsi prima che la rete sia pronta."
    warn "Se accade, aumentare RestartSec nel file delta.service."
else
    # Abilita il wait-online se non già attivo
    if systemctl list-unit-files | grep -q "NetworkManager-wait-online"; then
        systemctl enable NetworkManager-wait-online.service 2>/dev/null || true
    else
        systemctl enable systemd-networkd-wait-online.service 2>/dev/null || true
    fi
    ok "Servizio wait-online abilitato (garantisce rete disponibile prima di DELTA)."
fi

# ─── Generazione del file .service con i percorsi reali ──────────────────────
info "Generazione /etc/systemd/system/${SERVICE_NAME}.service ..."

sed \
    -e "s|DELTA_DIR|${DELTA_DIR}|g" \
    -e "s|DELTA_USER|${DELTA_USER}|g" \
    "$SERVICE_SRC" > "$SERVICE_DST"

chmod 644 "$SERVICE_DST"
ok "File servizio scritto in ${SERVICE_DST}."

# ─── Reload + enable + start ──────────────────────────────────────────────────
systemctl daemon-reload
systemctl enable "${SERVICE_NAME}.service"
ok "Servizio abilitato: si avvierà automaticamente ad ogni boot."

# Ferma eventuale istanza precedente prima di riavviare
systemctl stop "${SERVICE_NAME}" 2>/dev/null || true
# Rimuove PID stale se presente
rm -f "${DELTA_DIR}/delta.pid"

systemctl start "${SERVICE_NAME}.service"
sleep 3

# ─── Stato finale ─────────────────────────────────────────────────────────────
header "Verifica stato servizio"
if systemctl is-active --quiet "${SERVICE_NAME}"; then
    ok "DELTA è ATTIVO e in esecuzione."
else
    warn "Il servizio è stato avviato ma non risulta attivo. Controlla i log:"
    warn "  journalctl -u delta -n 50 --no-pager"
fi

# ─── Info di supporto ──────────────────────────────────────────────────────────
header "Comandi utili per troubleshooting"
echo ""
echo -e "${BOLD}Monitoraggio:${RESET}"
echo "  sudo journalctl -u delta -f              # Log in tempo reale"
echo ""
echo -e "${BOLD}Diagnostica e repair:${RESET}"
echo "  sudo bash ${DELTA_DIR}/diagnose_autostart.sh    # Test completo (9 verifiche)"
echo "  sudo bash ${DELTA_DIR}/fix_autostart.sh         # Recovery rapido"
echo "  sudo bash ${DELTA_DIR}/fix_autostart.sh --hard-reset  # Reset totale"
echo ""
echo -e "${BOLD}Documentazione:${RESET}"
echo "  less ${DELTA_DIR}/AUTOSTART_TROUBLESHOOTING.md  # Guida troubleshooting"
echo "  less ${DELTA_DIR}/CHANGELOG_2.0.5_AUTOSTART.md  # Dettagli dei fix"
echo ""

ok "Installazione completata!"


echo ""
echo -e "${BOLD}Comandi utili:${RESET}"
echo "  sudo systemctl status delta        # Stato servizio"
echo "  sudo systemctl restart delta       # Riavvio manuale"
echo "  sudo systemctl stop delta          # Arresto"
echo "  journalctl -u delta -f             # Log in tempo reale"
echo "  sudo bash install_service.sh --remove  # Rimuovi autostart"
echo ""
echo -e "${YELLOW}Il bot Telegram @DELTAPLANO_bot sarà attivo a ogni accensione del Raspberry Pi.${RESET}"
echo ""
