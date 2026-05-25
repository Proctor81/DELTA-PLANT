# DEMO HERO fallback: sincronizzazione logica browser-backend

Questa repository implementa la logica di fallback DEMO HERO sia lato browser (JS) sia lato backend (Python) per garantire che i dati demo generati in assenza di API siano **identici** tra sito e bot Telegram.

- La funzione Python `build_demo_analysis_payload` in `ai/demo_hero_fallback.py` è la **replica fedele** della funzione JS `buildDemoAnalysisPayload` in `website/nasa-monitor.html`.
- Ogni modifica alla logica demo nel sito **deve essere riportata** anche in Python.
- Vedi `DEMO_HERO_SYNC.md` per la procedura di sincronizzazione.

**Nota:** Se la DEMO HERO viene aggiornata, aggiornare anche il backend Python per evitare disallineamenti tra sito e bot.
