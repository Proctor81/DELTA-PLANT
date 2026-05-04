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
