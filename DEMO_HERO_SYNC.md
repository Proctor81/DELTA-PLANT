# Sincronizzazione logica fallback DEMO HERO (browser) e backend Python

## Obiettivo
Garantire che la logica di fallback per la generazione dei dati demo (usata quando le API non restituiscono dati reali) sia **sempre allineata** tra:
- Il sito web (logica JS in `website/nasa-monitor.html`)
- Il backend Python (`ai/demo_hero_fallback.py`)

## Regole operative
- **Ogni modifica** alla logica di generazione dati demo lato sito **deve essere replicata** in `ai/demo_hero_fallback.py`.
- La funzione di riferimento è `build_demo_analysis_payload` (Python) che deve restituire dati identici alla funzione JS `buildDemoAnalysisPayload`.
- Tutti i parametri, formule, soglie e struttura dell’output devono essere mantenuti sincronizzati.
- In caso di divergenza, il backend Python **deve essere aggiornato** per riflettere la logica più recente del sito.
- Annotare in questo file ogni modifica rilevante e la data di sincronizzazione.

## Procedura di sincronizzazione
1. Ogni volta che si aggiorna la logica demo nel sito, copiare le modifiche anche in `ai/demo_hero_fallback.py`.
2. Validare che l’output Python sia identico a quello della DEMO HERO per gli stessi input.
3. Aggiornare la sezione changelog qui sotto.

## Changelog sincronizzazione
- 2024-06-XX: Prima integrazione logica fallback DEMO HERO in Python (`ai/demo_hero_fallback.py`)
- [aggiungi qui le future modifiche]

---
**IMPORTANTE:** Questa sincronizzazione è fondamentale per garantire che il bot Telegram e il backend DELTA Plant restituiscano sempre dati demo identici alla DEMO HERO, senza disallineamenti.
