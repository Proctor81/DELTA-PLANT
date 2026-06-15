# DELTA v4.0 — Advanced Technical User Guide (Production GA)

**Date:** 15 June 2026  
**Version:** 4.0 (Production GA)  
**Audience:** technical users, agronomists, maintainers, field operators

---

## Overview

This guide reflects the runtime that is actually active in the current DELTA Plant repository. The legacy filename is kept for compatibility, but the content is no longer centered on the old Telegram diagnosis flow based on mandatory plant description, multi-question fallback loops and PlantVillage-only routing.

Today DELTA v4.0 (Production GA) is an operational hybrid stack built around four coordinated layers:

1. Telegram operator experience with guided diagnosis, direct-photo diagnosis, free chat, voice and NASA-ISRO/SAR
2. Hugging Face conversational and multimodal inference for advanced operator-facing reasoning
3. Native edge AI backends for local fallback, structured agronomic scoring and explainability
4. Persistent diagnostic memory, exports and release-grade documentation pipelines

---

## Current Runtime At A Glance

### Production GA status (v4.0)

- DELTA-PLANT is officially out of beta and enters Production GA
- the Telegram diagnosis pipeline is now treated as production-critical surface
- diagnostics, free chat, voice and NASA/SAR context flows are hardened for continuity between turns
- EN/IT license release numbering is aligned to `v4.0 (Production GA)`
- release communication and docs now declare production status consistently

### Operator-facing diagnosis modes

- Guided Telegram diagnosis from the menu uses a VLM-first path
- Direct photo sent freely in chat uses a separate vision-only VLM path
- Native PlantVillage/TFLite classification is still available, but no longer represents the primary Telegram diagnosis route
- Sensor readings remain available automatically from the device or manually through guided input

### Active AI stack

- Primary Telegram vision model: Hugging Face multimodal VLM via `llm/huggingface_llm.py`
- Validated default vision model: `google/gemma-4-31B-it`
- Primary free-chat model: `Qwen/Qwen3-14B`
- Native edge classifiers: `generale` plus `EfficientFormerV2-S1`
- Explainability path: LayerCAM on the native edge branch

### Shared conversation guarantees

- diagnosis results, free chat and explicit `/chat` sessions share the same persisted memory
- follow-up can continue after restart because history is stored on disk
- free chat is suspended automatically while DELTA is waiting for mandatory guided input
- direct-photo diagnosis and guided diagnosis do not steal each other anymore

---

## Telegram Operational Flows

### 1. Guided diagnosis from menu

Entry point:

- `/diagnosi`
- inline button `Effettua una diagnosi della Pianta`

Current runtime flow:

1. DELTA asks for the image source or receives the uploaded image
2. DELTA moves directly to sensor mode after the image is available
3. The operator chooses automatic sensors or manual entry
4. DELTA builds a multimodal prompt with image plus sensor context
5. The VLM produces the diagnostic report
6. If the VLM is unavailable, DELTA falls back to the native local diagnosis path

Important behavioral note:

- the guided workflow no longer asks `Di che pianta si tratta? Descrivimi...`
- plant identification is delegated to the multimodal model directly from the image

### 2. Direct photo in chat

Entry point:

- user sends a plant image outside the guided diagnosis wizard

Current runtime flow:

1. Telegram receives the image in normal chat context
2. DELTA routes the image to the dedicated direct-photo handler
3. The Hugging Face VLM performs a vision-only analysis
4. The diagnosis is returned immediately, without asking for sensors or opening the guided flow

This route is intentionally distinct from the menu-driven diagnosis and must remain distinct in documentation and user training.

### 3. Free chat and explicit `/chat`

- free chat accepts natural-language agronomic questions in the main conversation
- `/chat` opens a dedicated consultation session
- both read and write the same persisted memory used by diagnosis follow-up
- after a diagnosis the operator can ask things like `approfondisci`, `spiega il rischio` or `qual e il nome della pianta` without rebuilding context manually

### 4. Telegram voice behavior

Voice is now documented as a free-chat-first capability.

- incoming voice messages are transcribed with `faster-whisper`
- in `auto` mode DELTA mirrors the input channel: voice in, voice out; text in, text out
- default local TTS is `Piper`
- `edge-tts` is the free fallback
- `ElevenLabs` is optional and premium

Operational boundary:

- voice is primarily intended for free chat
- in guided diagnosis, voice is allowed only where a textual answer is still meaningful, such as manual sensor input or rare native fallback follow-up
- voice is not accepted while DELTA is waiting for a required photo or inline button choice

### Voice stability hardening (v4.0)

In production telemetry we observed a post-diagnosis edge case: on the first voice turn after diagnosis, DELTA could answer with stale SAR fungal-risk explanatory context instead of the operator's actual question.

v4.0 introduces a deterministic guard:

- diagnosis/NASA seed context is no longer injected blindly at first turn
- seed context is applied only for explicit text follow-up requests that are semantically related to diagnosis/SAR context
- for voice turns, stale seed context is ignored to avoid semantic hijacking

