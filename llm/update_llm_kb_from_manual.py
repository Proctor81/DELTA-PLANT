#!/usr/bin/env python3
"""
Script di automazione: aggiorna knowledge base LLM e prompt few-shot con l’indice del manuale.
Da inserire come post-step in Manuale/genera_manuale.py o come hook separato.
"""
from pathlib import Path
import re

# Percorsi
ROOT = Path(__file__).resolve().parent.parent
LLM_DIR = ROOT / "llm"
KB_FILE = LLM_DIR / "knowledge_base_delta.md"
PROMPT_FILE = LLM_DIR / "prompt_fewshot_delta.md"
MANUALE = ROOT / "Manuale" / "genera_manuale.py"
PROMPT_TOC_START = "<!-- MANUAL_TOC_EXAMPLE:START -->"
PROMPT_TOC_END = "<!-- MANUAL_TOC_EXAMPLE:END -->"

# Indice da main()
def estrai_indice():
    lines = MANUALE.read_text(encoding="utf-8").splitlines()
    toc = []
    in_toc = False
    for line in lines:
        if "toc_entries = [" in line:
            in_toc = True
            continue
        if in_toc:
            if "]" in line:
                break
            m = re.match(r'\s*\(\"(.+?)\",', line)
            if m:
                toc.append(m.group(1))
    return toc

# Aggiorna knowledge base

def aggiorna_kb(toc):
    kb = KB_FILE.read_text(encoding="utf-8")
    # Rimuovi vecchia sezione indice se presente
    kb = re.sub(r"## Indice dettagliato del Manuale[\s\S]+$", "", kb, flags=re.MULTILINE)
    kb = kb.rstrip() + "\n\n## Indice dettagliato del Manuale\nEcco l’indice completo del Manuale Utente DELTA (aggiornato automaticamente):\n\n"
    for entry in toc:
        kb += f"{entry}\n"
    KB_FILE.write_text(kb, encoding="utf-8")

# Aggiorna prompt few-shot

def aggiorna_prompt(toc):
    prompt = PROMPT_FILE.read_text(encoding="utf-8")
    toc_block = "\n".join(toc)
    # Rimuovi blocchi generati legacy o marker-based, cosi l'update resta idempotente.
    prompt = re.sub(
        rf"{re.escape(PROMPT_TOC_START)}[\s\S]+?{re.escape(PROMPT_TOC_END)}\s*",
        "",
        prompt,
        flags=re.MULTILINE,
    )
    prompt = re.sub(
        r"### Domanda: Mostrami l['’]indice del manuale[\s\S]+?(?=\n###|\n---|$)",
        "",
        prompt,
        flags=re.MULTILINE,
    )

    # Pulisce i vecchi blocchi raw dell'indice eventualmente accumulati nel file.
    while toc_block in prompt:
        prompt = prompt.replace(toc_block, "")
    prompt = re.sub(r"\n{3,}", "\n\n", prompt)

    # Inserisci nuovo esempio prima di ---
    idx = prompt.find('---')
    if idx == -1:
        prompt = prompt.rstrip() + "\n\n---\n"
        idx = prompt.find('---')
    esempio = (
        f"{PROMPT_TOC_START}\n"
        "### Domanda: Mostrami l’indice del manuale\n"
        "Risposta: Ecco l’indice dettagliato del Manuale Utente DELTA:\n\n"
        f"{toc_block}\n"
        f"{PROMPT_TOC_END}\n\n"
    )
    prompt = prompt[:idx] + esempio + prompt[idx:]
    PROMPT_FILE.write_text(prompt, encoding="utf-8")

if __name__ == "__main__":
    toc = estrai_indice()
    aggiorna_kb(toc)
    aggiorna_prompt(toc)
    print("✔ Knowledge base e prompt few-shot aggiornati con l’indice del manuale.")
