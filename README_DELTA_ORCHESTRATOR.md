# DELTA Ð Multi-LLM Agent Orchestrator (LangGraph Edition)

## Come compilare e avviare il grafo

1. **Installazione dipendenze**
   ```bash
   cd delta_orchestrator
   pip install -r requirements.txt
   ```
2. **Avvio FastAPI**
   ```bash
   uvicorn delta_orchestrator.api.routes:router --host 0.0.0.0 --port 8000
   ```
3. **Avvio con Docker**
   ```bash
   docker-compose up --build
   ```

## Esempio di utilizzo CLI
```python
import asyncio
from delta_orchestrator.integration.delta_bridge import orchestrate_task

async def main():
    result = await orchestrate_task("Diagnosi pianta", {"delta_context": {"plant_type": "pomodoro"}})
    print(result)

asyncio.run(main())
```

## Esempio di chiamata da main.py / Flask / Telegram bot
```python
from delta_orchestrator.integration.delta_bridge import orchestrate_task
# ...
result = asyncio.run(orchestrate_task("Diagnosi pianta", delta_context))
```

## Esempio invocazione main_graph
```python
from delta_orchestrator.graphs.main_graph import MainGraph
from delta_orchestrator.state.schema import DeltaOrchestratorState
import asyncio

graph = MainGraph()
state = DeltaOrchestratorState()
result = asyncio.run(graph.run(state.dict()))
print(result)
```

## Prossimi passi consigliati

# Pipeline LLM attuale

## Chat engine e priorita backend
La pipeline DELTA usa HuggingFace come backend principale per la chat e, nel ramo orchestrator, Ollama come fallback secondario. TinyLlama locale e llama.cpp sono stati rimossi dai flussi runtime.

**Requisiti:**
- Token HuggingFace valido in `.env` (`HF_API_TOKEN`)
- Modello HF configurato in `.env` (`HF_MODEL_NAME`, default consigliato `meta-llama/Llama-3.1-8B-Instruct`)
- (Opzionale orchestrator) endpoint Ollama raggiungibile (`OLLAMA_ENDPOINT`)

**Comportamento:**
- DELTAPLANO_bot e ChatEngine usano esclusivamente HuggingFace.
- L'orchestrator usa HuggingFace e, se non disponibile, prova Ollama.
- In assenza di backend disponibili, viene restituito un messaggio di errore controllato.

**Note:**
- Se ricevi "Errore durante l'elaborazione della domanda. Dettagli: ...", copia qui il traceback per la diagnosi.

## Comandi utili
```
git add .
git commit -m "Patch: consolidamento LLM su HuggingFace/Ollama e rimozione TinyLlama"
git push
```
