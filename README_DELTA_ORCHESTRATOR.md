# DELTA Orchestrator - Multi-Agent Layer for DELTA Plant v3.2

## Ruolo nel repository

DELTA Orchestrator e il modulo opzionale che aggiunge orchestrazione multi-step, grafi LangGraph, API FastAPI e strumenti di esecuzione attorno al core di DELTA Plant.

Nella release 3.2 il percorso di produzione del repository resta centrato su:

- stack edge vision a 33 classi
- Pipeline X resumable
- benchmark ed evaluation validati
- pacchetto divulgativo generato automaticamente

L'orchestrator completa questa architettura quando serve coordinare task piu complessi, ma non sostituisce il runtime diagnostico principale.

## Componenti principali

- `delta_orchestrator/graphs/main_graph.py`: grafo principale di orchestrazione
- `delta_orchestrator/nodes/`: planner, router, executor, critic e specialist nodes
- `delta_orchestrator/adapters/`: adapter LLM e integrazioni esterne
- `delta_orchestrator/tools/`: tool di contesto, web search, vision e code execution
- `delta_orchestrator/api/routes.py`: esposizione FastAPI
- `delta_orchestrator/integration/delta_bridge.py`: bridge asincrono verso il resto di DELTA
- `delta_orchestrator/tests/test_orchestrator.py`: copertura di base del modulo

## Backend LLM

Stato runtime documentato per il ramo orchestrator:

- backend primario: HuggingFace Inference API
- fallback opzionale: Ollama via `OLLAMA_ENDPOINT`
- modello HF configurabile tramite `HF_MODEL_NAME`
- in assenza di backend disponibili, il nodo executor restituisce un errore controllato

Questo livello e separato dalla Pipeline X vision: i risultati di benchmark, evaluation e dissemination della release 3.2 vengono prodotti dai tool in root repository, non dal modulo orchestrator.

## Avvio rapido

1. Installare le dipendenze del modulo:

```bash
cd delta_orchestrator
pip install -r requirements.txt
```

2. Avviare l'API FastAPI:

```bash
uvicorn delta_orchestrator.api.routes:router --host 0.0.0.0 --port 8000
```

3. In alternativa, usare Docker:

```bash
docker-compose up --build
```

## Esempi di integrazione

### Chiamata via bridge

```python
import asyncio
from delta_orchestrator.integration.delta_bridge import orchestrate_task

async def main():
   result = await orchestrate_task(
      "Diagnosi pianta",
      {"delta_context": {"plant_type": "pomodoro"}},
   )
   print(result)

asyncio.run(main())
```

### Invocazione diretta del grafo

```python
import asyncio
from delta_orchestrator.graphs.main_graph import MainGraph
from delta_orchestrator.state.schema import DeltaOrchestratorState

graph = MainGraph()
state = DeltaOrchestratorState()
result = asyncio.run(graph.run(state.dict()))
print(result)
```

## Posizionamento nella release 3.2

- il repository principale pubblica la narrativa di release in `README.md`, `MODEL_CARD.md` e `RELEASE.md`
- il pacchetto divulgativo e generato in `logs/attivita_divulgative/`
- l'orchestrator resta un layer avanzato per sperimentazione, integrazione e automazione di task compositi

Per il percorso end-to-end che porta agli artefatti pubblicabili della release 3.2, il riferimento operativo resta:

```bash
python tools/pipeline_x.py --resume
```
