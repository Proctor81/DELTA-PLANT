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
