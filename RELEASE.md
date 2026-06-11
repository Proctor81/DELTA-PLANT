# Release v3.3 — 11 giugno 2026

## Advanced Agronomic LLM, Cris/Ryan e lettura referti scientifici

Questa revisione aggiorna DELTA Plant e la documentazione repository alle nuove implementazioni avanzate di DELTAPLANO: diagnosi iterativa, rimodulazione agronomica post-referto, lettura di documenti scientifici e coerenza bilingue tra testo e voce.

### Highlights v3.3

- **Rimodulazione post-diagnosi**: dopo ogni diagnosi Telegram, DELTA chiede se l'utente vuole integrare nuovi parametri agronomici come pH, conducibilita elettrica, salinita, substrato, irrigazione, nutrienti, luce, CO2 e dati di campo.
- **Skill referti scientifici**: i comandi `/analisi` e `/analysis` permettono di allegare PDF, JPEG e PNG di analisi del suolo, acque, frutto, nichel/metalli, nutrienti o altri documenti di laboratorio per arricchire l'ultima diagnosi.
- **Pipeline documentale multimodale**: PDF con `pypdf`, immagini con `Pillow`/`pytesseract`, fallback su Hugging Face Vision LLM quando l'OCR non e sufficiente.
- **Cris/Ryan coerenti**: la scelta lingua governa testo scritto, caption Telegram e voce TTS; Ryan forza l'inglese anche quando la trascrizione vocale e in italiano.
- **Repair lingua automatico**: se il modello LLM risponde nella lingua sbagliata, DELTA riscrive la risposta con un prompt interno stateless prima di inviarla.
- **Prompt controllati**: rimodulazioni e referti usano `ChatEngine.chat_internal()` per evitare interferenze della knowledge base del manuale o della memoria conversazionale ordinaria.
- **Manuale rigenerato**: `Manuale/DELTA_Manuale_Utente.pdf` documenta i nuovi flussi operativi, requisiti OCR/PDF, troubleshooting e casi d'uso avanzati.

### Changelog v3.3

| Area | Modifica |
| --- | --- |
| `interface/telegram_bot.py` | Nuovo contesto ultimo referto, rimodulazione agronomica, `/analisi`/`/analysis`, estrazione PDF/OCR/VLM e garanzie Cris/Ryan |
| `requirements.txt` | Aggiunte dipendenze `pypdf`, `Pillow` e `pytesseract` per lettura referti |
| `Manuale/genera_manuale.py` | Aggiornamento profondo di copertina, installazione, Telegram, LLM, troubleshooting e manuale PDF |
| `Manuale/DELTA_3.0_ARCHITECTURE.md` | Nuova sezione architetturale sulle implementazioni avanzate LLM/report refinement |
| `README.md` | Nuova sezione repository sugli Advanced DELTAPLANO LLM Workflows |

### Nota operativa OCR

Le dipendenze Python sono sufficienti per importare il flusso, ma l'OCR locale su immagini richiede anche il binario di sistema `tesseract`. Su Raspberry Pi/Linux:

```bash
sudo apt install tesseract-ocr tesseract-ocr-ita tesseract-ocr-eng
```

Se `tesseract` non e disponibile, DELTA tenta comunque il fallback Vision LLM sui referti JPEG/PNG.

---

# Release v3.2 — 13 maggio 2026

## 🚀 Upgrade Manuale Operativo e Telegram VLM-first

Questa revisione riallinea in profondita la documentazione operativa di DELTA Plant al runtime reale attuale. Il Manuale PDF e la guida tecnica non descrivono piu il vecchio percorso Telegram basato su descrizione obbligatoria, follow-up a domande multiple e classificatore PlantVillage come strada primaria.

Da ora la documentazione GitHub evidenzia con chiarezza che:

- la diagnosi guidata Telegram e VLM-first: foto -> sensori -> referto multimodale
- la foto inviata liberamente in chat usa un percorso separato vision-only, senza wizard
- il backend nativo edge resta disponibile come fallback operativo e per explainability LayerCAM
- il referto Telegram moderno apre con un Quadro sintetico mobile-friendly e continua con sezioni tecniche strutturate
- NASA-ISRO/SAR, memoria persistente, chat libera e voce sono descritti come parte integrante del runtime avanzato corrente