Operational result: first voice question after diagnosis now follows the actual transcript intent.

## Advanced Telegram LLM And Report Refinement

This section documents the new advanced DELTAPLANO behavior added after the v3.2 manual baseline. The goal is to make a diagnosis iterative: the operator can enrich the same diagnosis with agronomic parameters or scientific documents instead of restarting the workflow.

### Post-diagnosis agronomic refinement

After each Telegram diagnosis, DELTA stores a structured `last_diagnosis_context` containing the report, sensor context, model path, language and timestamp. Free-chat messages that mention agronomic parameters can trigger a controlled refinement prompt.

Examples of accepted refinement context:

- pH and electrical conductivity (EC)
- salinity, substrate, soil texture and irrigation water quality
- N-P-K, calcium, magnesium, iron, boron and other nutrients
- temperature, humidity, light/LUX and CO2
- nickel, heavy metals or other lab-measured contaminants
- operator observations that change risk interpretation

Implementation notes:

- refinement is routed through `ChatEngine.chat_internal()` to avoid manual knowledge-base hijacking
- the LLM receives the previous diagnosis plus the new values and must state what changes, what remains unchanged, revised risk, corrective actions and monitoring
- the refined diagnosis becomes the new active context for later follow-up

### Scientific PDF/JPEG/PNG report reading

Telegram commands:

- `/analisi` for Italian/Cris mode
- `/analysis` for English/Ryan mode

Supported documents include soil reports, water reports, fruit quality reports, nickel/metals analysis, nutrient panels, salinity/pH/EC analysis and other agronomic or scientific lab documents.

Extraction stack:

- PDF text layer: `pypdf.PdfReader`
- image OCR: `Pillow` plus `pytesseract`
- image fallback: Hugging Face Vision LLM through `HuggingFaceLLM.chat_with_image()`

Routing rule:

- normal plant photos remain plant diagnosis inputs
- images are treated as scientific reports only after `/analisi` or `/analysis`, or when the caption explicitly looks like a report/lab-analysis context

### Cris/Ryan language guarantees

The selected voice persona now controls both speech and written text.

- Cris forces Italian output
- Ryan forces English output
- switching language clears transient chat seeds and resets chat memory while preserving diagnosis context
- voice transcription language does not decide response language: Ryan still answers in English if the audio transcript is Italian
- if the LLM returns the wrong language, DELTA rewrites the response with a stateless internal repair prompt before sending text, caption or TTS

### 5. NASA-ISRO/SAR from Telegram

Entry point:

- `/nasa_sar`
- inline button `Connettiti a NASA-ISRO/SAR`

Runtime behavior:

1. DELTA opens the NASA-ISRO/SAR flow from Telegram
2. The operator can use the Telegram Mini App for GPS acquisition or send the position manually
3. DELTA generates the dashboard with map, climate indicators and compact daily context
4. After the dashboard is delivered, free chat becomes immediately available again

This matters because NASA-ISRO/SAR is no longer a detached side feature: it is part of the same operator experience and the follow-up context remains continuous.

### 6. Diagnosis GPS context: LUX and Environment Type (v3.3)

When a photo is submitted for diagnosis, DELTA asks for GPS position and then:

1. **NASA-ISRO/SAR soil moisture** — weekly analysis (today and previous 6 days)
2. **NASA POWER LUX estimate** — fetches a 14-day window to compensate the 3-7 day NASA POWER data lag, keeps the 7 most recent valid days and computes both daily and mean LUX
3. **Environment classification from satellite image** — downloads the satellite view at zoom 19 (≈50 m radius) and sends it to the VLM with a structured prompt to classify the site as one of:

| Type | Emoji | LUX correction factor |
|------|-------|-----------------------|
| `outdoor` | 🌳 | 1.00 — full solar LUX applied |
| `greenhouse` | 🏡 | 0.50 — glass/polyethylene typically filters 30-55% PAR |
| `indoor` | 🏠 | 0.00 — solar LUX not applicable |

The corrected LUX values (`lux_today_adjusted`, `lux_mean_adjusted`) are passed in the diagnosis prompt so the VLM can reason about light availability in the actual growing context.

**GPS orphan fix (v3.3):** if GPS is received but no diagnosis or NASA/SAR flow is pending (e.g., after a bot restart), DELTA now replies with a clear message instead of silently ignoring the position.

**Cancel fix (v3.3):** `/annulla` now preserves the operator's language preference (Cris/Ryan) when clearing the guided state.

### 7. Satellite image coherence and environment validation (v4.0)

v4.0 enforces image-source coherence between the two satellite-dependent flows:

- the map sent in Telegram NASA/SAR flow
- the satellite image used by the VLM to classify environment (`outdoor` / `greenhouse` / `indoor`)

Both now use the same satellite-image generation path (`get_satellite_image_with_marker`) with aligned parameters (center, radius, zoom, marker), reducing divergence between human-visible map evidence and machine classification evidence.

