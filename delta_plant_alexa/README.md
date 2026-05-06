# DELTA Plant Alexa

Modulo indipendente che espone **DELTA-PLANT** come Alexa Custom Skill pubblica.
Fornisce accesso esclusivo alla conversazione agronomica: nessuna funzione di
visione artificiale, sensori, quantum, training o admin è raggiungibile tramite
questa skill.

---

## Indice

1. [Architettura](#architettura)
2. [Struttura modulo](#struttura-modulo)
3. [Lingue supportate](#lingue-supportate)
4. [Integrazione con DELTA-PLANT](#integrazione-con-delta-plant)
5. [Endpoint Flask opzionale](#endpoint-flask-opzionale)
6. [Sicurezza: misure implementate](#sicurezza-misure-implementate)
7. [Limitazioni di sicurezza dichiarate](#limitazioni-di-sicurezza-dichiarate)
8. [Privacy e compliance Alexa](#privacy-e-compliance-alexa)
9. [Avvio locale per sviluppo](#avvio-locale-per-sviluppo)
10. [Canale Telegram per funzioni avanzate](#canale-telegram-per-funzioni-avanzate)

---

## Architettura

```
Utente Alexa
    │  voce
    ▼
Alexa Voice Service  (AWS)
    │  JSON request
    ▼
AWS Lambda  ──► SkillIdVerificationInterceptor  (blocca skill ID errate)
    │
    ▼
Handler routing (ASK SDK)
    │
    ├── LaunchRequestHandler
    ├── LanguageSwitchHandler
    ├── ChatIntentHandler
    │       │
    │       ├── InputSanitizer        (normalizza + blacklist + regex)
    │       ├── ThreatDetector        (rate limit + keyword + regex euristiche)
    │       ├── DeltaOrchestratorClient
    │       │       ├── chiamata diretta delta_orchestrator (try/except rigoroso)
    │       │       └── fallback HTTP opzionale
    │       └── ResponseGuard         (blocco output pericoloso + redazione secret)
    ├── HelpIntentHandler
    ├── FallbackIntentHandler
    ├── CancelAndStopIntentHandler
    ├── SessionEndedRequestHandler
    └── GenericExceptionHandler       (no stack trace in output vocale)
```

Il modulo è progettato per girare come **funzione Lambda autonoma** e non richiede
alcuna modifica ai moduli esistenti di DELTA-PLANT.

---

## Struttura modulo

```
delta_plant_alexa/
├── lambda_function.py          # Entry point Lambda + SkillBuilder
├── requirements.txt            # Dipendenze isolate
├── config.py                   # Configurazione sicurezza centralizzata
├── interaction_models/         # Intent model per 6 lingue (Alexa Console)
│   ├── it-IT.json
│   ├── en-US.json
│   ├── fr-FR.json
│   ├── de-DE.json
│   ├── es-ES.json
│   └── nl-NL.json
├── handlers/
│   ├── launch_handler.py       # Benvenuto + disclaimer Telegram
│   ├── chat_handler.py         # Multi-turn fino a 12 turni
│   ├── language_handler.py     # Cambio lingua a runtime
│   ├── fallback_handler.py     # Intent non riconosciuto
│   ├── help_handler.py         # Guida uso + info privacy
│   └── session_ended_handler.py
├── utils/
│   ├── delta_orchestrator_client.py  # Client sicuro + structured prompting
│   ├── input_sanitizer.py            # Sanitizzazione aggressiva input
│   ├── response_guard.py             # Validazione output orchestrator
│   ├── ssml_builder.py               # SSML con escape XML
│   └── language_manager.py           # Gestione locale
├── security/
│   └── threat_detector.py     # Blacklist + rate limit + logging sospetti
├── flask_endpoint/
│   └── alexa_chat_endpoint.py # Blueprint Flask /api/alexa/chat
├── README.md
└── DEPLOY.md
```

---

## Lingue supportate

| Locale  | Lingua    | Voce SSML |
|---------|-----------|----------|
| it-IT   | Italiano  | Giorgio  |
| en-US   | Inglese   | Matthew  |
| fr-FR   | Francese  | Mathieu  |
| de-DE   | Tedesco   | Hans     |
| es-ES   | Spagnolo  | Enrique  |
| nl-NL   | Olandese  | Ruben    |

Il cambio lingua avviene tramite comandi vocali:

- *"Alexa, parla in inglese"*
- *"Alexa, cambia lingua in francese"*
- *"Alexa, switch to German"*

Il locale viene mantenuto negli `session_attributes` per tutta la durata della
sessione e applicato a SSML, messaggi di servizio e structured prompt
all'orchestrator.

---

## Integrazione con DELTA-PLANT

### Chiamata diretta (preferita)

`DeltaOrchestratorClient` tenta prima una chiamata in-process:

```python
from delta_orchestrator.integration.delta_bridge import orchestrate_task
result = await orchestrate_task(structured_prompt, orchestrator_state)
```

Il `try/except` è rigoroso: qualsiasi eccezione del bridge viene intercettata,
loggata e tradotta in una risposta di fallback sicura senza esporre internals.

### Fallback HTTP (opzionale)

Se la chiamata diretta fallisce e `DELTA_ALEXA_ORCHESTRATOR_HTTP_URL` è
configurato, viene tentata una chiamata REST verso l'endpoint
`POST /orchestrate` dell'orchestrator.

Se anche il fallback HTTP fallisce, la skill risponde con un messaggio neutro
che invita a riprovare o usare Telegram DELTA.

### Contesto passato all'orchestrator

Per isolamento funzionale, il contesto inviato forza a `null` tutti i campi
sensibili:

```python
delta_context = {
    "tflite_diagnosis": None,   # nessuna diagnosi immagine
    "sensor_data": None,        # nessun dato sensore
    "quantum_risk_score": None, # nessun quantum module
    "image_path": None,         # nessun path immagine
    "plant_type": "generic",
}
```

---

## Endpoint Flask opzionale

Registra il blueprint sull'app Flask principale di DELTA:

```python
# In interface/api.py o main.py
from delta_plant_alexa.flask_endpoint.alexa_chat_endpoint import alexa_chat_bp
app.register_blueprint(alexa_chat_bp)
```

**Chiamata di test:**

```bash
curl -X POST http://localhost:5000/api/alexa/chat \
  -H "Content-Type: application/json" \
  -H "X-Alexa-Skill-Id: amzn1.ask.skill.YOUR_SKILL_ID" \
  -d '{"message": "Come tratto la peronospora?", "session_id": "test-001", "locale": "it-IT"}'
```

**Risposta:**

```json
{
  "answer": "La peronospora si tratta con prodotti a base di rame...",
  "blocked": false,
  "reason": ""
}
```

L'endpoint **non è pubblico per design**: deve essere protetto a monte da
authentication middleware, VPN o token API.

---

## Sicurezza: misure implementate

### 1. Verifica Skill ID (AWS Lambda)

Ogni invocazione Lambda verifica che `application.application_id` corrisponda
a `DELTA_ALEXA_SKILL_ID`. Richieste da skill diverse vengono rifiutate prima di
qualsiasi elaborazione.

### 2. Sanitizzazione input aggressiva (`InputSanitizer`)

- Normalizzazione NFKC per ridurre bypass tramite omoglifi di base
- Rimozione caratteri di controllo (`\x00-\x1F`, `\x7F`)
- Collapse whitespace anomali
- Limite hard di 550 caratteri
- Neutralizzazione marker strutturali injection (` ``` `, `<system>`, `<developer>`, `[[...]]`)
- Validazione finale su blacklist + regex euristiche

### 3. Blacklist e regex anti-injection (`ThreatDetector`)

Keyword bloccate (non esaustive):
`ignore previous instructions`, `system prompt`, `jailbreak`, `bypass`,
`admin`, `root`, `sudo`, `photo`, `image`, `sensor`, `quantum`, `train`,
`export`, `delete`, `credential`, `token`, `password`, `shell`, `bash`

Regex euristiche:
- `ignore\s+(all\s+)?previous\s+instructions`
- `reveal\s+(the\s+)?system\s+prompt`
- `\b(jailbreak|bypass|override)\b`
- `\b(api\s*key|secret|token|password|credential)\b`

### 4. Structured prompting

Input utente e istruzioni sistema sono separati in blocchi distinti:

```
### SYSTEM_INSTRUCTIONS
[istruzioni fisse non modificabili dall'utente]

### SECURITY_CONSTRAINTS
[vincoli accesso espliciti]

### USER_CONTEXT
locale=it-IT

### USER_INPUT
[testo sanitizzato dell'utente]
```

### 5. Output guard (`ResponseGuard`)

- Blocco pattern pericolosi in uscita (comandi shell, credenziali, ecc.)
- Secondo pass regex per azioni distruttive (`rm -rf`, `drop table`, `curl http`, ecc.)
- Redazione automatica di token/chiavi (`hf_...`, `sk-...`, `AKIA...`)
- Limite 1200 caratteri output parlato
- Fallback neutro se la risposta non supera la validazione

### 6. Rate limiting per sessione

Massimo 18 richieste per sessione Alexa (configurabile via `DELTA_ALEXA_MAX_REQ_SESSION`).
Al superamento la skill invita a chiudere e riaprire la sessione.

### 7. Least privilege contesto

Tutti i campi sensibili dello stato orchestrator (`sensor_data`, `tflite_diagnosis`,
`quantum_risk_score`, `image_path`) vengono forzati a `null` prima di ogni chiamata.

### 8. Logging privacy-safe

I tentativi sospetti vengono registrati con:
- hash SHA-256 breve (12 caratteri) del testo utente
- lunghezza del testo
- tipo evento e pattern corrispondente

Il testo originale non viene mai salvato nei log.

---

## Limitazioni di sicurezza dichiarate

| Limitazione | Descrizione | Mitigazione |
|---|---|---|
| Omoglifi avanzati | La normalizzazione NFKC copre casi comuni ma non tutti i possibili omoglifi Unicode | Aggiungere una libreria confusable-homoglyphs se il profilo di rischio lo richiede |
| Rate limit in memoria | Il rate limiter per sessione è in-memory: non persiste tra cold start Lambda distanti | Usare ElastiCache/DynamoDB per rate limiting distribuito in ambienti ad alto volume |
| Llamata diretta orchestrator | Se il processo Lambda condivide memoria con l'orchestrator, un bug nell'orchestrator potrebbe avere scope più ampio | Valutare deploy Lambda isolato senza import diretti in ambienti ad alto rischio |
| SSML injection parziale | L'escape HTML copre caratteri speciali XML standard; tag Alexa proprietari non standard potrebbero non essere coperti | Rivedere se si usano estensioni SSML custom |
| Voce SSML dipendente da regione | Non tutti i profili voce SSML sono disponibili in tutte le regioni Alexa | Testare la disponibilità delle voci nel Developer Console e aggiornare `VOICE_BY_LOCALE` |

---

## Privacy e compliance Alexa

- **Dati conversazionali**: conservati solo nella `session` Alexa (in-memory, non persistita
  a fine sessione). Nessun database esterno coinvolto dalla skill.
- **Dati personali**: nessuna raccolta di nome, email, posizione o dati biometrici.
- **Reindirizzamento**: gli utenti vengono informati nel benvenuto e nell'help che
  funzioni avanzate (foto, sensori, diagnosi AI) richiedono il canale Telegram DELTA.
- **Policy Alexa per skill pubbliche**: la skill non raccoglie dati non necessari e
  non effettua acquisti in-skill. La privacy policy deve essere pubblicata sulla
  pagina della skill nel Alexa Developer Console.
- **GDPR**: poiché nessun dato personale è persistito dalla skill, il trattamento
  è limitato alla sessione vocale effimera gestita da Amazon.

---

## Avvio locale per sviluppo

```bash
# Dalla root di DELTA-PLANT
pip install -r delta_plant_alexa/requirements.txt

# Test unitario rapido (richiede ask-sdk installato)
python -c "
from delta_plant_alexa.utils.input_sanitizer import InputSanitizer
s = InputSanitizer()
print(s.sanitize_user_input('Come irrigare il pomodoro?', 'test-session'))
"

# Avvio Flask con endpoint Alexa
export DELTA_ALEXA_SKILL_ID=amzn1.ask.skill.your-skill-id
export HF_API_TOKEN=hf_your_token
python main.py  # se alexa_chat_bp è registrato sull'app principale
```

---

## Canale Telegram per funzioni avanzate

La skill Alexa è intenzionalmente limitata alla chat conversazionale.
Per funzioni avanzate usa il bot Telegram DELTA:

- Diagnosi malattie fogliari tramite foto
- Lettura dati sensori ambientali in tempo reale
- Analisi AI con modello TFLite
- Esportazione report
- Gestione accademia e progressi

