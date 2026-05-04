"""
DELTA - tools/hf_token_check.py
Verifica e aggiorna il token HuggingFace in .env.

Uso:
    python tools/hf_token_check.py            # solo verifica
    python tools/hf_token_check.py --set hf_IL_TUO_TOKEN   # aggiorna .env
    python tools/hf_token_check.py --interactive             # guida interattiva
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = BASE_DIR / ".env"

HELP_MSG = """
Come ottenere un token HuggingFace valido:
  1. Vai su  https://huggingface.co/settings/tokens
  2. Clicca  "New token"
  3. Tipo:   Fine-grained
  4. Abilita "Make calls to Inference Providers" (sezione Inference)
  5. Copia il token (inizia con hf_...)
"""


def load_dotenv() -> dict:
    """Carica le variabili da .env senza dipendenze esterne."""
    env: dict = {}
    if not ENV_FILE.exists():
        return env
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        env[key.strip()] = value.strip().strip('"').strip("'")
    return env


def update_env_token(new_token: str) -> None:
    """Aggiorna HF_API_TOKEN nel file .env."""
    if not ENV_FILE.exists():
        ENV_FILE.write_text(f"HF_API_TOKEN={new_token}\n", encoding="utf-8")
        print(f"  ✓ Creato .env con il nuovo token.")
        return

    content = ENV_FILE.read_text(encoding="utf-8")
    pattern = r"^HF_API_TOKEN\s*=.*$"
    replacement = f"HF_API_TOKEN={new_token}"

    if re.search(pattern, content, re.MULTILINE):
        new_content = re.sub(pattern, replacement, content, flags=re.MULTILINE)
        ENV_FILE.write_text(new_content, encoding="utf-8")
        print(f"  ✓ HF_API_TOKEN aggiornato in {ENV_FILE}")
    else:
        with ENV_FILE.open("a", encoding="utf-8") as f:
            f.write(f"\n{replacement}\n")
        print(f"  ✓ HF_API_TOKEN aggiunto in {ENV_FILE}")


def validate_token(token: str) -> tuple[bool, str]:
    """Verifica il token tramite whoami HuggingFace."""
    if not token:
        return False, "Token vuoto"
    if not token.startswith("hf_"):
        return False, f"Formato token non valido (dovrebbe iniziare con 'hf_')"
    try:
        from huggingface_hub import HfApi
        api = HfApi(token=token)
        info = api.whoami()
        username = info.get("name", "sconosciuto")
        return True, f"Token valido — utente HF: {username}"
    except ImportError:
        return False, "huggingface_hub non installato (pip install huggingface_hub)"
    except Exception as exc:
        err = str(exc)
        if "401" in err or "unauthorized" in err.lower() or "invalid" in err.lower() or "token" in err.lower():
            return False, "401 Unauthorized — token scaduto o non valido"
        return False, f"Errore verifica: {exc}"


def test_inference(token: str) -> tuple[bool, str]:
    """Testa una chiamata di inferenza minima."""
    try:
        from huggingface_hub import InferenceClient
        client = InferenceClient(api_key=token, timeout=30)
        resp = client.chat.completions.create(
            model="meta-llama/Llama-3.1-8B-Instruct",
            messages=[{"role": "user", "content": "Rispondi con una sola parola: ciao"}],
            max_tokens=10,
            temperature=0.1,
        )
        answer = resp.choices[0].message.content.strip()
        return True, f"Inferenza OK — risposta: '{answer}'"
    except Exception as exc:
        return False, f"Inferenza fallita: {exc}"


def main():
    parser = argparse.ArgumentParser(description="Verifica token HuggingFace per DELTA")
    parser.add_argument("--set", metavar="TOKEN", help="Imposta un nuovo token in .env")
    parser.add_argument("--interactive", action="store_true", help="Modalità interattiva guidata")
    parser.add_argument("--test-inference", action="store_true", help="Testa anche una chiamata di inferenza reale")
    args = parser.parse_args()

    print("\n=== DELTA — Verifica Token HuggingFace ===\n")

    # Aggiornamento diretto
    if args.set:
        token = args.set.strip()
        print(f"Verifica nuovo token: {token[:8]}...")
        ok, msg = validate_token(token)
        if ok:
            print(f"  ✓ {msg}")
            update_env_token(token)
            print("\n  Riavvia DELTA per applicare il nuovo token.\n")
        else:
            print(f"  ✗ {msg}")
            print(HELP_MSG)
            sys.exit(1)
        return

    # Modalità interattiva
    if args.interactive:
        print(HELP_MSG)
        token = input("Incolla il tuo token HuggingFace (hf_...): ").strip()
        if not token:
            print("Token vuoto. Uscita.")
            sys.exit(1)
        ok, msg = validate_token(token)
        if ok:
            print(f"\n  ✓ {msg}")
            update_env_token(token)
            print("\n  Riavvia DELTA per applicare il nuovo token.\n")
        else:
            print(f"\n  ✗ {msg}")
            print(HELP_MSG)
            sys.exit(1)
        return

    # Solo verifica del token attuale
    env = load_dotenv()
    # Carica anche da variabili d'ambiente di sistema
    token = os.environ.get("HF_API_TOKEN") or env.get("HF_API_TOKEN", "")

    if not token:
        print("  ✗ HF_API_TOKEN non configurato in .env\n")
        print(HELP_MSG)
        print(f"  Per aggiornare: python tools/hf_token_check.py --set hf_IL_TUO_TOKEN\n")
        sys.exit(1)

    print(f"  Token trovato: {token[:8]}...{token[-4:]}")
    print("  Verifica in corso...")
    ok, msg = validate_token(token)

    if ok:
        print(f"  ✓ {msg}")
        if args.test_inference:
            print("\n  Test inferenza in corso (può richiedere ~10s)...")
            ok2, msg2 = test_inference(token)
            if ok2:
                print(f"  ✓ {msg2}")
            else:
                print(f"  ✗ {msg2}")
                sys.exit(1)
        print()
    else:
        print(f"  ✗ {msg}")
        print(HELP_MSG)
        print(f"  Per aggiornare: python tools/hf_token_check.py --set hf_IL_TUO_TOKEN\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
