"""
DELTA - Entry point principale.
Questo file avvia il sistema DELTA Plant modulare.
L'intero progetto è organizzato nella directory DELTA/ con architettura modulare.

Per avviare: python main.py
"""

import sys
import os

# Assicura che la root del progetto sia nel path
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
	sys.path.insert(0, PROJECT_ROOT)

from main import main

if __name__ == "__main__":
	main()
