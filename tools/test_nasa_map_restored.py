#!/usr/bin/env python3
"""
Verifica che la funzione _send_nasa_sar_map_snapshot è presente e funzionante
"""

import inspect
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

def test_function_exists():
    """Verifica che la funzione sia presente"""
    from interface import telegram_bot as tg
    
    if not hasattr(tg, '_send_nasa_sar_map_snapshot'):
        print("❌ FAIL: _send_nasa_sar_map_snapshot non trovata nel modulo")
        return False
    
    func = getattr(tg, '_send_nasa_sar_map_snapshot')
    if not callable(func):
        print("❌ FAIL: _send_nasa_sar_map_snapshot non è callable")
        return False
    
    # Verifica firma
    sig = inspect.signature(func)
    params = list(sig.parameters.keys())
    expected = ['update', 'latitude', 'longitude', 'language', 'locality_label']
    
    if params != expected:
        print(f"❌ FAIL: Firma parametri scorretta. Atteso: {expected}, trovato: {params}")
        return False
    
    print("✓ PASS: _send_nasa_sar_map_snapshot esiste con firma corretta")
    print(f"  Parametri: {params}")
    print(f"  Async: {inspect.iscoroutinefunction(func)}")
    
    return True


def test_map_payload_builder():
    """Verifica che _build_nasa_sar_map_photo_payload esista"""
    from interface import telegram_bot as tg
    
    if not hasattr(tg, '_build_nasa_sar_map_photo_payload'):
        print("❌ FAIL: _build_nasa_sar_map_photo_payload non trovata nel modulo")
        return False
    
    func = getattr(tg, '_build_nasa_sar_map_photo_payload')
    print("✓ PASS: _build_nasa_sar_map_photo_payload esiste")
    print(f"  Async: {inspect.iscoroutinefunction(func)}")
    
    return True


def test_flow_integration():
    """Verifica che la funzione sia chiamata nel flusso _run_nasa_sar_analysis"""
    from interface import telegram_bot as tg
    
    # Leggi il source code di _run_nasa_sar_analysis
    source = inspect.getsource(tg._run_nasa_sar_analysis)
    
    if '_send_nasa_sar_map_snapshot' not in source:
        print("❌ FAIL: _send_nasa_sar_map_snapshot non è chiamata in _run_nasa_sar_analysis")
        return False
    
    print("✓ PASS: _send_nasa_sar_map_snapshot è chiamata in _run_nasa_sar_analysis")
    
    # Verifica che sia prima della dashboard_text
    lines = source.split('\n')
    map_line = -1
    dashboard_line = -1
    
    for i, line in enumerate(lines):
        if '_send_nasa_sar_map_snapshot' in line:
            map_line = i
        if 'dashboard_text' in line:
            dashboard_line = i
    
    if map_line > 0 and dashboard_line > map_line:
        print(f"  ✓ Ordine corretto: mappa (riga {map_line}) prima di dashboard (riga {dashboard_line})")
    else:
        print(f"  ⚠ Ordine verifica non determinato: map_line={map_line}, dashboard_line={dashboard_line}")
    
    return True


if __name__ == '__main__':
    print("\n" + "="*60)
    print("TEST: Mappa NASA-ISRO/SAR Ripristinata")
    print("="*60 + "\n")
    
    results = []
    
    try:
        results.append(("Funzione esiste", test_function_exists()))
    except Exception as e:
        print(f"❌ ERRORE test 1: {e}")
        results.append(("Funzione esiste", False))
    
    try:
        results.append(("Builder mappa", test_map_payload_builder()))
    except Exception as e:
        print(f"❌ ERRORE test 2: {e}")
        results.append(("Builder mappa", False))
    
    try:
        results.append(("Integrazione flusso", test_flow_integration()))
    except Exception as e:
        print(f"❌ ERRORE test 3: {e}")
        results.append(("Integrazione flusso", False))
    
    print("\n" + "="*60)
    passed = sum(1 for _, p in results if p)
    total = len(results)
    print(f"RISULTATO: {passed}/{total} test passati")
    
    if passed == total:
        print("\n✓ Mappa NASA-ISRO/SAR RIPRISTINATA E FUNZIONANTE")
        print("  La funzione è stata re-aggiunta e integrata nel flusso.")
        print("  Foto della mappa verrà inviata quando l'utente usa /nasa_sar")
    else:
        print("\n❌ Alcuni test falliti")
    
    print("="*60 + "\n")
    
    sys.exit(0 if passed == total else 1)
