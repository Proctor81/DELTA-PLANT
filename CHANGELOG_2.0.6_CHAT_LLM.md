# DELTA 2.0.6 — Chat Intelligente "Chiedi a DELTA" + HF LLM Integration

**Data:** 29 aprile 2026  
**Branch:** main  
**Tipo:** Feature Release

---

## Novità principali

### 🔵 Pulsante "Chiedi a DELTA" nel bot Telegram
- Nuovo pulsante `🔵 💬 Chiedi a DELTA` in **prima posizione** nel menu principale di `@DELTAPLANO_bot`
- Pulsante a riga intera per massima visibilità (stile "blu" tramite emoji + posizionamento)
- Avvia una **sessione di chat dedicata** con il modello LLM cloud

### 🤖 ChatEngine con HuggingFace Inference API
- Modello primario: **`meta-llama/Llama-3.1-8B-Instruct`** (testato, risposte in italiano)
- Fallback automatico a TinyLlama locale se HF non disponibile
- Validazione token all'avvio con messaggio chiaro in caso di errore 401
- Memoria conversazionale per sessione (per utente Telegram)

### 💬 ConversationHandler dedicato (`STATE_CHAT_WAITING`)
- Stato `STATE_CHAT_WAITING = 21` aggiunto alla macchina a stati esistente
- Entry point: `/chat` (comando) e `CMD_CHAT` (callback menu)
- Messaggi testo → risposta LLM con `typing action` in corso
- Pulsanti inline integrati: **"🔴 Termina chat"** e **"🗑 Reset conversazione"**
- Comandi di uscita: `/chiudi`, `/annulla`, `/menu`
- Timeout chat: 600 secondi (configurabile via `chat_timeout_sec` in config)

### 🔧 Bot e Router aggiornati
- **`bot/deltaplano_bot.py`**: rimosso stub TinyLlama, usa `ChatEngine` con HF LLM reale
  - `handle_message()`: chat LLM o vision a seconda dell'input
  - `handle_command("/status")`: mostra stato HF token e MobileNet
  - `handle_command("/reset")`: azzera memoria conversazionale
- **`router/router.py`**: `Router("")` crea `ChatEngine("")` senza model_path locale obbligatorio

### 🚀 Fix autostart Raspberry Pi 5
- **`delta.service`**: `ExecStart` aggiornato a `.venv/bin/python3.12` (symlink robusto)
- **`delta.service`**: aggiunta direttiva `EnvironmentFile=-DELTA_DIR/.env` per caricare token HF e Telegram via systemd
- **`main.py`**: auto-rilancio venv usa `os.path.realpath()` per confronto path (evita loop con `python3.12` vs `python`)
- **`install_service.sh`**: rileva automaticamente `python3.12` nel venv, con fallback a `python`

### 📦 Dipendenze
- `huggingface_hub>=0.27.0` installato nel `.venv` tramite `python3.12 -m pip`
- Aggiunto in `requirements.txt` (era già presente, confermato)

---

## File modificati

| File | Modifica |
|------|----------|
| `interface/telegram_bot.py` | +CMD_CHAT, +STATE_CHAT_WAITING, +chat handlers, +ConversationHandler, menu aggiornato |
| `bot/deltaplano_bot.py` | Riscritto: ChatEngine HF reale, rimosso Router/stub |
| `router/router.py` | ChatEngine("") senza path locale obbligatorio |
| `main.py` | Auto-rilancio venv con realpath() anti-loop |
| `delta.service` | python3.12, EnvironmentFile .env |
| `install_service.sh` | Rilevamento python3.12 automatico |

---

## Test eseguiti

- ✅ Import chain completa: `ChatEngine`, `DELTAPLANOBot`, `Router`, `HuggingFaceLLM`
- ✅ Parse AST: tutti i file Python senza errori di sintassi
- ✅ `.venv/bin/python3.12` carica `huggingface_hub 1.12.2`, `telegram`, `requests`
- ✅ Token HF valido (utente Proctor81, configurato in `.env`)
- ✅ Modello LLM `meta-llama/Llama-3.1-8B-Instruct` risponde in italiano

---

## Come usare la chat intelligente

1. Avvia `@DELTAPLANO_bot` su Telegram
2. Usa `/start` o `/menu`
3. Clicca **`🔵 💬 Chiedi a DELTA`** (prima riga del menu)
4. Scrivi qualsiasi domanda: malattie piante, agronomia, interpretazione diagnosi
5. DELTA risponde usando Llama-3.1-8B via HuggingFace (o TinyLlama offline)
6. Clicca **"🔴 Termina chat"** o invia `/chiudi` per tornare al menu

---

## Troubleshooting

**Token HF non valido:**
```bash
python tools/hf_token_check.py --interactive
```

**Bot non si avvia:**
```bash
sudo journalctl -u delta -f
sudo bash diagnose_autostart.sh
```

**Reinstalla dipendenze venv:**
```bash
/usr/local/bin/python3.12 -m pip install --prefix=/path/to/DELTA_2.0/.venv "huggingface_hub>=0.27.0"
```
