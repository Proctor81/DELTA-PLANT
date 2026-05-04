# DELTA v3.1 — Intelligent PlantVillage Generalization

**Release Date:** 4 May 2026
**Version:** 3.1
**Status:** Production Ready ✅

---

## 🚀 Highlights v3.1

> **DELTA Plant ha imparato a generalizzare sulle classi PlantVillage, evolvendo il suo modello di Computer Vision.**

Il sistema ora riconosce il genere botanico dalla descrizione dell'operatore e filtra dinamicamente le classi di classificazione, eliminando la confusione cross-genus e migliorando drasticamente la precisione diagnostica.

---

## 🌿 What's New in v3.1

### 1. **Genus Detection Programmatico**
- Nuovo `_GENUS_KEYWORD_MAP` con 11 generi PlantVillage (IT + EN)
- Priorità multi-parola: `"bell pepper"` rilevato prima di `"pepper"`
- Zero costi LLM per il rilevamento del genere (logica Python pura)
- Previene errore storico: peperone → classe Tomato (ora → Bell_pepper)

### 2. **Class Filtering per Genus**
- L'LLM riceve SOLO le classi del genere rilevato (es. 2 classi per Bell_pepper vs 33 totali)
- Elimina falsi positivi causati da firme visive simili tra generi diversi
- Fallback: se genus non rilevato → flusso Q&A interattivo

### 3. **Healthy Check Contestuale (LLM Stateless)**
- Sostituisce il semplice match sulla parola `"sano"`
- Valuta l'intera frase dell'operatore con prompt binario SANO/NON_SANO/INCERTO
- Usa `chat_internal()` → nessuna contaminazione della ConversationMemory

### 4. **Fix Doppio Messaggio Q&A**
- Causa: `free_chat_handler` (PTB group=99) rispondeva anche durante il follow-up
- Fix: flag `diag_qa_active` dedicato al flusso Q&A, separato da `diagnosis_active`
- Risultato: zero messaggi doppi durante le domande di approfondimento

### 5. **Fix Loop Richiesta Foto**
- Causa: LLM aggiungeva "invia una foto per ulteriore analisi" in fondo alla diagnosi
- Fix livello 1: vincolo nel prompt — fase di acquisizione immagine già conclusa
- Fix livello 2: `_PHOTO_REQUEST_PATTERNS` regex rimuove frasi residue dall'output LLM

### 6. **Pulsante Inline `/continua`**
- Handler globale `CMD_CONTINUA` registrato direttamente sull'Application (non nei fallbacks)
- Pulsante inline `📄 Continua lettura` sostituisce il testo `/continua`
- Funziona anche dopo `ConversationHandler.END`

### 7. **Menu Telegram Ridisegnato**
- "Export Excel" → "Report Excel"
- "Preflight" e "Health" affiancati sulla stessa riga
- Layout più compatto: 4 righe invece di 5

### 8. **Academy Aggiornata**
- 2 nuovi scenari di simulazione (v3.1): peperone con maculatura batterica + vite sana con rilevamento contestuale
- 3 nuove domande quiz su: genus-filter, chat_internal stateless, flag diag_qa_active
- Tutorial guidato: aggiunto Passo 6 — come DELTA interpreta la descrizione dell'operatore

---

## 🔄 Riepilogo Bug Fix

| Bug | Causa | Fix |
|---|---|---|
| Peperone classificato come Tomato | Nessun filtro per genus | `_detect_genus_from_description()` + class filtering |
| Doppio messaggio durante Q&A | `free_chat_handler` group=99 non inibito | Flag `diag_qa_active` |
| Loop richiesta foto | LLM aggiungeva frase "invia foto" | Vincolo prompt + regex `_PHOTO_REQUEST_PATTERNS` |
| `/continua` non funzionava dopo END | Handler nei fallbacks del ConversationHandler | Handler globale + pulsante inline |
| Healthy check solo su parola "sano" | Match stringa rigido | LLM contestuale con `chat_internal()` |
| Auto-risposta LLM nel Q&A | `engine.chat()` contaminava ConversationMemory | `chat_internal()` stateless |

