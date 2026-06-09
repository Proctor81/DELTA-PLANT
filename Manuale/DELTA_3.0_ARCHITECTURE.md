# DELTA v3.2 — Advanced Technical User Guide

**Date:** 9 June 2026  
**Version:** 3.2  
**Audience:** technical users, agronomists, maintainers, field operators

---

## Overview

This guide reflects the runtime that is actually active in the current DELTA Plant repository. The legacy filename is kept for compatibility, but the content is no longer centered on the old Telegram diagnosis flow based on mandatory plant description, multi-question fallback loops and PlantVillage-only routing.

Today DELTA v3.2 is an operational hybrid stack built around four coordinated layers:

1. Telegram operator experience with guided diagnosis, direct-photo diagnosis, free chat, voice and NASA-ISRO/SAR
2. Hugging Face conversational and multimodal inference for advanced operator-facing reasoning
3. Native edge AI backends for local fallback, structured agronomic scoring and explainability
4. Persistent diagnostic memory, exports and release-grade documentation pipelines

---

## Current Runtime At A Glance

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
