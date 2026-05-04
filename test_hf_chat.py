"""
DELTA - test_hf_chat.py
Script di test end-to-end per la chat intelligente con HuggingFace.
Verifica: token, modello disponibile, qualità risposta agronomica.

Uso:
    python test_hf_chat.py
    python test_hf_chat.py --verbose
    python test_hf_chat.py --token <nuovo_token>
"""

import sys
import os
import argparse
import time

# Aggiungi root progetto al path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Carica .env manualmente se presente
_ENV = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
if os.path.isfile(_ENV):
    with open(_ENV) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


def print_banner():
    print("=" * 60)
    print("  DELTA 2.0 — Test Chat Intelligente HuggingFace")
    print("=" * 60)


def test_token_validity(token: str) -> bool:
    """Verifica che il token HF sia valido."""
    print("\n[1/4] Verifica token HuggingFace...")
    try:
        import httpx
        r = httpx.get(
            "https://huggingface.co/api/whoami",
            headers={"Authorization": f"Bearer {token}"},
            timeout=15,
        )
        if r.status_code == 200:
            info = r.json()
            print(f"  ✓ Token valido - Utente: {info.get('name', 'N/A')}")
            return True
        else:
            print(f"  ✗ Token non valido (HTTP {r.status_code})")
            print(f"    Risposta: {r.text[:120]}")
            print()
            print("  SOLUZIONE: Crea un nuovo token su https://huggingface.co/settings/tokens")
            print("  Tipo richiesto: fine-grained con permesso 'Make calls to Inference Providers'")
            print("  Poi aggiorna HF_API_TOKEN nel file .env")
            return False
    except ImportError:
        print("  ✗ httpx non installato: pip install httpx")
        return False
    except Exception as e:
        print(f"  ✗ Errore rete: {e}")
        return False


def test_import():
    """Verifica che huggingface_hub sia installabile."""
    print("\n[2/4] Verifica dipendenze...")
    try:
        import huggingface_hub
        print(f"  ✓ huggingface_hub {huggingface_hub.__version__} disponibile")
        return True
    except ImportError:
        print("  ✗ huggingface_hub non installato")
        print("    Esegui: pip install huggingface_hub")
        return False


def test_model_selection(token: str, verbose: bool = False) -> str | None:
    """Testa la disponibilita del modello HF configurato."""
    print("\n[3/4] Verifica modello HF configurato...")
    from llm.huggingface_llm import HuggingFaceLLM, HF_MODEL_PRIORITY

    llm = HuggingFaceLLM(api_token=token, max_tokens=20)

    for model in HF_MODEL_PRIORITY:
        print(f"  → Probe {model}... ", end="", flush=True)
        t0 = time.time()
        if llm._probe_model(llm._get_client(), model):
            elapsed = time.time() - t0
            print(f"OK ({elapsed:.1f}s)")
            llm._active_model = model
            return model
        else:
            elapsed = time.time() - t0
            print(f"non disponibile ({elapsed:.1f}s)")

    print("  ✗ Nessun modello disponibile")
    return None


def test_chat_quality(token: str, model: str, verbose: bool = False) -> bool:
    """Testa la qualità della risposta agronomica."""
    print(f"\n[4/4] Test risposta agronomica con {model}...")
    from llm.huggingface_llm import HuggingFaceLLM

    llm = HuggingFaceLLM(
        api_token=token,
        model_name=model,
        max_tokens=200,
        temperature=0.65,
    )
    llm._active_model = model

    test_questions = [
        (
            "Cosa è la peronospora della vite e come si tratta?",
            ["peronospora", "plasmopara", "rame", "fungo", "vite"],
        ),
        (
            "Una pianta mostra foglie gialle con nervature verdi. Che problema potrebbe avere?",
            ["clorosi", "ferro", "carenza", "ph", "nutrizione"],
        ),
        (
            "Ho rilevato oidio su pomodoro con confidenza 87%. Cosa devo fare?",
            ["oidio", "zolfo", "trattamento", "fungicida", "leveillula"],
        ),
    ]

    passed = 0
    for i, (question, expected_keywords) in enumerate(test_questions, 1):
        print(f"\n  Domanda {i}: {question[:70]}...")
        t0 = time.time()
        response, model_used = llm.chat(question)
        elapsed = time.time() - t0

        if verbose:
            print(f"  Risposta ({elapsed:.1f}s, {len(response)} chars):")
            print(f"  {response[:300]}")
        else:
            print(f"  Risposta ({elapsed:.1f}s, {len(response)} chars): {response[:100]}...")

        # Controlla che la risposta sia in italiano e contenga keyword pertinenti
        response_lower = response.lower()
        found_keywords = [k for k in expected_keywords if k in response_lower]
        is_italian = any(w in response_lower for w in [" è ", " un ", " la ", " il ", " le ", " di ", " per "])

        if len(response) > 50 and is_italian and len(found_keywords) >= 1:
            print(f"  ✓ Risposta pertinente (keyword trovate: {found_keywords})")
            passed += 1
        else:
            print(f"  ⚠ Risposta generica/non pertinente")
            if verbose:
                print(f"    Keyword attese: {expected_keywords}")
                print(f"    Trovate: {found_keywords}, italiano: {is_italian}")

    print(f"\n  Risultato: {passed}/{len(test_questions)} test superati")
    return passed >= 2