The guided diagnosis prompt now requires explicit coherence validation between:

- plant-photo visual clues
- GPS-derived satellite environment classification

Expected output behavior in diagnosis block 1:

- explicit environment statement (outdoor/greenhouse/indoor)
- explicit coherence judgement (coherent/incoherent between satellite context and plant photo)
- uncertainty declaration when evidence is weak

### 8. GA acceptance criteria (operational)

For production acceptance in DELTA v4.0, the following criteria are required:

1. voice first-turn after diagnosis must answer the user transcript intent without stale SAR diversion
2. GPS context must expose environment type with confidence and rationale
3. LUX values must be environment-adjusted before diagnosis reasoning (`1.0 outdoor`, `0.5 greenhouse`, `N/A indoor`)
4. diagnosis output must visibly expose environment context and coherence statement
5. fallback behavior (models unavailable, GPS unavailable, web app fallback) must return actionable operator feedback

---

## Diagnosis Output Structure

The modern Telegram diagnosis is not documented as a raw classifier dump anymore. The operator-facing result is a structured professional report.

### Current report shape

1. Quadro sintetico
2. Sintesi diagnostica
3. Diagnosi e rischio
4. Interventi immediati
5. Consigli operativi
6. Monitoraggio e prevenzione

### Quadro sintetico

The snapshot block is optimized for phone readability. It summarizes the most important fields in a compact HTML layout instead of an old fixed-width preformatted card.

### Native fallback extras

When DELTA degrades to the local branch, the report may also expose native diagnostic artifacts such as:

- local AI class
- confidence score
- agronomic rules triggered
- Quantum Risk Score
- LayerCAM overlay or explainability assets

These details remain important, but they are no longer the main way Telegram diagnosis is explained to operators.

---

## Native Edge AI Still Matters

The documentation should not erase the edge branch. It is still part of the runtime, but its role is now explicit.

### Native branch responsibilities

- local fallback if the Hugging Face VLM is unavailable
- explainability generation with LayerCAM
- structured agronomic scoring and Quantum Risk Score
- CLI and API continuity when remote multimodal services are not usable

### Native models documented in repository

- `generale`: MobileNet-based PlantVillage classifier
- `efficientformer`: EfficientFormerV2-S1 with validated int8 runtime and float32 fallback

### What changed in the docs

- PlantVillage classification remains documented as an internal capability
- it is no longer described as the default Telegram diagnosis path
- the old narrative `photo -> description -> TFLite -> conversational rescue` is obsolete

---

## Manual Sensor Input

Manual sensors still matter, but only in the contexts where they are really used now.

### Main active use cases

- guided diagnosis after the image step
- local CLI operation when physical sensors are not connected
- fallback workflows where the operator must complete environmental context manually

### Input fields retained

- temperature
- humidity
- pressure
- light
- CO2
- pH
- EC

The key correction versus older docs is this: manual sensor input is no longer the normal next step after every Telegram photo. It is part of the guided diagnosis path, not of the direct-photo branch.

---

## Persistence And Runtime Data

### Conversation persistence

Per-user sessions are stored under:

`memory/sessions/<user_id>.json`

Documented behavior:

- the latest bounded conversation history survives restarts
- diagnosis follow-up can resume after bot reboot
- service boilerplate and backend errors should not pollute memory

### Diagnostic persistence

DELTA stores structured diagnostic elements such as:

- plant name
- status or disease hypothesis
- sensor context
- risk commentary
- recommendations

This is what makes the post-diagnosis free chat consistent instead of generic.

---

## Operations And Regeneration

### Main runtime command

```bash
python main.py --preflight --enable-api --enable-telegram --daemon
```

### Manual regeneration

The authoritative PDF manual is generated from:

- `Manuale/genera_manuale.py`

Primary output:

- `Manuale/DELTA_Manuale_Utente.pdf`

Recommended regeneration command:

```bash
python Manuale/genera_manuale.py
```

### Related documentation sources to keep aligned

- `README.md`
- `README_LLM_CHAT.md`
- `README_DELTA_ORCHESTRATOR.md`
- `RELEASE.md`
- `Manuale/genera_manuale.py`

---

## Obsolete Documentation Assumptions Removed

The following statements should be considered obsolete and have been removed from the current guide:

- guided Telegram diagnosis requires a manual plant description before analysis
- a freely sent photo follows the same wizard as the guided diagnosis button
- five follow-up questions are the main rescue path for Telegram diagnosis
- PlantVillage/TFLite is the primary Telegram diagnosis engine
- phone output should be rendered as a fixed-width preformatted block

If any other repository document still says one of these things, that document is stale.

---

## Bottom Line

DELTA v3.2 should now be understood as a VLM-first Telegram operator system with a hardened direct-photo path, a distinct guided diagnosis path, persistent post-diagnosis memory, voice-enabled free chat, NASA-ISRO/SAR continuity and a still-important native edge fallback for explainability and local resilience.

That is the runtime this guide documents.
