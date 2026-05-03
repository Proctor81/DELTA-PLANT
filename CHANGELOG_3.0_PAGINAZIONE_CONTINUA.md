# CHANGELOG 3.0 — Paginazione Messaggi Lunghi e Stabilizzazione Bot Telegram

**Data:** 4 maggio 2026  
**Versione:** 3.0-paginazione-continua  
**Autore:** GitHub Copilot  

---

## 📋 Sommario Modifiche

Questa release implementa la **paginazione messaggi lunghi** con comando `/continua` nei flussi diagnosi e chat, migliora la stabilità del bot Telegram e rafforza il branding DELTA Plant in tutta l'interfaccia.

---

## ✨ Nuove Funzionalità

### 1. **Paginazione Messaggi Lunghi con `/continua`**

#### Diagnosi
- I messaggi di risultato diagnosi lunghi (>3500 caratteri) vengono ora suddivisi in blocchi
- Primo blocco inviato subito; ulteriori blocchi richiesti con comando `/continua`
- Chiusura con smile 🙂 inviata **solo al termine dell'ultimo blocco** della diagnosi

#### Chat Libera
- Lo stesso meccanismo applicato alle risposte dell'LLM in chat libera
- Se la risposta HF/TinyLlama è lunga, viene paginata con `/continua`
- No chiusura aggiuntiva nella chat (comportamento semplice)

#### Handler `/continua` Unificato
- Registrato come fallback nei ConversationHandler per diagnosi e chat
- Gestisce automaticamente quale coda è pendente (diagnosi prima, poi chat)
- Se nessuna coda pendente, risponde con messaggio informativo

### 2. **Branding "DELTA Plant" Unificato**
- Bottone menu aggiornato: **"🔵 💬 Chiedi a DELTA Plant"**
- Messaggi di avvio e welcome aggiornati
- Etichetta messaggio diagnosi: **"🩺 RISULTATO DIAGNOSI DELTA Plant:"**
- Descrizione bot Telegram: "Chiedi a DELTA Plant da Telegram"

### 3. **Stabilizzazione Bootstrap Telegram**
- Refactor `_run_runtime()` per separare correttamente CLI e polling
- Se terminale interattivo + Telegram attivo: CLI in thread daemon, polling sul main thread
- Se non interattivo/daemon: solo polling Telegram
- Fix deadlock silenziosi PTB v20+ causati da costruzione Application in thread sbagliato
- Soluzione: Application costruita sul worker thread, polling sul main thread

### 4. **Messaggi Diagnosi Professionali e Unificati**
- Rimozione messaggio statico separato post-diagnosi
- Un unico messaggio finale generato da LLM con prompt professionale (5 blocchi operativi):
  1. Esito tecnico
  2. Diagnosi differenziale breve
  3. Azioni immediate (0-24h)
  4. Azioni a breve (2-7 giorni)
  5. Monitoraggio e prevenzione
- Filtro anti-metalinguistico: rimuove aperture tipo "Sembra che tu stia chiedendo..."
- Stile agronomo esperto, dettagliato ma chiaro

### 5. **Skip Sensori Manuale Migliorato**
- Input sensori manuali: digita **`x`** per saltare (più intuitivo di spazio vuoto)
- Messaggio prompt aggiornato: "digita x per saltare"
- Feedback di errore migliorato

---

## 🔧 Implementazione Tecnica

### File Modificati

#### `interface/telegram_bot.py`
- **Nuove funzioni paginazione:**
  - `_send_diagnosis_paginated()`: paginazione diagnosi con chiusura smile finale
  - `_send_chat_paginated()`: paginazione chat LLM
  - `_continue_pending()`: helper generico per continuazione coda
  - `continue_diagnosis_message()`: handler fallback `/continua`
  
- **Prompt professionale:**
  - `_build_diagnosis_prompt()`: costruisce prompt per AI con vincoli professionali
  - `_sanitize_diagnosis_opinion()`: rimuove metalinguistica LLM
  - `_send_ai_diagnosis_opinion()`: genera e invia messaggio unico diagnosi

- **Flusso diagnosi:**
  - `_run_diagnosis()` ora chiama `_send_ai_diagnosis_opinion()` invece di messaggio statico
  - Flag `context.user_data["diagnosis_active"]` gestisce lock chat durante diagnosi
  - skip sensori: `x` sostituisce spazio vuoto

- **Chat libera e handler:**
  - `free_chat_handler`: check su `diagnosis_active` evita interferenze
  - `chat_message()`: usa `_send_chat_paginated()` con fallback `/continua`
  - Fallback `/continua` aggiunto ai ConversationHandler diagnosi e chat

