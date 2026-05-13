# Release v3.2 — 13 maggio 2026

## 🚀 DELTA Plant consolida la pipeline edge: runtime int8 validato, documentazione allineata, manuale rigenerato in automatico

Questa release trasforma le novita introdotte nelle versioni precedenti in una catena di deploy coerente: il backend EfficientFormerV2-S1 non e piu solo presente nel repository, ma ha ora una variante int8 realmente eseguibile su questo hardware, una strategia di fallback runtime robusta e una Pipeline X che aggiorna anche manuale e artefatti divulgativi senza passaggi manuali esterni.

### Highlights v3.2

- **EfficientFormer int8 validato**: export calibrato, scarto dei falsi artefatti dynamic-range e inferenza locale confermata con input/output integer
- **Fallback runtime**: il backend EfficientFormer ricade automaticamente su float32 se la variante richiesta non e allocabile
- **Pipeline X estesa**: `tools/pipeline_x.py --resume` ora copre train, export, evaluation, benchmark, dissemination e rigenerazione del manuale PDF
- **Manuale utente revisionato**: aggiornati cover, flussi diagnostici, sezione MLOps, Pipeline X, licenza e release corrente
- **Documentazione coerente**: README, MODEL_CARD, RELEASE e LICENSE allineati alla versione 3.2

### Risultati validati dalla Pipeline X

Validation set: 7,502 campioni PlantVillage su Raspberry Pi 5.

| Metrica | Generale | EfficientFormer |
| --- | --- | --- |
| Accuracy top-1 | 91.70% | 29.42% |
| Accuracy top-3 | 99.23% | 90.19% |
| Macro-F1 | 88.97% | 31.68% |
| Avg latency | 41.360 ms | 308.918 ms |
| P95 latency | 54.318 ms | 582.547 ms |
| Throughput | 24.178 fps | 3.237 fps |

Questi risultati confermano che il backend `generale` rimane il profilo raccomandato per produzione nella release 3.2. EfficientFormerV2-S1 resta invece parte della stack edge per explainability, export, ensemble e sperimentazione comparativa, ma non viene promosso come backend predefinito sulla base delle metriche correnti.

### Changelog v3.2

| Area | Modifica |
|---|---|
| `ai/export_efficientformer_tflite.py` | Export int8 calibrato, validazione artefatti e percorso ONNX dedicato |
| `vision/efficientformer_classifier.py` | Fallback runtime `int8 -> float32` e gestione coerente delle varianti |
| `core/config.py` | Metadata di release 3.2 e backend `efficientformer` allineato al profilo int8 |
| `tools/pipeline_x.py` | Nuovo step `manual` per rigenerare `Manuale/DELTA_Manuale_Utente.pdf` |
| `Manuale/genera_manuale.py` | Revisione profonda del manuale e dei flussi MLOps/diagnostici |
| `LICENSE` | Aggiornamento a Software Release v3.2 |

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