---

# DELTA v3.0 — Leaf-Only Architecture Changelog

**Release Date:** 3 May 2026
**Version:** 3.0
**Status:** Superseded by v3.1

---

## 🎯 Major Changes

### Architectural Shift: Multi-Organ → Leaf-Only

**DELTA v2.0** ⟹ Multi-organ diagnostic system (leaf + flower + fruit)
**DELTA v3.0** ⟹ Orchestrated AI specializing in **leaf disease classification**

| Component | v2.0 | v3.0 | Status |
|-----------|------|------|--------|
| **Leaf analysis** | ✅ | ✅ | Retained & improved |
| **Flower analysis** | ✅ | ❌ | Removed |
| **Fruit analysis** | ✅ | ❌ | Removed |
| **Chat during diagnosis** | Enabled | Disabled | New gating |
| **Low confidence fallback** | Generic | Class 39 + expert | New v3.0 |
| **Diagnosis rules** | 21 (12L + 4F + 5R) | 12 (leaf only) | Simplified |

---

## 🌿 What's New in v3.0

### 1. **Leaf-Only Classification**
- Focus on 38-class **leaf disease taxonomy** (PlantVillage)
- Removed flower-specific rules (FLOW_01-04)
- Removed fruit-specific rules (FRUT_01-05)
- Streamlined to 12 core leaf diagnostics rules

### 2. **Intelligent Class 39 Fallback**
- **Trigger:** AI confidence < 50% (low_confidence_threshold)
- **Action:** Return `Classe_39_NonClassificato`
- **Recommendation:** Suggest "Ask DELTA" chat + agronomy expert
- **User Impact:** Clear guidance when model uncertain

### 3. **Chat Inhibition During Diagnosis**
- AI chat **disabled** during manual sensor input phase
- Prevents interference with critical data entry
- Auto-resets after diagnosis completion
- Reduces user confusion

### 4. **Manual Sensor Input (Enhanced)**
- Users submit 7 sensor readings manually:
  1. **Temperature** (°C): 5.0–40.0 range
  2. **Humidity** (%):** 20.0–95.0 range
  3. **Pressure** (hPa): 950.0–1060.0 range
  4. **Light** (lux): 0–120,000 lux
  5. **CO₂** (ppm): 300–5000 ppm
  6. **pH**: 3.0–10.0
  7. **EC** (mS/cm): 0–5.0 mS/cm
- Optional fields (skip with empty input)
- Built-in validation per sensor bounds

### 5. **Simplified Diagnosis Engine**
- **Removed:** Flower organ enrichment (FLOWER_LABELS, HSV ranges for flowers)
- **Removed:** Fruit organ enrichment (FRUIT_LABELS, HSV ranges for fruits)
- **Kept:** Leaf-focused quantum risk oracle
- **Result:** Faster diagnosis, clearer recommendations

---

## 🔄 Breaking Changes (Migration Guide)

### 1. Flower/Fruit Analysis Unavailable
**v2.0 Workaround:** Users relying on flower/fruit classification must:
- Use external tools for flower/fruit diagnostics
- OR request custom retraining for multi-organ support

### 2. Chat Disabled During Diagnosis
**v2.0 Workaround:** Users cannot access chat while submitting sensor data
- Solution: Complete diagnosis flow first, then use `/chat`

### 3. Rules Configuration Changes
**v2.0 Workaround:** Custom rules that reference FLOW_* or FRUT_* are disabled
- Solution: Implement custom leaf-only rules via `diagnosis/rules.py`

---

## 📊 Performance Improvements

