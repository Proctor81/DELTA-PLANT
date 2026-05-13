# DELTA Plant - Conversational AI Layer v3.2

## Ruolo nella release 3.2

Il layer conversazionale gestisce il dialogo con l'operatore prima, durante e dopo la diagnosi. In v3.2 questa parte del repository resta importante per due motivi:

- mantiene continuita tra diagnosi, follow-up e spiegazioni successive
- rimane coerente con la stack edge documentata e con il backend vision di produzione

La release odierna e focalizzata soprattutto su Pipeline X, benchmark, evaluation e dissemination, ma il valore operativo di DELTA dipende ancora dalla qualita del flusso conversazionale lato utente.

## Componenti principali

- `chat/chat_engine.py`: gestione conversazione, prompt orchestration e chiamate LLM
- `bot/deltaplano_bot.py`: logica Telegram, sessioni, comandi e delivery dei messaggi
- `router/router.py`: instradamento tra richieste chat e flussi vision/diagnosi
- `vision/vision_service.py`: aggancio del backend di classificazione per il layer conversazionale
- `memory/conversation_memory.py`: persistenza della memoria conversazionale per utente
- `main.py`: entry point operativo del sistema

## Comportamento runtime documentato

- backend chat principale: HuggingFace Inference API
- modello configurabile tramite `HF_MODEL_NAME`
- memoria per utente persistita su disco in `memory/sessions/<user_id>.json`
- follow-up diagnostico disponibile anche dopo riavvio del bot
- i flussi legacy TinyLlama non fanno parte del percorso runtime documentato della release 3.2

## Esperienza operatore mantenuta in v3.2

Il layer chat conserva le garanzie introdotte nelle iterazioni precedenti:

- follow-up post-diagnosi senza perdere il contesto immediato
- continuita tra referto strutturato, spiegazioni e raccomandazioni richieste dopo la diagnosi
- routing piu stabile tra richieste libere e fasi guidate della diagnosi
- compatibilita con la memoria persistente e con il backend vision attivo

## Requisiti essenziali

- Raspberry Pi 5 o ambiente Python 3.12 equivalente
- `HF_API_TOKEN` valido nel file `.env`
- `HF_MODEL_NAME` coerente con il backend HuggingFace scelto
- Telegram bot configurato se si usa l'interfaccia bot

## Relazione con la documentazione pubblica

Per la narrativa completa della release 3.2 e dei risultati validati della Pipeline X fare riferimento a:

- `README.md`
- `MODEL_CARD.md`
- `RELEASE.md`
- `logs/attivita_divulgative/ATTIVITA_DIVULGATIVE.md`

Questo file resta invece focalizzato sul sottosistema chat e sulla sua integrazione con il resto di DELTA Plant.
