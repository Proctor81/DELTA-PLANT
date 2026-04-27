# VADEMECUM: Risoluzione problemi HuggingFace LLM (DELTA Orchestrator)

## Obiettivo
Consentire la risposta in linguaggio naturale tramite fallback HuggingFace, risolvendo l’errore 404 (modello non disponibile via API).

---

## 1. Verifica credenziali HuggingFace
- Accedi a https://huggingface.co/settings/tokens
- Crea un nuovo token **fine-grained** con permesso "Make calls to Inference Providers"
- Esporta il token come variabile d’ambiente:
  ```bash
  export HF_API_TOKEN="<il_tuo_token>"
  ```
- (Opzionale) Inserisci il token in un file `.env` o nel sistema di avvio.

---

## 2. Scegli un modello realmente disponibile
- Vai su https://huggingface.co/models?pipeline_tag=text-generation&sort=downloads
- Filtra per "Inference available" e "Conversational" o "Text Generation"
- Copia il nome di un modello che **NON** abbia badge "This model is not available for Inference API"
- Esempi (verifica sempre la disponibilità!):
  - openai-community/gpt2
  - Qwen/Qwen3-0.6B
  - deepseek-ai/DeepSeek-V3.2

---

## 3. Aggiorna il codice DELTA
- Modifica la lista dei modelli fallback in `delta_orchestrator/nodes/executor_node.py`:
  ```python
  hf_models = [
      "openai-community/gpt2"
  ]
  ```
- Salva e riavvia DELTA.

---

## 4. Testa la chat
- Avvia DELTA
- Accedi alla chat domanda/risposta
- Invia una domanda semplice (es: "ciao come stai?")
- Se ricevi una risposta, la configurazione è corretta.

---

## 5. Se ancora errore 404
- Ripeti il punto 2 con un altro modello.
- Verifica che il token sia valido e abbia i permessi giusti.
- Consulta la documentazione ufficiale: https://huggingface.co/docs/api-inference/index

---

## 6. Alternative
- Configura un endpoint Ollama funzionante su localhost o remoto.
- Usa provider commerciali (Together, Fireworks, etc.) tramite HuggingFace Inference Providers.

---

## 7. Supporto
- Community HuggingFace: https://discuss.huggingface.co/
- Documentazione API: https://huggingface.co/docs/api-inference/index

---

**Nota:** Alcuni modelli richiedono crediti o abilitazione specifica anche se pubblici.

---

**Autore:** GitHub Copilot – DELTA 2.0
**Data:** 27/04/2026
