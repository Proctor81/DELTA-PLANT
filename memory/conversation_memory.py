# Gestione memoria conversazionale per utente — persistenza su disco (JSON)

import json
import logging
import time
from pathlib import Path

logger = logging.getLogger("delta.conversation_memory")

# Ogni turno di conversazione = 2 righe (Utente + DELTA).
# Manteniamo in disco le ultime MAX_STORED_TURNS coppie per utente.
MAX_STORED_TURNS = 20  # 40 righe totali per utente

# Se il file su disco è stato modificato da un'altra istanza più di questo numero
# di secondi dopo l'ultimo caricamento in cache, ricarica da disco.
_STALE_SECONDS = 5


class ConversationMemory:
    """Memoria conversazionale persistente.

    La storia di ogni utente viene salvata in:
        memory/sessions/<user_id>.json

    Il file viene caricato in RAM al primo accesso e scritto dopo ogni
    modifica.  Se il file su disco risulta più recente della cache RAM
    (per esempio perché un'altra istanza dell'engine ha scritto), la cache
    viene invalidata e il file viene riletto.
    """

    _SESSIONS_DIR = Path(__file__).parent / "sessions"

    def __init__(self):
        self._SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
        # Cache in RAM: { user_id: [righe] }
        self.sessions: dict = {}
        # Timestamp dell'ultimo caricamento da disco per ogni user_id
        self._loaded_at: dict = {}

    # ── Helpers interni ───────────────────────────────────────────────

    def _path(self, user_id: str) -> Path:
        # Sanitizza: usa solo caratteri sicuri per il nome file
        safe = "".join(c for c in str(user_id) if c.isalnum() or c in "_-")
        return self._SESSIONS_DIR / f"{safe}.json"

    def _is_stale(self, user_id: str) -> bool:
        """True se il file su disco è più recente della cache RAM."""
        p = self._path(user_id)
        if not p.exists():
            return False
        loaded_at = self._loaded_at.get(user_id, 0)
        try:
            return p.stat().st_mtime > loaded_at + _STALE_SECONDS
        except OSError:
            return False

    def _load(self, user_id: str) -> list:
        """Carica la storia dal disco se non già in cache (o se stale)."""
        if user_id in self.sessions and not self._is_stale(user_id):
            return self.sessions[user_id]
        p = self._path(user_id)
        if p.exists():
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    self.sessions[user_id] = data
                    self._loaded_at[user_id] = time.time()
                    return data
            except Exception as exc:
                logger.warning("ConversationMemory: errore lettura %s: %s", p, exc)
        self.sessions[user_id] = []
        self._loaded_at[user_id] = time.time()
        return self.sessions[user_id]

    def _save(self, user_id: str) -> None:
        """Scrive la storia corrente su disco."""
        p = self._path(user_id)
        try:
            p.write_text(
                json.dumps(self.sessions[user_id], ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            self._loaded_at[user_id] = time.time()
        except Exception as exc:
            logger.error("ConversationMemory: errore scrittura %s: %s", p, exc)

    def _trim(self, user_id: str) -> None:
        """Mantiene solo gli ultimi MAX_STORED_TURNS * 2 elementi."""
        lines = self.sessions[user_id]
        cap = MAX_STORED_TURNS * 2
        if len(lines) > cap:
            self.sessions[user_id] = lines[-cap:]

    # ── Interfaccia pubblica (compatibile con la versione precedente) ─

    def get_history(self, user_id: str) -> list:
        return list(self._load(str(user_id)))

    def append(self, user_id: str, user_input: str, response: str) -> None:
        uid = str(user_id)
        self._load(uid)
        self.sessions[uid].append(f"Utente: {user_input}")
        self.sessions[uid].append(f"DELTA: {response}")
        self._trim(uid)
        self._save(uid)

    def reset(self, user_id: str) -> None:
        uid = str(user_id)
        self.sessions[uid] = []
        self._save(uid)