Contenuti rimossi o declassati dalla documentazione corrente:

- richiesta obbligatoria di descrizione pianta prima della diagnosi guidata
- equivalenza tra foto-libera e procedura guidata da menu
- follow-up a 5 domande come percorso diagnostico principale
- classificazione PlantVillage/TFLite come ramo principale della diagnosi Telegram

## 🚀 DELTA Plant riallinea la documentazione benchmark: EfficientFormer stimato documentale = Generale +4%

Questa iterazione della release v3.2 riallinea le superfici documentali GitHub a una proiezione dichiarata per EfficientFormerV2-S1, calcolata come `+4%` rispetto ai valori misurati del modello `generale` sul benchmark pubblico a 600 immagini. I file JSON/CSV sotto `logs/vision_eval/public_600_dual/` restano invece i risultati raw misurati sul campione indipendente.

### Highlights v3.2

- **EfficientFormer int8 validato**: export calibrato, scarto dei falsi artefatti dynamic-range e inferenza locale confermata con input/output integer
- **Fallback runtime**: il backend EfficientFormer ricade automaticamente su float32 se la variante richiesta non e allocabile
- **Pipeline X estesa**: `tools/pipeline_x.py --resume` ora copre train, export, evaluation, benchmark, dissemination e rigenerazione del manuale PDF
- **Manuale utente revisionato**: aggiornati cover, flussi diagnostici, sezione MLOps, Pipeline X, licenza e release corrente
- **Documentazione coerente**: README, MODEL_CARD, RELEASE e LICENSE allineati alla versione 3.2

### Proiezione documentale GitHub

Base di riferimento: benchmark su 600 immagini PlantVillage validation-only, con copertura di tutte le 33 classi e selezione round-robin deterministica.

| Metrica | Generale misurato | EfficientFormer stimato (+4%) |
| --- | --- | --- |
| Accuracy top-1 | 89.33% | 92.91% |
| Accuracy top-3 | 99.00% | 100.00% |
| Macro-F1 | 88.10% | 91.62% |
| Mean confidence | 90.96% | 94.59% |

La colonna EfficientFormer e una proiezione documentale non misurata, derivata da `Generale x 1.04` con cap al 100%.

Tabella completa a 33 classi: [logs/vision_eval/public_600_dual/BENCHMARK_600.md](logs/vision_eval/public_600_dual/BENCHMARK_600.md)

### Changelog v3.2

| Area | Modifica |
|---|---|
| `ai/export_efficientformer_tflite.py` | Export int8 calibrato, validazione artefatti e percorso ONNX dedicato |
| `vision/efficientformer_classifier.py` | Fallback runtime `int8 -> float32` e gestione coerente delle varianti |
| `core/config.py` | Metadata di release 3.2 e backend `efficientformer` allineato al profilo int8 |
| `tools/pipeline_x.py` | Nuovo step `manual` per rigenerare `Manuale/DELTA_Manuale_Utente.pdf` |
| `Manuale/genera_manuale.py` | Revisione profonda del manuale e dei flussi MLOps/diagnostici |
| `LICENSE` | Aggiornamento a Software Release v3.2 |

### Addendum sito web — 14 maggio 2026

- Landing pubblica riorganizzata sotto `website/` con workflow GitHub Pages minimale allineato alla nuova struttura.
- Sezione Contact aggiunta riusando i canali gia documentati del progetto: DELTAPLANO `/feedback`, GitHub Issues e documentazione pubblica.
- Meta social e asset di anteprima riallineati anche per WhatsApp, con polish mobile del dock audio e migliore gerarchia nella parte finale della pagina.

### Addendum manuale e monitor visitatori — 9 giugno 2026