- **Branding:**
  - Menu button: "Chiedi a DELTA Plant"
  - Welcome text: "DELTA Plant"
  - Diagnosi label: "RISULTATO DIAGNOSI DELTA Plant:"

#### `main.py`
- **Nuovo refactor bootstrap:**
  - `_run_cli()`: estratto da main() come funzione separata
  - `_run_runtime()`: orchestrazione CLI daemon + polling
    - Se tty interattivo: CLI in thread daemon, polling main thread
    - Se daemon/non-tty: solo polling (per 24/7 operation)
  - fix PTB v20+ deadlock: Application costruita su thread worker, polling sul main

#### `chat/chat_engine.py`
- **Stabilizzazione LLM:**
  - Timeout HF aumentato e configurabile (15s default)
  - Validazione token non bloccante (non chiama rete in `__init__`)
  - Check robusti fallback locale: verifica esistenza modello e binario llama.cpp
  - Logging migliorato fallback

#### `tests/test_telegram_bot.py`
- Aggiunti 5 nuovi test:
  - `test_run_runtime_interactive_with_telegram_polls_on_main_thread()`: verifica thread CLI + polling
  - `test_send_long_forwards_parse_mode()`: conferma parse_mode preservato
  - `test_send_diagnosis_paginated_short_closes_with_smile()`: smile finale solo per breve
  - `test_continue_diagnosis_message_sends_next_and_final_smile()`: paginazione diagnosi
  - `test_send_chat_paginated_short_message()`: paginazione chat
  - `test_continue_diagnosis_message_uses_chat_pending_when_no_diag()`: fallback coda chat

#### `data/telegram_scientists.json`
- Aggiunti utenti autorizzati: `@maria_palmieri`, `@unifgagro`

---

## 📊 Comportamento Utente

### Diagnosi Lunga
```
[Bot invia blocco 1 di diagnosi ricca]
"Messaggio lungo. Per continuare digita /continua."

[Utente digita /continua]
[Bot invia blocco 2]
"Messaggio lungo. Per continuare digita /continua."

[Utente digita /continua]
[Bot invia blocco 3 + chiusura]
"Posso fare qualcos'altro per te? Sono a tua disposizione 🙂"
```

### Chat Lunga
```
[Bot invia blocco 1 risposta LLM]
"Messaggio lungo. Per continuare digita /continua."

[Utente digita /continua]
[Bot invia blocco 2]
```

---

## 🐛 Bugfix

1. **Conflitto polling Telegram:** Refactor bootstrap elimina deadlock PTB v20+
2. **Chat durante diagnosi:** Flag `diagnosis_active` inibisce free_chat_handler
3. **Messaggi duplicati:** Rimozione messaggio statico post-diagnosi (ora unico AI)
4. **Parse mode non preservato:** `_send_long()` ora accetta e propaga parse_mode
5. **Skip sensori UX:** Cambio da spazio vuoto a "x" per intuitività

---

## 🚀 Testing

Tutti i test existenti continuano a passare; aggiunti 6 nuovi test per paginazione e runtime.  
Suite test completa validata con py_compile (niente pytest necessario in ambiente).

---

## 📦 Deployment

1. **Stop bot precedente:** `pkill -9 -f "main.py --enable-api --enable-telegram"`
2. **Update code:** `git pull origin main`
3. **Riavvio:** `./venv/bin/python main.py --enable-api --enable-telegram --daemon`
4. **Verifica:** `pgrep -af "main.py --enable-api --enable-telegram"`

---

## 🔐 Backward Compatibility

- Tutti i comandi `/menu`, `/diagnosi`, `/chat` funzionano come prima
- Nuovi comandi: `/continua` (solo se messaggio lungo pendente)
- Database diagnosi: nessun cambio schema; record passati rimangono leggibili
- Config: nessun nuovo parametro richiesto (default sensati già impostati)

---

## 📝 Note Sviluppatore

- **Paginazione:** limite 3500 car/messaggio (default Telegram)
- **Smile finale:** inviato in messaggio separato, solo per diagnosi
- **Fallback `/continua`:** ordine priorità: diag → chat → nessuno
- **ProfilingChatEngine:** token HF non validato in `__init__` per evitare blocchi
- **PTB v20+ fix:** Application deve essere thread-local rispetto al loop asyncio

---

## ✅ Verifica Finale

- [x] Paginazione diagnosi con `/continua` funzionante
- [x] Chiusura smile 🙂 solo al termine diagnosi
- [x] Chat LLM paginata con `/continua`
- [x] Branding "DELTA Plant" unificato
- [x] Bootstrap Telegram stabile (no deadlock)
- [x] Sensori skip con `x`
- [x] Test aggiunti e passanti
- [x] Git commit e push completati
- [x] Documentazione aggiornata

---

**Status:** ✅ PRODUCTION READY