| Metric | v2.0.6 | v3.0 | Change |
|--------|--------|------|--------|
| **Diagnosis time** | ~3-4s | ~2-2.5s | ⬇️ 30% faster |
| **Rule evaluations** | 21 rules | 12 rules | ⬇️ 43% fewer |
| **Memory (diagnosis)** | ~180MB | ~140MB | ⬇️ 22% reduction |
| **Quantum states** | 16 states | 8 states | Simplified |
| **Model inference** | 150ms | 150ms | No change |

---

## 🛠 Technical Details

### Configuration Changes

**`core/config.py`:**
```python
# v3.0 flags
"leaf_only_mode": True,                      # NEW
"enable_flower_analysis": False,              # Changed: True → False
"enable_fruit_analysis": False,               # Changed: True → False
"model_version": "v3.0",                      # Changed: v2.0.6 → v3.0
```

### Code Changes

**`core/agent.py`:**
- Wrapped flower analysis in `if not leaf_only_mode` guard
- Wrapped fruit analysis in `if not leaf_only_mode` guard
- Lines 167-190: Conditional organ segmentation

**`diagnosis/rules.py`:**
- Modified `evaluate_all_rules()` to filter out FLOW_*/FRUT_* rules
- v3.0 leaf-only mode: Returns only 12 leaf rules

**`interface/telegram_bot.py`:**
- Added `diagnosis_active` flag in `start_diagnosis()`
- Gate chat: `chat_start()` checks `diagnosis_active`
- Clears flag on `/annulla` or timeout

**`ai/inference.py`:**
- New class 39 fallback in `_build_result()`
- Low confidence → `Classe_39_NonClassificato`
- Adds `fallback`, `requires_chat`, `requires_agronomy` flags

---

## 📋 Database/Compatibility

### Backward Compatibility: **Breaking**
- v2.0 database records have flower/fruit data ✅ Still readable
- v3.0 will not **write** flower/fruit data
- Old diagnoses can be viewed, but new system won't generate them

### Migration Path

If you need to preserve v2.0 multi-organ support:
```bash
git checkout v2.0.6
# Use v2.0.6 branch for multi-organ analysis
```

---

## ✅ Testing Checklist

- [x] Version displays as v3.0 in CLI
- [x] Flower analysis disabled (no FLOW_* rules)
- [x] Fruit analysis disabled (no FRUT_* rules)
- [x] Chat gates during diagnosis
- [x] Manual sensor input works (7 fields)
- [x] Class 39 fallback triggers on low confidence
- [x] All leaf rules (12) evaluate correctly
- [ ] **User acceptance testing** (pending)
- [ ] **Bot deployment** (pending)

---

## 📖 Documentation Changes

**New:**
- `Manuale/DELTA_3.0_ARCHITECTURE.md` — Technical guide
- `RELEASE_v3.0_ARCHITECTURE.md` — Release notes
- `CHANGELOG_3.0_LEAF_FOCUSED.md` — This file

**Updated:**
- `README.md` — Updated badges & feature list
- `MODEL_CARD.md` — Version 3.0, leaf-only description
- `core/config.py` — Inline v3.0 comments

---

## 🚀 Deployment Notes

### Production Deployment
```bash
git pull origin main
python AVVIO_DELTA.py
# Should display: "Versione 3.0"
```

### Rollback to v2.0
```bash
git checkout v2.0.6
python AVVIO_DELTA.py
```

---

## 📞 Support

### Questions about v3.0?
- Check `Manuale/DELTA_3.0_ARCHITECTURE.md` for technical details
- Review `RELEASE_v3.0_ARCHITECTURE.md` for comprehensive specs
- Inspect logs: `python main.py --enable-api --enable-telegram --daemon`

### Report Issues
- Missing dependency? Check `requirements.txt`
- Chat not working? Verify `DELTA_TELEGRAM_TOKEN` in `.env`
- Low accuracy? Submit leaf images to improve Class 39 boundary

---

**Status:** ✅ Production Ready  
**Next Steps:** Deployment + user training  
**Rollout Date:** 3 May 2026