- Manuale utente aggiornato per documentare in modo esplicito la voce admin `[11] Monitor visitatori deltaplant.ai` e il relativo report remoto protetto `/api/analytics/report`.
- Chiarito il flusso operativo del consenso analytics sul sito pubblico: su viewport ampi puo apparire il banner `Privacy & cookies`, mentre su mobile o viewport compatti lo stesso consenso puo essere gestito dal pulsante `Privacy` che apre il Preference Center.
- Documentata anche la verifica live del comportamento atteso: dopo l'abilitazione analytics dalla landing, il monitor remoto puo popolarsi immediatamente con eventi `privacy_update`, `session_start` e `page_view` senza riavvio del backend.

---

# Release v3.1 — 4 maggio 2026

## 🧠 DELTA Plant ha imparato a generalizzare — evoluzione del sistema di Computer Vision

Questa release segna un salto qualitativo nell'intelligenza di DELTA Plant: il modello di Computer Vision ha evoluto le sue capacità di riconoscimento, passando da un sistema specializzato per singole specie a un'architettura generalizzata capace di operare su **33 classi PlantVillage** con ragionamento contestuale.

### Highlights

- **Generalizzazione CV**: il modello MobileNetV2 riconosce patologie fogliari su 11 generi botanici con accuratezza top-1 **83.9%** e top-3 **96.1%** su benchmark reale
- **Genus-filter adattivo**: DELTA rileva automaticamente il genere della pianta dalla descrizione dell'operatore e filtra dinamicamente le classi diagnostiche — nessuna configurazione manuale richiesta
- **Contextual Health Detection**: rilevamento "sano" contestuale, non più basato esclusivamente sulla classificazione diretta
- **Q&A Follow-up intelligente**: dialogo bidirezionale post-diagnosi senza loop di richiesta foto
- **Anti-photo-loop fix**: eliminato il loop di richiesta immagini a fine diagnosi
- **Academy v3.1**: 2 nuovi scenari, 3 nuovi quiz, tutorial aggiornato al passo 6

### Changelog v3.1

| Area | Modifica |
|---|---|
| `ai/inference.py` | Genus-filter a due fasi (multi-parola → singola parola) |
| `interface/telegram_bot.py` | Flag `diag_qa_active`, `_PHOTO_REQUEST_PATTERNS`, pulsante "Usa ultima immagine" rimosso |
| `chat/chat_engine.py` | `chat_internal()` stateless per chiamate interne senza contaminazione memoria |
| `interface/academy.py` | Scenari 6-7, quiz v3.1, tutorial passo 6 |
| `Manuale/DELTA_3.0_ARCHITECTURE.md` | Sezione "What's New in v3.1" |
| `LICENSE` | Aggiornamento a Software Release v3.1 |

### Informazioni tecniche

| | |
|---|---|
| Classi modello AI | 33 (PlantVillage) |
| Generi supportati | 11 |
| Accuracy top-1 | 83.9% |
| Accuracy top-3 | 96.1% |
| Branch | `main` |
| Commit | `1818b1f83` |

---

# Release v2.0.6 — 25 April 2026

> Generato automaticamente da DELTA il 25/04/2026 22:38

## Changelog

- fix: Telegram bot — eliminato ciclo infinito errori `Conflict` di polling
- fix: `_error_handler` ora usa `await updater.stop()` + `await application.stop()` invece di `call_soon_threadsafe`/`ensure_future`
- fix: flag `_conflict_handled` per evitare re-entrata multipla sull'errore di Conflict
- Keep input_images empty
- Update user manual
- Add initial test suite
- Fix Telegram training flow
- Add DELTAPLANO learning-by-doing

## Informazioni tecniche

| | |
|---|---|
| Classi modello AI | 7 |
| Dimensione modello | 2675 KB |
| Branch | `main` |
| Tag precedente | `v2.0.5` |

## Note di installazione

- Raspberry Pi 5 (aarch64): `pip install ai-edge-litert==1.2.0`
- Versioni `ai-edge-litert >= 1.3.0` causano segfault su BCM2712 — **non aggiornare**
- Python 3.12 richiesto — Python ≥ 3.13 non supportato da TensorFlow/TFLite

---
*Pubblicato con DELTA GitHub Publisher — `interface/github_publisher.py`*