def test_chat_engine_integration() -> bool:
    """Testa l'integrazione completa con ChatEngine."""
    print("\n[BONUS] Test integrazione ChatEngine...")
    try:
        from chat.chat_engine import ChatEngine
        engine = ChatEngine()

        # Test reset
        engine.reset("test_user")

        # Verifica status
        status = engine.get_status()
        print(f"  ChatEngine status: {status}")

        hf_ok = status.get("hf_token_present", False)
        model = status.get("hf_active_model", "N/A")
        print(f"  Token HF presente: {hf_ok}")
        print(f"  Modello HF attivo: {model}")
        print("  ✓ ChatEngine caricato correttamente")
        return True
    except Exception as e:
        print(f"  ✗ Errore ChatEngine: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Test Chat Intelligente DELTA")
    parser.add_argument("--verbose", "-v", action="store_true", help="Output dettagliato")
    parser.add_argument("--token", help="Override token HF (default: da .env)")
    parser.add_argument("--skip-model-test", action="store_true",
                        help="Salta il test del modello (solo verifica token/import)")
    args = parser.parse_args()

    print_banner()

    token = args.token or os.environ.get("HF_API_TOKEN", "")
    if not token:
        print("\n⚠ HF_API_TOKEN non trovato nel .env")
        print("  Aggiungi: HF_API_TOKEN=hf_xxx al file .env")
        sys.exit(1)

    print(f"\nToken: {token[:8]}...{token[-4:]}")
    print(f"Modello target: {os.environ.get('HF_MODEL_NAME', 'meta-llama/Llama-3.1-8B-Instruct')}")

    results = {}

    # Test 1: Dipendenze
    results["import"] = test_import()
    if not results["import"]:
        print("\n⚠ Installa le dipendenze: pip install huggingface_hub httpx")
        sys.exit(1)

    # Test 2: Token
    results["token"] = test_token_validity(token)
    if not results["token"]:
        print("\n" + "=" * 60)
        print("AZIONE RICHIESTA: Il token HF non è valido.")
        print("1. Vai su https://huggingface.co/settings/tokens")
        print("2. Crea un nuovo token fine-grained con permesso:")
        print("   'Make calls to Inference Providers'")
        print("3. Aggiorna HF_API_TOKEN nel file .env")
        print("=" * 60)
        # Testa comunque l'integrazione ChatEngine (struttura codice)
        test_chat_engine_integration()
        sys.exit(1)

    if args.skip_model_test:
        print("\n✓ Skip test modello richiesto")
        test_chat_engine_integration()
        sys.exit(0)

    # Test 3: Selezione modello
    model = test_model_selection(token, args.verbose)
    results["model"] = model is not None
    if not model:
        print("\n⚠ Nessun modello HF disponibile con il tuo piano/token.")
        print("  Verifica i modelli disponibili su: https://huggingface.co/models")
        sys.exit(1)

    # Test 4: Qualità chat
    results["quality"] = test_chat_quality(token, model, args.verbose)

    # Test bonus: Integrazione ChatEngine
    results["integration"] = test_chat_engine_integration()

    # ── Riepilogo ─────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("  RIEPILOGO TEST")
    print("=" * 60)
    for test_name, passed in results.items():
        status = "✓" if passed else "✗"
        print(f"  {status} {test_name}")

    all_passed = all(results.values())
    if all_passed:
        print(f"\n✅ DELTA chat intelligente operativa con modello: {model}")
    else:
        failed = [k for k, v in results.items() if not v]
        print(f"\n⚠ Test falliti: {', '.join(failed)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
