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

# TinyLlama locale & fallback LLM

## Pipeline LLM locale (TinyLlama)
La pipeline DELTA ora supporta TinyLlama locale tramite llama.cpp (modello GGUF). Il bot Telegram e la CLI usano TinyLlama come LLM principale, con fallback automatico su Ollama e HuggingFace solo se TinyLlama fallisce.

**Requisiti:**
- Modello GGUF valido in `models/tinyllama-1.1b-chat-v1.0-q4_K_M.gguf`
- Binario `llama.cpp` compilato in `llama.cpp/build/bin/llama-cli`
- Python wrapper funzionante: `llm/llama_cpp_wrapper.py`

**Comportamento:**
- DELTAPLANO_bot risponde tramite TinyLlama locale.
- Se TinyLlama fallisce, fallback su Ollama (se attivo) o HuggingFace (se configurato).
- Log dettagliato degli errori Telegram: in caso di errore, il messaggio Telegram mostra il traceback Python per facilitare la diagnosi.

**Note:**
- Se ricevi "Errore durante l'elaborazione della domanda. Dettagli: ...", copia qui il traceback per la diagnosi.
- Se la cartella `llama.cpp` è un repository git annidato, segui le istruzioni nel prompt per usare submodule o gitignore.

## Comandi utili
```
git add .
git commit -m "Patch: integrazione TinyLlama locale, fallback LLM, logging errori Telegram dettagliato"
git push
```
