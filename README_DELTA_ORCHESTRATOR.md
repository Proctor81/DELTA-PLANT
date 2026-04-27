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
- Integrare delta_context_tool con sensors/, ai/, diagnosis/ reali
- Estendere i tool e i nodi per nuovi casi d'uso
- Abilitare Redis per checkpointing distribuito in cloud
- Aggiungere test di integrazione e validazione edge/cloud
- Aggiornare la documentazione principale di DELTA 2.0
