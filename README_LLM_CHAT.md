# DELTA Plant - Conversational AI Layer v3.2

## Ruolo nella release 3.2

Il layer conversazionale gestisce il dialogo con l'operatore prima, durante e dopo la diagnosi. In v3.2 questa parte del repository resta importante per due motivi:

- mantiene continuita tra diagnosi, follow-up e spiegazioni successive
- rimane coerente con la stack edge documentata e con il backend vision di produzione

La release odierna e focalizzata soprattutto su Pipeline X, benchmark, evaluation e dissemination, ma il valore operativo di DELTA dipende ancora dalla qualita del flusso conversazionale lato utente.

## Componenti principali

- `chat/chat_engine.py`: gestione conversazione, prompt orchestration e chiamate LLM
- `interface/telegram_bot.py`: logica Telegram, sessioni, comandi, modalita voce e delivery dei messaggi
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

## Modalita voce Telegram

La chat Telegram supporta ora un percorso vocale pensato per la chat libera, senza interferire con i flussi strutturati della diagnosi.

- un messaggio vocale in chat libera viene trascritto con `faster-whisper`
- la risposta DELTA usa il normale `ChatEngine`, quindi mantiene memoria e routing esistenti
- in modalita `auto` il bot rispecchia l'input: vocale in ingresso, vocale in uscita; testo in ingresso, testo in uscita
- durante diagnosi guidata, follow-up, upload immagine o altri stati strutturati il vocale viene rifiutato con un messaggio esplicito e il bot chiede testo
- se la sintesi vocale fallisce, il bot risponde automaticamente in testo senza interrompere la sessione

### Comandi operativi

- `/voice auto`: comportamento predefinito, con mirroring tra input e output
- `/voice on`: forza una risposta vocale anche ai messaggi testuali in chat libera
- `/voice off`: disattiva la risposta vocale, ma mantiene la trascrizione dei vocali

### Provider voce supportati

- STT: `faster-whisper`
- TTS predefinito: `Piper`, locale e gratuito, con modello italiano ONNX scaricato nel progetto
- TTS fallback gratuito: `edge-tts`, usato se Piper non e disponibile o non e configurabile
- TTS opzionale premium: `ElevenLabs`, solo se lo configuri esplicitamente

### Variabili ambiente utili

- `HF_API_TOKEN`: backend LLM per la chat
- `HF_MODEL_NAME`: modello HuggingFace da usare per la conversazione
- `Piper`: nessuna chiave API, ma richiede il pacchetto `piper-tts`; il modello viene scaricato automaticamente la prima volta
- `ELEVENLABS_API_KEY`: opzionale, abilita il provider premium ElevenLabs
- `ELEVENLABS_VOICE_ID`: opzionale, consente di scegliere la voce ElevenLabs

## Requisiti essenziali

- Raspberry Pi 5 o ambiente Python 3.12 equivalente
- `HF_API_TOKEN` valido nel file `.env`
- `HF_MODEL_NAME` coerente con il backend HuggingFace scelto
- Telegram bot configurato se si usa l'interfaccia bot
- `piper-tts` installato per la risposta vocale locale gratuita
- `edge-tts` installato come fallback gratuito aggiuntivo
- `ELEVENLABS_API_KEY` solo se si vuole passare a un provider premium

## Relazione con la documentazione pubblica

Per la narrativa completa della release 3.2 e dei risultati validati della Pipeline X fare riferimento a:

- `README.md`
- `MODEL_CARD.md`
- `RELEASE.md`
- `logs/attivita_divulgative/ATTIVITA_DIVULGATIVE.md`

Questo file resta invece focalizzato sul sottosistema chat e sulla sua integrazione con il resto di DELTA Plant.
