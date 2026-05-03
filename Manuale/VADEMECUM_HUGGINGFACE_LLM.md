# VADEMECUM: Risoluzione problemi HuggingFace LLM (DELTA Orchestrator)

## Obiettivo
Consentire la risposta in linguaggio naturale tramite fallback HuggingFace, risolvendo l’errore 404 (modello non disponibile via API).

---

## 1. Verifica credenziali HuggingFace
- Accedi a https://huggingface.co/settings/tokens
- Crea un nuovo token **fine-grained** con permesso "Make calls to Inference Providers"
- Esporta il token come variabile d’ambiente:
  ```bash
  export HF_API_TOKEN="<il_tuo_token>"
  ```
- (Opzionale) Inserisci il token in un file `.env` o nel sistema di avvio.

---

## 2. Scegli un modello realmente disponibile
- Vai su https://huggingface.co/models?pipeline_tag=text-generation&sort=downloads
- Filtra per "Inference available" e "Conversational" o "Text Generation"
- Copia il nome di un modello che **NON** abbia badge "This model is not available for Inference API"
- Esempi (verifica sempre la disponibilità!):
  - openai-community/gpt2
  - Qwen/Qwen3-0.6B
  - deepseek-ai/DeepSeek-V3.2

---

## 3. Aggiorna il codice DELTA
- Modifica la lista dei modelli fallback in `delta_orchestrator/nodes/executor_node.py`:
  ```python
  hf_models = [
      "openai-community/gpt2"
  ]
  ```
- Salva e riavvia DELTA.

---

## 4. Testa la chat
- Avvia DELTA
- Accedi alla chat domanda/risposta
- Invia una domanda semplice (es: "ciao come stai?")
- Se ricevi una risposta, la configurazione è corretta.

---

## 5. Se ancora errore 404
- Ripeti il punto 2 con un altro modello.
- Verifica che il token sia valido e abbia i permessi giusti.
- Consulta la documentazione ufficiale: https://huggingface.co/docs/api-inference/index

---

## 6. Alternative
- Configura un endpoint Ollama funzionante su localhost o remoto.
- Usa provider commerciali (Together, Fireworks, etc.) tramite HuggingFace Inference Providers.

---

## 7. Supporto
- Community HuggingFace: https://discuss.huggingface.co/
- Documentazione API: https://huggingface.co/docs/api-inference/index

---

**Nota:** Alcuni modelli richiedono crediti o abilitazione specifica anche se pubblici.

---

# GUIDA PAGINAZIONE MESSAGGI LUNGHI — v3.0

## Cosa è `/continua`?

A partire da **DELTA v3.0**, i messaggi diagnostici e le risposte chat molto lunghi vengono automaticamente divisi in **blocchi** per una migliore UX Telegram.

### Comportamento

#### Diagnosi Lungo
```
[Bot invia blocco 1 del risultato diagnosi]
---
"Messaggio lungo. Per continuare digita /continua."
```

Digiti `/continua`:
```
[Bot invia blocco 2]
---
"Messaggio lungo. Per continuare digita /continua."
```

Digiti `/continua` di nuovo:
```
[Bot invia blocco 3 finale + chiusura speciale]
---
"Posso fare qualcos'altro per te? Sono a tua disposizione 🙂"
```

#### Chat Libera
Stesso meccanismo, ma senza la chiusura con smile finale (comportamento semplice).

### Limite Pagina
- **3500 caratteri** per messaggio Telegram
- Se la risposta supera, viene automaticamente paginata
- Comando `/continua` disponibile solo se ci sono pagine pendenti

### Come Funziona
- Il bot **non richiede input**: se il messaggio è breve, arriva tutto insieme
- Se lungo, il primo blocco arriva subito, poi `/continua` per i successivi
- Nessuna perdita di contenuto: tutto il testo viene mandato in sequenza

---

# BRANDING DELTA PLANT — v3.0

## Aggiornamenti

**DELTA Plant** è il nuovo branding unificato in tutta l'interfaccia Telegram:

### Interfaccia Bot
- Bottone menu: **"🔵 💬 Chiedi a DELTA Plant"** (era "Chiedi a DELTA")
- Welcome: "Benvenuto in @DELTAPLANO_bot. Qui puoi interagire con **DELTA Plant** da Telegram..."
- Diagnosi: **"🩺 RISULTATO DIAGNOSI DELTA Plant:"** (etichetta risultato)

### Sensori Manuali — Novità v3.0
- Digita **`x`** per saltare un sensore (più intuitivo dello spazio vuoto)
- Prompt aggiornato: "Inserisci [sensore] (digita **x** per saltare):"

### Messaggi Diagnosi — Stile Agronomo
- Risultato diagnosi ora generato da **un unico messaggio AI** (non più duplicati)
- Struttura professionale a 5 blocchi:
  1. **Esito tecnico:** classe rilevata, confidenza, stato pianta
  2. **Diagnosi differenziale:** breve analisi delle alternative
  3. **Azioni immediate (0-24h):** interventi urgenti
  4. **Azioni a breve (2-7 giorni):** follow-up strategici
  5. **Monitoraggio e prevenzione:** indicazioni a lungo termine
- Stile: **agronomico professionale**, dettagliato ma chiaro

---

# STABILIZZAZIONE BOOTSTRAP TELEGRAM — v3.0

## Cosa è Cambiato

### Avvio Bot
- Bot Telegram ora usa **polling main-thread** (fix deadlock PTB v20+)
- Se lanciato con flag `--daemon`: solo polling (no CLI)
- Se lanciato da terminale interattivo: CLI in background + polling main thread

### Vantaggi
- ✅ Zero deadlock su avvio concorrente
- ✅ Polling stabile h24
- ✅ No conflitti multi-istanza (se lanciato con `pkill` preventivo)
- ✅ Risposta AI garantita durante diagnosi (no hang)

### Come Avviare

#### Modalità Daemon (24/7)
```bash
cd /home/proctor81/Desktop/DELTA-PLANT
./venv/bin/python main.py --enable-api --enable-telegram --daemon &
```

#### Modalità Interattiva (con CLI locale)
```bash
cd /home/proctor81/Desktop/DELTA-PLANT
./venv/bin/python main.py --enable-api --enable-telegram
# CLI menu appare; polling Telegram in background
```

---

# QUICK TROUBLESHOOTING — v3.0

| Problema | Soluzione |
|----------|-----------|
| `/continua` non compare | Il messaggio è breve (<3500 char); arriva tutto insieme. Se lungo, digita `/continua` dopo il prompt. |
| Diagnosi duplicata | v3.0 unisce tutto in 1 messaggio AI. Se vedi 2 messaggi, è dalla run precedente (consultare log). |
| Chat lunga tagliata | Normale, usa `/continua` per continuare. |
| Skip sensore con spazio non funziona | v3.0 usa **`x`** (digita x, non spazio). |
| "Messaggio lungo. Per continuare..." ma no bottone | `/continua` è un comando, digita nella chat: `/continua` |

---

**Autore:** GitHub Copilot – DELTA 3.0 (Paginazione & Branding)
**Data:** 04/05/2026
**Versione:** 3.0-paginazione-continua
