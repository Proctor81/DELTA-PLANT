# DELTA Plant — Conversational AI Extension

## Architettura

- `/llm/llama_cpp_wrapper.py`: wrapper Python per TinyLlama (llama.cpp, GGUF, streaming)
- `/chat/chat_engine.py`: gestione conversazione, memoria per utente, prompt engineering
- `/bot/deltaplano_bot.py`: logica Telegram, routing, comandi, sessioni
- `/router/router.py`: smistamento tra LLM e Vision (MobileNet)
- `/vision/vision_backend.py`: interfaccia astratta VisionBackend (CPU/Hailo-ready)
- `/vision/mobilenet_service.py`: servizio MobileNet CPU
- `/memory/conversation_memory.py`: memoria conversazionale per utente
- `/main.py`: entry point unificato

## Note
- Tutto gira su Raspberry Pi (16GB RAM)
- Nessuna dipendenza Hailo, ma architettura pronta
- TinyLlama GGUF va posizionato in `/models`
- Serve installare `llama.cpp` e python-telegram-bot
- Logging, limiti token, timeout e streaming previsti

## TODO
- Completare implementazione wrapper llama.cpp (streaming)
- Integrare polling Telegram reale
- Migliorare routing e gestione sessioni
- Testare su Raspberry Pi
