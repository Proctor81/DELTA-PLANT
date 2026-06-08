"""
DELTA - interface/admin.py
Pannello Amministratore DELTA — accesso protetto da password.
Funzionalità: cambio password, log di sistema, statistiche DB,
configurazione, backup, reset Academy.
"""

import json
import logging
import os
import shutil
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import TYPE_CHECKING

import requests
from jose import jwt

if TYPE_CHECKING:
    from core.agent import DeltaAgent

logger = logging.getLogger("delta.interface.admin")

BOLD   = "\033[1m"
DIM    = "\033[2m"
GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
BLUE   = "\033[94m"
RESET  = "\033[0m"

_ROOT = Path(__file__).resolve().parent.parent


class AdminPanel:
    """Pannello di controllo amministratore DELTA."""

    def __init__(self, agent: "DeltaAgent"):
        self.agent = agent
        self._admin_authenticated = False

    # ── Autenticazione ─────────────────────────────────────────

    def authenticate(self) -> bool:
        """Richiede e verifica la password di amministratore."""
        from core.auth import verify_password
        import getpass
        print(f"\n{BOLD}─── ACCESSO AMMINISTRATORE ───{RESET}")
        print(f"{DIM}Inserire la password per continuare.{RESET}")
        try:
            pw = getpass.getpass("Password: ")
        except (KeyboardInterrupt, EOFError):
            print()
            self._admin_authenticated = False
            return False
        if verify_password(pw):
            print(f"{GREEN}✔ Accesso autorizzato.{RESET}")
            logger.info("Accesso admin riuscito.")
            self._admin_authenticated = True
            return True
        print(f"{RED}✘ Password errata. Accesso negato.{RESET}")
        logger.warning("Tentativo di accesso admin FALLITO.")
        self._admin_authenticated = False
        return False

    # ── Menu principale ────────────────────────────────────────

    def run(self):
        """Avvia il pannello (richiede autenticazione preventiva)."""
        if not self.authenticate():
            return

        while True:
            self._header()
            print(f"  {BOLD}[1]{RESET} Cambia password amministratore")
            print(f"  {BOLD}[2]{RESET} Visualizza ultimi log di sistema")
            print(f"  {BOLD}[3]{RESET} Statistiche database")
            print(f"  {BOLD}[4]{RESET} Configurazione sistema")
            print(f"  {BOLD}[5]{RESET} Backup database")
            print(f"  {BOLD}[6]{RESET} Reset progressi Academy")
            print(f"  {BOLD}[7]{RESET} {BLUE}Pubblica su GitHub{RESET}     (README, RELEASE, tag, push)")
            print(f"  {BOLD}[8]{RESET} Scientists Telegram (autorizzazioni)")
            print(f"  {BOLD}[9]{RESET} {YELLOW}Programmazione orario avvio/uscita{RESET} (cron)")
            print(f"  {BOLD}[10]{RESET} {CYAN}Statistiche inferenza DELTAPLANO_bot{RESET}")
            print(f"  {BOLD}[11]{RESET} {CYAN}Monitor visitatori deltaplant.ai{RESET}")
            print(f"  {BOLD}[0]{RESET} Esci dal pannello")

            scelta = input(f"\n{BOLD}> Scelta: {RESET}").strip()

            if scelta == "1":
                self._change_password()
            elif scelta == "2":
                self._view_logs()
            elif scelta == "3":
                self._db_stats()
            elif scelta == "4":
                self._show_config()
            elif scelta == "5":
                self._backup_db()
            elif scelta == "6":
                self._reset_academy()
            elif scelta == "7":
                self._publish_github()
            elif scelta == "8":
                self._manage_scientists()
            elif scelta == "9":
                self._schedule_manager()
            elif scelta == "10":
                self._bot_inference_stats()
            elif scelta == "11":
                self._website_visitor_monitor()
            elif scelta == "0":
                print(f"{DIM}Uscita dal pannello amministratore.{RESET}")
                break
            else:
                print(f"⚠ Scelta non valida.")

    # ── Cambio password ────────────────────────────────────────

    def _change_password(self):
        from core.auth import change_password
        import getpass
        print(f"\n{BOLD}─── CAMBIO PASSWORD ───{RESET}")
        try:
            old     = getpass.getpass("Password corrente: ")
            new     = getpass.getpass("Nuova password (min. 8 caratteri): ")
            confirm = getpass.getpass("Conferma nuova password: ")
        except (KeyboardInterrupt, EOFError):
            print()
            return
        if new != confirm:
            print(f"{RED}✘ Le password non coincidono.{RESET}")
            return
        ok, msg = change_password(old, new)
        if ok:
            print(f"{GREEN}✔ {msg}{RESET}")
            logger.info("Password amministratore cambiata.")
        else:
            print(f"{RED}✘ {msg}{RESET}")

    # ── Log ────────────────────────────────────────────────────

    def _view_logs(self):
        print(f"\n{BOLD}─── ULTIMI LOG DI SISTEMA (50 righe) ───{RESET}")
        log_dir = _ROOT / "logs"
        logs = sorted(log_dir.glob("*.log"), reverse=True) if log_dir.exists() else []
        if not logs:
            print(f"{DIM}Nessun file di log trovato in logs/.{RESET}")
            return
        lf = logs[0]
        print(f"{DIM}File: {lf.name}{RESET}\n")
        try:
            lines = lf.read_text(encoding="utf-8").splitlines()
            for line in lines[-50:]:
                print(line)
        except Exception as exc:
            print(f"Errore lettura log: {exc}")

    # ── Statistiche DB ─────────────────────────────────────────

    def _db_stats(self):
        import sqlite3
        print(f"\n{BOLD}─── STATISTICHE DATABASE ───{RESET}")
        db_path = _ROOT / "delta.db"
        if not db_path.exists():
            print(f"{DIM}Database non trovato.{RESET}")
            return
        try:
            con = sqlite3.connect(str(db_path))
            cur = con.cursor()
            cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
            for (tbl,) in cur.fetchall():
                cur.execute(f"SELECT COUNT(*) FROM [{tbl}]")
                cnt = cur.fetchone()[0]
                print(f"  • {tbl:<35} {cnt:>6} record")
            con.close()
        except Exception as exc:
            print(f"Errore accesso DB: {exc}")

    # ── Configurazione ─────────────────────────────────────────

    def _show_config(self):
        print(f"\n{BOLD}─── CONFIGURAZIONE SISTEMA ───{RESET}")
        try:
            from core.config import (
                MODEL_CONFIG, SENSOR_CONFIG, VISION_CONFIG,
                QUANTUM_CONFIG, API_CONFIG, TELEGRAM_CONFIG,
            )
            sections = {
                "Modello AI":     MODEL_CONFIG,
                "Sensori":        SENSOR_CONFIG,
                "Visione/Camera": VISION_CONFIG,
                "Quantum Oracle": QUANTUM_CONFIG,
                "API":            API_CONFIG,
                "Telegram":       TELEGRAM_CONFIG,
            }
            for name, cfg in sections.items():
                print(f"\n  {CYAN}{BOLD}{name}{RESET}")
                for k, v in cfg.items():
                    print(f"    {k:<32}: {v}")
        except Exception as exc:
            print(f"Errore lettura configurazione: {exc}")

    # ── Backup DB ──────────────────────────────────────────────

    def _backup_db(self):
        print(f"\n{BOLD}─── BACKUP DATABASE ───{RESET}")
        db_path = _ROOT / "delta.db"
        if not db_path.exists():
            print(f"{DIM}Database non trovato.{RESET}")
            return
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_dir = _ROOT / "exports"
        backup_dir.mkdir(exist_ok=True)
        dest = backup_dir / f"delta_backup_{ts}.db"
        shutil.copy2(db_path, dest)
        print(f"{GREEN}✔ Backup salvato: {dest.name}{RESET}")
        logger.info("Backup DB creato: %s", dest)

    # ── Reset Academy ──────────────────────────────────────────

    def _reset_academy(self):
        print(f"\n{BOLD}─── RESET PROGRESSI ACADEMY ───{RESET}")
        confirm = input(
            f"{YELLOW}⚠ Azzerare tutti i progressi Academy? [s/N]: {RESET}"
        ).strip().lower()
        if confirm != "s":
            print("Operazione annullata.")
            return
        pf = _ROOT / "data" / "academy_progress.json"
        if pf.exists():
            pf.unlink()
            print(f"{GREEN}✔ Progressi Academy azzerati.{RESET}")
            logger.info("Progressi Academy resettati dall'amministratore.")
        else:
            print(f"{DIM}Nessun file di progressi trovato.{RESET}")

    # ── Pubblicazione GitHub ────────────────────────────────────

    def _publish_github(self):
        """Avvia il wizard di pubblicazione automatica su GitHub."""
        try:
            from interface.github_publisher import GitHubPublisher
        except ImportError as exc:
            print(f"{RED}✘ Modulo github_publisher non disponibile: {exc}{RESET}")
            logger.error("GitHubPublisher import error: %s", exc)
            return
        try:
            publisher = GitHubPublisher()
            publisher.run()
        except Exception as exc:
            print(f"{RED}✘ Errore durante la pubblicazione: {exc}{RESET}")
            logger.error("Errore GitHubPublisher.run(): %s", exc, exc_info=True)

    # ── Scientists Telegram ────────────────────────────────────

    def _manage_scientists(self):
        """Gestione autorizzazioni Telegram (nicknames)."""
        while True:
            self._header()
            print(f"{BOLD}─── SCIENTISTS TELEGRAM ───{RESET}")
            scientists = self._load_scientists()
            if scientists:
                for idx, name in enumerate(scientists, start=1):
                    print(f"  {idx:>2}. {name}")
            else:
                print(f"{DIM}Nessun nickname autorizzato.{RESET}")

            print(f"\n  {BOLD}[1]{RESET} Aggiungi nickname")
            print(f"  {BOLD}[2]{RESET} Rimuovi nickname")
            print(f"  {BOLD}[3]{RESET} Svuota lista")
            print(f"  {BOLD}[4]{RESET} Mostra accessi negati recenti")
            print(f"  {BOLD}[5]{RESET} Aggiungi utenti bloccati recenti")
            print(f"  {BOLD}[0]{RESET} Indietro")

            scelta = input(f"\n{BOLD}> Scelta: {RESET}").strip()
            if scelta == "1":
                nickname = input("Nickname Telegram (es: @utente): ").strip()
                self._add_scientist(nickname)
            elif scelta == "2":
                nickname = input("Nickname da rimuovere: ").strip()
                self._remove_scientist(nickname)
            elif scelta == "3":
                confirm = input(f"{YELLOW}⚠ Svuotare la lista? [s/N]: {RESET}").strip().lower()
                if confirm == "s":
                    self._save_scientists([])
                    print(f"{GREEN}✔ Lista scientists svuotata.{RESET}")
            elif scelta == "4":
                self._show_denied_log()
            elif scelta == "5":
                self._add_denied_users()
            elif scelta == "0":
                return
            else:
                print("⚠ Scelta non valida.")

    def _show_denied_log(self, max_lines: int = 20):
        """Mostra ultimi accessi negati dal log."""
        log_path = _ROOT / "logs" / "telegram_denied.log"
        if not log_path.exists():
            print(f"{DIM}Nessun accesso negato registrato.{RESET}")
            return
        try:
            lines = log_path.read_text(encoding="utf-8").splitlines()
            print(f"\n{BOLD}Ultimi accessi negati:{RESET}")
            for line in lines[-max_lines:]:
                print(f"  {line}")
        except Exception as exc:
            print(f"{YELLOW}⚠ Errore lettura denied log: {exc}{RESET}")

    def _add_denied_users(self):
        """Permette di aggiungere rapidamente utenti bloccati dal log agli autorizzati."""
        log_path = _ROOT / "logs" / "telegram_denied.log"
        if not log_path.exists():
            print(f"{DIM}Nessun accesso negato registrato.{RESET}")
            return
        try:
            lines = log_path.read_text(encoding="utf-8").splitlines()
            denied = []
            for line in lines[-30:]:
                # Cerca USERNAME: @nome
                if "USERNAME:" in line:
                    username = line.split("USERNAME:", 1)[-1].strip()
                    if username and username != "None":
                        denied.append(username)
            denied = sorted(set(denied))
            if not denied:
                print(f"{DIM}Nessun username trovato nel log.{RESET}")
                return
            print(f"\n{BOLD}Utenti bloccati trovati:{RESET}")
            for idx, name in enumerate(denied, 1):
                print(f"  {idx:>2}. {name}")
            to_add = input(f"\n{BOLD}Aggiungi tutti questi utenti agli autorizzati? [s/N]: {RESET}").strip().lower()
            if to_add == "s":
                names = self._load_scientists()
                for name in denied:
                    if name not in names:
                        names.append(name)
                self._save_scientists(names)
                print(f"{GREEN}✔ Utenti aggiunti.{RESET}")
            else:
                print("Operazione annullata.")
        except Exception as exc:
            print(f"{YELLOW}⚠ Errore aggiunta denied users: {exc}{RESET}")

    @staticmethod
    def _normalize_username(value: str) -> str:
        raw = value.strip()
        if not raw:
            return ""
        if not raw.startswith("@"):
            raw = f"@{raw}"
        return raw.lower()

    def _scientists_path(self) -> Path:
        try:
            from core.config import TELEGRAM_CONFIG
            path = TELEGRAM_CONFIG.get("authorized_usernames_file")
            if path:
                return Path(path)
        except Exception:
            pass
        return _ROOT / "data" / "telegram_scientists.local.json"

    def _load_scientists(self) -> list[str]:
        path = self._scientists_path()
        if not path.exists():
            return []
        try:
            data = path.read_text(encoding="utf-8")
            names = []
            for value in json.loads(data):
                if isinstance(value, str):
                    norm = self._normalize_username(value)
                    if norm:
                        names.append(norm)
            return sorted(set(names))
        except Exception as exc:
            print(f"{YELLOW}⚠ Errore lettura scientists: {exc}{RESET}")
            return []

    def _save_scientists(self, names: list[str]) -> None:
        path = self._scientists_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = sorted(set(self._normalize_username(n) for n in names if n))
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def _add_scientist(self, nickname: str):
        norm = self._normalize_username(nickname)
        if not norm:
            print(f"{YELLOW}⚠ Nickname non valido.{RESET}")
            return
        names = self._load_scientists()
        if norm in names:
            print(f"{DIM}Nickname già presente.{RESET}")
            return
        names.append(norm)
        self._save_scientists(names)
        print(f"{GREEN}✔ Aggiunto {norm}.{RESET}")

    def _remove_scientist(self, nickname: str):
        norm = self._normalize_username(nickname)
        if not norm:
            print(f"{YELLOW}⚠ Nickname non valido.{RESET}")
            return
        names = self._load_scientists()
        if norm not in names:
            print(f"{DIM}Nickname non trovato.{RESET}")
            return
        names = [n for n in names if n != norm]
        self._save_scientists(names)
        print(f"{GREEN}✔ Rimosso {norm}.{RESET}")

    # ── Programmazione orario (cron) ────────────────────────────

    _CRON_TAG_START = "# DELTA_SCHEDULE_START"
    _CRON_TAG_STOP  = "# DELTA_SCHEDULE_STOP"

    def _schedule_manager(self):
        """Gestione programmazione orario avvio/uscita DELTA tramite crontab."""
        import subprocess
        import shutil

        if not shutil.which("crontab"):
            print(f"\n{RED}✘ 'crontab' non trovato nel sistema. Necessario su Raspberry Pi.{RESET}")
            input(f"{DIM}Premere Invio per tornare...{RESET}")
            return

        while True:
            self._header()
            print(f"{BOLD}─── PROGRAMMAZIONE ORARIO AVVIO/USCITA ───{RESET}")

            start_entry, stop_entry = self._cron_read_delta_entries()

            print(f"\n  {CYAN}Avvio  DELTA:{RESET} ", end="")
            if start_entry:
                print(f"{GREEN}{self._cron_entry_to_human(start_entry)}{RESET}")
            else:
                print(f"{DIM}non programmato{RESET}")

            print(f"  {CYAN}Uscita DELTA:{RESET} ", end="")
            if stop_entry:
                print(f"{GREEN}{self._cron_entry_to_human(stop_entry)}{RESET}")
            else:
                print(f"{DIM}non programmata{RESET}")

            print(f"\n  {BOLD}[1]{RESET} Imposta orario di avvio")
            print(f"  {BOLD}[2]{RESET} Imposta orario di uscita")
            print(f"  {BOLD}[3]{RESET} Rimuovi programmazione avvio")
            print(f"  {BOLD}[4]{RESET} Rimuovi programmazione uscita")
            print(f"  {BOLD}[5]{RESET} Rimuovi tutta la programmazione")
            print(f"  {BOLD}[0]{RESET} Indietro")

            scelta = input(f"\n{BOLD}> Scelta: {RESET}").strip()

            if scelta == "1":
                orario = self._ask_time("Orario di avvio DELTA")
                if orario:
                    self._cron_set_entry("start", orario)
                    print(f"{GREEN}✔ Avvio programmato alle {orario}.{RESET}")
                    logger.info("Cron avvio DELTA impostato: %s", orario)
            elif scelta == "2":
                orario = self._ask_time("Orario di uscita DELTA")
                if orario:
                    self._cron_set_entry("stop", orario)
                    print(f"{GREEN}✔ Uscita programmata alle {orario}.{RESET}")
                    logger.info("Cron uscita DELTA impostato: %s", orario)
            elif scelta == "3":
                self._cron_remove_entry("start")
                print(f"{GREEN}✔ Programmazione avvio rimossa.{RESET}")
                logger.info("Cron avvio DELTA rimosso.")
            elif scelta == "4":
                self._cron_remove_entry("stop")
                print(f"{GREEN}✔ Programmazione uscita rimossa.{RESET}")
                logger.info("Cron uscita DELTA rimosso.")
            elif scelta == "5":
                confirm = input(
                    f"{YELLOW}⚠ Rimuovere tutta la programmazione DELTA? [s/N]: {RESET}"
                ).strip().lower()
                if confirm == "s":
                    self._cron_remove_entry("start")
                    self._cron_remove_entry("stop")
                    print(f"{GREEN}✔ Programmazione rimossa completamente.{RESET}")
                    logger.info("Cron DELTA rimosso completamente.")
            elif scelta == "0":
                return
            else:
                print("⚠ Scelta non valida.")

    @staticmethod
    def _ask_time(label: str) -> str | None:
        """Chiede un orario HH:MM all'utente, restituisce None se non valido."""
        raw = input(f"{BOLD}{label} (HH:MM, 24h): {RESET}").strip()
        parts = raw.split(":")
        if len(parts) != 2:
            print(f"{RED}✘ Formato non valido. Usare HH:MM (es: 07:30).{RESET}")
            return None
        try:
            hh, mm = int(parts[0]), int(parts[1])
            if not (0 <= hh <= 23 and 0 <= mm <= 59):
                raise ValueError
        except ValueError:
            print(f"{RED}✘ Orario fuori range (0-23 ore, 0-59 minuti).{RESET}")
            return None
        return f"{hh:02d}:{mm:02d}"

    @staticmethod
    def _cron_entry_to_human(line: str) -> str:
        """Converte una riga cron in testo leggibile (es: 07:30 ogni giorno)."""
        parts = line.split()
        if len(parts) < 5:
            return line
        mm, hh = parts[0], parts[1]
        try:
            return f"{int(hh):02d}:{int(mm):02d} ogni giorno"
        except ValueError:
            return line

    def _cron_read_raw(self) -> list[str]:
        """Legge il crontab corrente dell'utente."""
        import subprocess
        try:
            result = subprocess.run(
                ["crontab", "-l"],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                return result.stdout.splitlines()
            # returncode 1 = nessun crontab, non è un errore
            return []
        except Exception as exc:
            logger.warning("Errore lettura crontab: %s", exc)
            return []

    def _cron_write_raw(self, lines: list[str]) -> bool:
        """Scrive il crontab dell'utente."""
        import subprocess
        content = "\n".join(lines)
        if content and not content.endswith("\n"):
            content += "\n"
        try:
            proc = subprocess.run(
                ["crontab", "-"],
                input=content, capture_output=True, text=True, timeout=5
            )
            return proc.returncode == 0
        except Exception as exc:
            logger.error("Errore scrittura crontab: %s", exc)
            return False

    def _cron_read_delta_entries(self) -> tuple[str | None, str | None]:
        """Restituisce (riga_start, riga_stop) o None se non presenti."""
        lines = self._cron_read_raw()
        start = stop = None
        for i, line in enumerate(lines):
            if line.strip() == self._CRON_TAG_START and i + 1 < len(lines):
                start = lines[i + 1].strip()
            elif line.strip() == self._CRON_TAG_STOP and i + 1 < len(lines):
                stop = lines[i + 1].strip()
        return start, stop

    def _cron_remove_entry(self, kind: str) -> None:
        """Rimuove la entry DELTA (start o stop) dal crontab."""
        tag = self._CRON_TAG_START if kind == "start" else self._CRON_TAG_STOP
        lines = self._cron_read_raw()
        cleaned: list[str] = []
        skip_next = False
        for line in lines:
            if skip_next:
                skip_next = False
                continue
            if line.strip() == tag:
                skip_next = True
                continue
            cleaned.append(line)
        self._cron_write_raw(cleaned)

    def _cron_set_entry(self, kind: str, orario: str) -> None:
        """Aggiunge o aggiorna la entry DELTA (start o stop) nel crontab."""
        hh, mm = orario.split(":")
        tag = self._CRON_TAG_START if kind == "start" else self._CRON_TAG_STOP
        python_bin = str(_ROOT / ".venv" / "bin" / "python")
        main_py    = str(_ROOT / "main.py")

        if kind == "start":
            cmd = f"{mm} {hh} * * * cd {_ROOT!s} && {python_bin} {main_py}"
        else:
            # Termina DELTA cercando il processo per percorso main.py
            cmd = f"{mm} {hh} * * * pkill -f '{main_py}'"

        # Rimuovi eventuale entry precedente dello stesso tipo
        self._cron_remove_entry(kind)

        # Aggiungi la nuova entry con tag identificativo
        lines = self._cron_read_raw()
        lines.extend([tag, cmd])
        self._cron_write_raw(lines)

    # ── Statistiche inferenza DELTAPLANO_bot ───────────────────

    def _bot_inference_stats(self):
        """Mostra statistiche di utilizzo dell'inferenza LLM per utente autorizzato.

        - Parsa logs/delta.log per le righe di delta.deltaplano_bot e delta.chat_engine
        - Conta richieste/risposte per user_id e errori HF
        - Risolve user_id -> @username via data/telegram_user_map.json
        - Stampa tabella per utente autorizzato + istogramma ASCII complessivo
        """
        import re

        print(f"\n{BOLD}─── STATISTICHE INFERENZA DELTAPLANO_bot ───{RESET}")

        log_files = self._bot_inference_log_files()
        if not log_files:
            print(f"{DIM}Nessun log disponibile in logs/.{RESET}")
            return

        # Mappa user_id -> @username (popolata da _guard nel bot Telegram)
        map_path = _ROOT / "data" / "telegram_user_map.json"
        id_to_username: dict = {}
        if map_path.exists():
            try:
                raw = json.loads(map_path.read_text(encoding="utf-8")) or {}
                for uid, entry in raw.items():
                    uname = (entry or {}).get("username", "")
                    if uname:
                        id_to_username[str(uid)] = "@" + uname.lstrip("@").lower()
            except Exception as exc:
                print(f"{YELLOW}⚠ Impossibile leggere {map_path.name}: {exc}{RESET}")

        # Lista usernames autorizzati
        scientists_path = self._scientists_path()
        authorized: list = []
        if scientists_path.exists():
            try:
                raw = json.loads(scientists_path.read_text(encoding="utf-8")) or []
                authorized = [str(u).lstrip("@").lower() for u in raw if u]
            except Exception:
                authorized = []
        if not authorized:
            print(f"{YELLOW}⚠ Nessun username autorizzato in {scientists_path.name}.{RESET}")

        parse_result = self._collect_bot_inference_log_stats(log_files)
        stats = parse_result["stats"]
        total_hf_chars = parse_result["total_hf_chars"]
        total_hf_calls = parse_result["total_hf_calls"]
        total_hf_errors = parse_result["total_hf_errors"]
        duplicate_lines_skipped = parse_result["duplicate_lines_skipped"]
        synthetic_lines_skipped = parse_result["synthetic_lines_skipped"]

        print(
            f"{DIM}Log analizzati: {len(log_files)}  "
            f"duplicati ignorati={duplicate_lines_skipped}  "
            f"righe sintetiche ignorate={synthetic_lines_skipped}{RESET}"
        )

        # Costruisci righe per utente autorizzato
        # Mappa username -> user_id inverso, con normalizzazione (rimuove _ . -)
        # per tollerare differenze di scrittura (es. paolo_81_paolo vs paolo81paolo)
        def _norm_uname(u: str) -> str:
            return re.sub(r"[._\-]", "", (u or "").lstrip("@").lower())

        # Mappe: forma normalizzata -> uid e -> username originale dal log
        norm_to_uid: dict = {}
        norm_to_logname: dict = {}
        for uid, uname in id_to_username.items():
            n = _norm_uname(uname)
            if n:
                norm_to_uid[n] = uid
                norm_to_logname[n] = uname.lstrip("@").lower()

        # Set degli autorizzati (forma normalizzata) per il check successivo
        authorized_norm = {_norm_uname(u) for u in authorized}

        rows = []
        matched_uids: set = set()
        for uname in authorized:
            n = _norm_uname(uname)
            uid = norm_to_uid.get(n, "")
            s = stats.get(uid, None) if uid else None
            if uid:
                matched_uids.add(uid)
            rows.append({
                "username": "@" + uname,
                "user_id":  uid or "—",
                "requests": s["requests"] if s else 0,
                "errors":   s["errors"] if s else 0,
                "models":   ", ".join(sorted(s["models"])) if s and s["models"] else "—",
                "first":    s["first"] if s and s["first"] else "—",
                "last":     s["last"] if s and s["last"] else "—",
            })

        # Utenti non autorizzati che hanno comunque attività
        # (riconosciuti via mapping ma non in scientists, oppure user_id senza mapping)
        extra_rows = []
        for uid, s in stats.items():
            if uid in matched_uids:
                continue
            uname = id_to_username.get(uid, "")
            n = _norm_uname(uname)
            if n and n in authorized_norm:
                # protezione extra: già coperto da rows ma non era nel matched_uids
                continue
            extra_rows.append({
                "username": uname or "(sconosciuto)",
                "user_id":  uid,
                "requests": s["requests"],
                "errors":   s["errors"],
                "models":   ", ".join(sorted(s["models"])) if s["models"] else "—",
                "first":    s["first"] or "—",
                "last":     s["last"] or "—",
            })

        # Tabella per utente autorizzato
        print(f"\n{BOLD}Per singolo utente autorizzato:{RESET}")
        col_w_user = max([len(r["username"]) for r in rows] + [len("username")])
        col_w_id   = max([len(str(r["user_id"])) for r in rows] + [len("user_id")])
        header = (
            f"  {'username'.ljust(col_w_user)}  {'user_id'.ljust(col_w_id)}  "
            f"{'req':>5}  {'err':>4}  {'first':<19}  {'last':<19}  models"
        )
        print(f"{DIM}{header}{RESET}")
        print(f"{DIM}{'-' * (len(header))}{RESET}")
        rows_sorted = sorted(rows, key=lambda r: r["requests"], reverse=True)
        for r in rows_sorted:
            color = GREEN if r["requests"] > 0 else DIM
            print(
                f"  {color}{r['username'].ljust(col_w_user)}  "
                f"{str(r['user_id']).ljust(col_w_id)}  "
                f"{r['requests']:>5}  {r['errors']:>4}  "
                f"{r['first']:<19}  {r['last']:<19}  {r['models']}{RESET}"
            )

        if extra_rows:
            print(f"\n{BOLD}Altri utenti rilevati nei log (non in scientists):{RESET}")
            for r in sorted(extra_rows, key=lambda r: r["requests"], reverse=True):
                print(
                    f"  {YELLOW}{r['username']}  id={r['user_id']}  "
                    f"req={r['requests']}  err={r['errors']}  "
                    f"first={r['first']}  last={r['last']}  models={r['models']}{RESET}"
                )

        # Totali
        total_authorized_req = sum(r["requests"] for r in rows)
        total_other_req      = sum(r["requests"] for r in extra_rows)
        print(f"\n{BOLD}Totali globali:{RESET}")
        print(f"  Richieste LLM autorizzate:  {GREEN}{total_authorized_req}{RESET}")
        print(f"  Richieste LLM altri utenti: {YELLOW}{total_other_req}{RESET}")
        print(f"  Chiamate HF totali:         {total_hf_calls}")
        print(f"  Errori HF totali:           {RED if total_hf_errors else GREEN}{total_hf_errors}{RESET}")
        print(f"  Caratteri generati totali:  {total_hf_chars:,}".replace(",", "."))

        # Istogramma ASCII di tutti gli autorizzati
        print(f"\n{BOLD}Istogramma richieste LLM per utente autorizzato:{RESET}")
        max_req = max((r["requests"] for r in rows), default=0)
        if max_req == 0:
            print(f"{DIM}  (nessuna richiesta registrata per gli utenti autorizzati){RESET}")
        else:
            bar_max = 40
            for r in rows_sorted:
                bars = int(round(r["requests"] / max_req * bar_max)) if max_req else 0
                bar  = "█" * bars
                color = CYAN if r["requests"] > 0 else DIM
                print(
                    f"  {r['username'].ljust(col_w_user)}  "
                    f"{color}{bar}{RESET} {DIM}({r['requests']}){RESET}"
                )

        # Salva report su file
        report_path = _ROOT / "logs" / "deltaplano_inference_stats.txt"
        try:
            with report_path.open("w", encoding="utf-8") as fh:
                fh.write(f"DELTA — Statistiche inferenza DELTAPLANO_bot\n")
                fh.write(f"Generato: {datetime.now().isoformat(timespec='seconds')}\n\n")
                fh.write("Per utente autorizzato:\n")
                for r in rows_sorted:
                    fh.write(
                        f"  {r['username']:<25}  id={r['user_id']:<12}  "
                        f"req={r['requests']:<5}  err={r['errors']:<4}  "
                        f"first={r['first']}  last={r['last']}  models={r['models']}\n"
                    )
                if extra_rows:
                    fh.write("\nAltri utenti rilevati:\n")
                    for r in extra_rows:
                        fh.write(
                            f"  {r['username']:<25}  id={r['user_id']:<12}  "
                            f"req={r['requests']:<5}  err={r['errors']}\n"
                        )
                fh.write(f"\nTotali: req_autorizzati={total_authorized_req}  "
                         f"req_altri={total_other_req}  hf_calls={total_hf_calls}  "
                         f"hf_errors={total_hf_errors}  chars={total_hf_chars}\n")
            print(f"\n{DIM}Report salvato in: {report_path}{RESET}")
        except Exception as exc:
            print(f"{YELLOW}⚠ Impossibile salvare report: {exc}{RESET}")

        if not id_to_username:
            print(
                f"\n{YELLOW}ℹ Nessuna mappa user_id→username ancora popolata.{RESET}\n"
                f"{DIM}  La mappa viene aggiornata automaticamente in {map_path}\n"
                f"  ad ogni interazione di un utente autorizzato sul bot Telegram.{RESET}"
            )

    def _bot_inference_log_files(self) -> list[Path]:
        log_dir = _ROOT / "logs"
        log_files = []
        for name in ("delta.log", "deltaplano_chat.log", "bot.log", "delta_runtime.log"):
            log_files.extend(self._discover_bot_inference_log_variants(log_dir, name))
        return log_files

    @staticmethod
    def _discover_bot_inference_log_variants(log_dir: Path, base_name: str) -> list[Path]:
        if not log_dir.exists():
            return []

        base_path = log_dir / base_name
        candidates: list[Path] = []
        if base_path.is_file():
            candidates.append(base_path)

        for path in log_dir.glob(f"{base_name}.*"):
            if not path.is_file():
                continue
            if AdminPanel._is_rotated_bot_inference_log(path, base_name):
                candidates.append(path)

        return sorted(
            set(candidates),
            key=lambda path: AdminPanel._bot_inference_log_sort_key(path, base_name),
        )

    @staticmethod
    def _is_rotated_bot_inference_log(path: Path, base_name: str) -> bool:
        suffix = path.name[len(base_name):]
        if not suffix.startswith("."):
            return False

        parts = [part for part in suffix.split(".") if part]
        if parts and parts[-1] == "gz":
            parts = parts[:-1]
        return len(parts) == 1 and parts[0].isdigit()

    @staticmethod
    def _bot_inference_log_sort_key(path: Path, base_name: str) -> tuple[int, int, str]:
        if path.name == base_name:
            return (1, 0, path.name)

        suffix = path.name[len(base_name):]
        parts = [part for part in suffix.split(".") if part]
        if parts and parts[-1] == "gz":
            parts = parts[:-1]
        rotation_index = int(parts[0]) if parts and parts[0].isdigit() else 0
        return (0, -rotation_index, path.name)

    @staticmethod
    def _open_bot_inference_log(log_file: Path):
        if log_file.suffix == ".gz":
            import gzip

            return gzip.open(log_file, "rt", encoding="utf-8", errors="ignore")
        return log_file.open("r", encoding="utf-8", errors="ignore")

    def _collect_bot_inference_log_stats(self, log_files: list[Path]) -> dict[str, object]:
        import re
        from collections import defaultdict

        rx_chat_ok = re.compile(
            r"delta\.chat_engine: Risposta HF \[([^\]]+)\] per user (\d+)"
        )
        rx_chat_err = re.compile(r"delta\.chat_engine: HF ha restituito errore")
        rx_bot_reply_legacy = re.compile(
            r"delta\.deltaplano_bot: Chat LLM risposta per user (\d+)"
        )
        rx_bot_reply_current = re.compile(
            r"delta\.interface\.telegram: free_chat_response\[(\d+)\]:"
        )
        rx_bot_request_current = re.compile(
            r"delta\.interface\.telegram: free_chat_handler: Ricevuto da (\d+):"
        )
        rx_hf_chars = re.compile(r"delta\.huggingface_llm: HF risposta generata .*\((\d+) chars\)")
        rx_hf_err = re.compile(r"delta\.huggingface_llm: Errore HF")
        ts_re = re.compile(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})")

        stats = defaultdict(
            lambda: {
                "requests": 0,
                "bot_replies": 0,
                "errors": 0,
                "models": set(),
                "first": None,
                "last": None,
            }
        )
        total_hf_chars = 0
        total_hf_calls = 0
        total_hf_errors = 0
        duplicate_lines_skipped = 0
        synthetic_lines_skipped = 0
        seen_lines: set[str] = set()
        counted_error_fingerprints: set[tuple[str, str]] = set()

        for log_file in log_files:
            active_user_id = ""
            try:
                with self._open_bot_inference_log(log_file) as fh:
                    for raw_line in fh:
                        line = raw_line.rstrip("\n")
                        if line in seen_lines:
                            duplicate_lines_skipped += 1
                            continue
                        seen_lines.add(line)

                        if "fake-model" in line or "FakeEngine" in line:
                            synthetic_lines_skipped += 1
                            continue

                        ts_match = ts_re.match(line)
                        ts = ts_match.group(1) if ts_match else None

                        match = rx_bot_request_current.search(line)
                        if match:
                            active_user_id = match.group(1)
                            continue

                        match = rx_chat_ok.search(line)
                        if match:
                            model, uid = match.group(1), match.group(2)
                            user_stats = stats[uid]
                            user_stats["requests"] += 1
                            user_stats["models"].add(model)
                            if ts:
                                user_stats["first"] = ts if not user_stats["first"] or ts < user_stats["first"] else user_stats["first"]
                                user_stats["last"] = ts if not user_stats["last"] or ts > user_stats["last"] else user_stats["last"]
                            active_user_id = uid
                            continue

                        match = rx_bot_reply_current.search(line) or rx_bot_reply_legacy.search(line)
                        if match:
                            uid = match.group(1)
                            stats[uid]["bot_replies"] += 1
                            active_user_id = uid
                            continue

                        match = rx_hf_chars.search(line)
                        if match:
                            total_hf_chars += int(match.group(1))
                            total_hf_calls += 1
                            continue

                        if rx_hf_err.search(line):
                            total_hf_errors += 1
                            if active_user_id:
                                fingerprint = (active_user_id, ts or line)
                                if fingerprint not in counted_error_fingerprints:
                                    stats[active_user_id]["errors"] += 1
                                    counted_error_fingerprints.add(fingerprint)
                            continue

                        if rx_chat_err.search(line) and active_user_id:
                            fingerprint = (active_user_id, ts or line)
                            if fingerprint not in counted_error_fingerprints:
                                stats[active_user_id]["errors"] += 1
                                counted_error_fingerprints.add(fingerprint)
            except Exception as exc:
                print(f"{YELLOW}⚠ Errore parsing {log_file.name}: {exc}{RESET}")

        return {
            "stats": stats,
            "total_hf_chars": total_hf_chars,
            "total_hf_calls": total_hf_calls,
            "total_hf_errors": total_hf_errors,
            "duplicate_lines_skipped": duplicate_lines_skipped,
            "synthetic_lines_skipped": synthetic_lines_skipped,
        }

    def _website_visitor_monitor(self):
        from nasa_delta_plant.privacy.website_analytics import WebsiteAnalyticsTracker

        storage_path, storage_source = self._resolve_website_analytics_storage_path()
        tracker = WebsiteAnalyticsTracker(storage_path=storage_path)
        remote_api_base = self._website_analytics_remote_api_base()

        while True:
            diagnostics = self._website_analytics_storage_diagnostics(storage_path)
            self._header()
            print(f"{BOLD}─── MONITOR VISITATORI DELTAPLANT.AI ───{RESET}")
            source_label = "settings/.env" if storage_source == "settings" else "fallback locale"
            print(f"{DIM}Storage locale: {storage_path} ({source_label}){RESET}")
            print(f"{DIM}Report live remoto: {remote_api_base}/api/analytics/report{RESET}")
            print(f"{DIM}Le viste [1]-[5] provano prima il report remoto protetto e usano il DB locale solo come fallback.{RESET}")
            if diagnostics["error"]:
                print(f"{YELLOW}⚠ Diagnostica storage: {diagnostics['error']}{RESET}\n")
            else:
                latest_event = diagnostics["latest_event_at"] or "mai"
                exists_label = "si" if diagnostics["exists"] else "no"
                print(
                    f"{DIM}DB locale: esiste={exists_label}  size={diagnostics['size_bytes']} B  "
                    f"eventi={diagnostics['total_events']}  ultimo_evento={latest_event}{RESET}"
                )
                if diagnostics["total_events"] == 0:
                    print(
                        f"{YELLOW}ℹ Nessun evento nel database locale del monitor.{RESET}\n"
                        f"{DIM}  Per muovere questo monitor non basta aprire deltaplant.ai: il sito invia page_view e click\n"
                        f"  solo dopo consenso analytics esplicito dal banner Privacy/Preferences.\n"
                        f"  Le viste di questo menu proveranno comunque prima il report live dell'API pubblica.\n"
                        f"  Inoltre questo pannello legge solo lo SQLite del backend API in esecuzione su questa macchina.\n"
                        f"  Se deltaplant.ai sta inviando eventi a un server remoto, qui vedrai zero finché non apri\n"
                        f"  l'admin sullo stesso host del backend pubblico o non punti allo stesso storage analytics.\n"
                        f"  Check operativo: abilita analytics sul sito, ricarica la pagina e verifica il monitor sul server\n"
                        f"  che ospita api.deltaplant.ai.{RESET}"
                    )
            print()
            print(f"  {BOLD}[1]{RESET} Panoramica ultime 24 ore")
            print(f"  {BOLD}[2]{RESET} Panoramica ultimi 7 giorni")
            print(f"  {BOLD}[3]{RESET} Panoramica ultimi 30 giorni")
            print(f"  {BOLD}[4]{RESET} Eventi recenti ultimi 30 giorni")
            print(f"  {BOLD}[5]{RESET} Esporta report JSON ultimi 30 giorni")
            print(f"  {BOLD}[6]{RESET} Diagnostica report remoto")
            print(f"  {BOLD}[0]{RESET} Indietro")

            scelta = input(f"\n{BOLD}> Scelta: {RESET}").strip()

            if scelta == "1":
                self._print_website_analytics_summary(tracker, 1)
            elif scelta == "2":
                self._print_website_analytics_summary(tracker, 7)
            elif scelta == "3":
                self._print_website_analytics_summary(tracker, 30)
            elif scelta == "4":
                self._print_website_analytics_recent_events(tracker, 30)
            elif scelta == "5":
                self._export_website_analytics_report(tracker, 30)
            elif scelta == "6":
                self._print_website_analytics_remote_diagnostics()
            elif scelta == "0":
                return
            else:
                print(f"{YELLOW}⚠ Scelta non valida.{RESET}")

            input(f"\n{DIM}Premi Invio per continuare...{RESET}")

    @staticmethod
    def _website_analytics_remote_api_base() -> str:
        configured = (os.getenv("DELTA_PUBLIC_API_BASE") or os.getenv("DELTA_API_BASE") or "").strip()
        return configured.rstrip("/") if configured else "https://api.deltaplant.ai"

    def _issue_admin_analytics_token(self, lifetime_minutes: int = 5) -> str:
        if not self._admin_authenticated:
            raise RuntimeError("Admin authentication required.")

        from nasa_delta_plant.config import get_settings

        settings = get_settings()
        now = datetime.now(timezone.utc)
        payload = {
            "sub": "delta-admin",
            "scope": "admin:analytics:read",
            "iss": "delta-admin-panel",
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(minutes=lifetime_minutes)).timestamp()),
        }
        return jwt.encode(
            payload,
            settings.secret_key.get_secret_value(),
            algorithm=settings.jwt_algorithm,
        )

    def _fetch_remote_website_analytics_report(
        self,
        days: int,
        recent_limit: int = 15,
    ) -> tuple[dict[str, object] | None, str | None]:
        diagnostic = self._request_remote_website_analytics_report(days=days, recent_limit=recent_limit)
        if diagnostic["ok"]:
            report = diagnostic["report"]
            if isinstance(report, dict):
                report.setdefault("report_source", "remote_api")
                return report, None
        error = diagnostic.get("error")
        return None, str(error) if error else None

    def _request_remote_website_analytics_report(
        self,
        days: int,
        recent_limit: int = 15,
    ) -> dict[str, object]:
        api_base = self._website_analytics_remote_api_base()
        endpoint = f"{api_base}/api/analytics/report"
        diagnostic: dict[str, object] = {
            "ok": False,
            "api_base": api_base,
            "endpoint": endpoint,
            "authenticated": self._admin_authenticated,
            "token_available": False,
            "status_code": None,
            "detail": None,
            "error": None,
            "report": None,
        }

        if not self._admin_authenticated:
            diagnostic["error"] = "Admin non autenticato: impossibile firmare il token report remoto."
            return diagnostic

        try:
            token = self._issue_admin_analytics_token()
        except Exception as exc:
            diagnostic["error"] = f"Token admin analytics non disponibile: {exc}"
            return diagnostic

        diagnostic["token_available"] = True

        try:
            response = requests.get(
                endpoint,
                params={"days": days, "recent_limit": recent_limit},
                headers={"Authorization": f"Bearer {token}"},
                timeout=10,
            )
        except requests.RequestException as exc:
            diagnostic["error"] = f"Endpoint report remoto non raggiungibile: {exc}"
            return diagnostic

        diagnostic["status_code"] = response.status_code
        try:
            response_payload = response.json()
        except ValueError:
            response_payload = None

        if response.ok:
            payload = response_payload if isinstance(response_payload, dict) else {}
            payload.setdefault("report_source", "remote_api")
            diagnostic["ok"] = True
            diagnostic["report"] = payload
            diagnostic["detail"] = "Report remoto disponibile."
            return diagnostic

        detail = None
        if isinstance(response_payload, dict):
            detail = response_payload.get("detail")
        if not detail:
            detail = response.text.strip() or f"HTTP {response.status_code}"
        diagnostic["detail"] = detail
        diagnostic["error"] = f"Report remoto rifiutato da {endpoint}: {detail}"
        return diagnostic

    def _load_website_analytics_report(
        self,
        tracker,
        days: int,
        recent_limit: int = 15,
    ) -> tuple[dict[str, object], str, str | None]:
        remote_report, remote_error = self._fetch_remote_website_analytics_report(
            days=days,
            recent_limit=recent_limit,
        )
        if remote_report is not None:
            return remote_report, "API pubblica", None

        local_report = tracker.build_report(days=days, recent_limit=recent_limit)
        local_report["report_source"] = "local_storage"
        return local_report, "SQLite locale", remote_error

    def _print_website_analytics_remote_diagnostics(self, days: int = 30, recent_limit: int = 5):
        diagnostic = self._request_remote_website_analytics_report(days=days, recent_limit=recent_limit)

        print(f"\n{BOLD}─── DIAGNOSTICA REPORT REMOTO ───{RESET}")
        print(f"  API base:             {CYAN}{diagnostic['api_base']}{RESET}")
        print(f"  Endpoint:             {CYAN}{diagnostic['endpoint']}{RESET}")
        print(
            f"  Admin autenticato:    {CYAN}{'si' if diagnostic['authenticated'] else 'no'}{RESET}"
        )
        print(
            f"  Token disponibile:    {CYAN}{'si' if diagnostic['token_available'] else 'no'}{RESET}"
        )

        status_code = diagnostic.get("status_code")
        if status_code is not None:
            print(f"  HTTP status:          {CYAN}{status_code}{RESET}")

        if diagnostic["ok"]:
            report = diagnostic.get("report") or {}
            totals = report.get("totals") or {}
            print(f"  Esito remoto:         {GREEN}OK{RESET}")
            print(f"  Eventi totali:        {CYAN}{totals.get('total_events', 0)}{RESET}")
            print(f"  Visitatori unici:     {CYAN}{totals.get('unique_visitors', 0)}{RESET}")
            print(f"  Sessioni uniche:      {CYAN}{totals.get('unique_sessions', 0)}{RESET}")
            print(f"  Motivo fallback:      {DIM}nessuno{RESET}")
            return

        detail = diagnostic.get("detail")
        error = diagnostic.get("error") or "Sconosciuto"
        print(f"  Esito remoto:         {YELLOW}FALLBACK LOCALE{RESET}")
        if detail:
            print(f"  Dettaglio remoto:     {YELLOW}{detail}{RESET}")
        print(f"  Motivo fallback:      {YELLOW}{error}{RESET}")

    def _resolve_website_analytics_storage_path(self) -> tuple[Path, str]:
        default_path = _ROOT / "data" / "analytics" / "website_events.sqlite"
        try:
            from nasa_delta_plant.config import get_settings

            configured_path = Path(get_settings().website_analytics_storage_path)
            return configured_path, "settings"
        except Exception:
            return default_path, "fallback"

    def _website_analytics_storage_diagnostics(self, storage_path: Path) -> dict[str, object]:
        diagnostics: dict[str, object] = {
            "exists": storage_path.exists(),
            "size_bytes": storage_path.stat().st_size if storage_path.exists() else 0,
            "total_events": 0,
            "latest_event_at": None,
            "error": None,
        }
        if not storage_path.exists():
            return diagnostics

        try:
            with sqlite3.connect(str(storage_path)) as connection:
                tables = {
                    row[0]
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type = 'table'"
                    ).fetchall()
                }
                if "website_analytics_events" not in tables:
                    diagnostics["error"] = "Tabella website_analytics_events assente."
                    return diagnostics

                row = connection.execute(
                    "SELECT COUNT(*) AS total_events, MAX(created_at) AS latest_event_at "
                    "FROM website_analytics_events"
                ).fetchone()
                diagnostics["total_events"] = int((row[0] if row else 0) or 0)
                diagnostics["latest_event_at"] = row[1] if row else None
        except Exception as exc:
            diagnostics["error"] = str(exc)

        return diagnostics

    def _print_website_analytics_summary(self, tracker, days: int):
        report, source_name, warning = self._load_website_analytics_report(tracker, days=days)
        totals = report["totals"]

        print(f"\n{BOLD}─── PANORAMICA VISITATORI ({days} giorni) ───{RESET}")
        print(f"{DIM}Fonte dati: {source_name}{RESET}")
        if warning:
            print(f"{YELLOW}⚠ Fallback locale: {warning}{RESET}")
        print(f"  Visitatori unici:      {CYAN}{totals['unique_visitors']}{RESET}")
        print(f"  Sessioni uniche:       {CYAN}{totals['unique_sessions']}{RESET}")
        print(f"  Eventi totali:         {CYAN}{totals['total_events']}{RESET}")
        print(f"  Page view:             {CYAN}{totals['page_views']}{RESET}")
        print(f"  Session start:         {CYAN}{totals['session_starts']}{RESET}")
        print(f"  CTA click:             {CYAN}{totals['cta_clicks']}{RESET}")
        print(f"  Click outbound:        {CYAN}{totals['outbound_clicks']}{RESET}")
        print(f"  Run dashboard NASA:    {CYAN}{totals['hero_dashboard_runs']}{RESET}")
        print(f"  Invii contact form:    {CYAN}{totals['contact_submissions']}{RESET}")
        print(f"  Engagement medio:      {CYAN}{totals['avg_engagement_seconds']:.2f}s{RESET}")

        if report.get("top_pages"):
            print(f"\n{BOLD}Pagine più visitate:{RESET}")
            for row in report["top_pages"][:5]:
                print(f"  • {row['page_path']:<36} {row['count']:>5}")

        if report.get("top_referrers"):
            print(f"\n{BOLD}Referrer principali:{RESET}")
            for row in report["top_referrers"][:5]:
                print(f"  • {row['referrer_host']:<36} {row['count']:>5}")

        if report.get("top_campaigns"):
            print(f"\n{BOLD}Campagne UTM:{RESET}")
            for row in report["top_campaigns"][:5]:
                print(f"  • {row['utm_campaign']:<36} {row['count']:>5}")

        if report.get("device_breakdown"):
            print(f"\n{BOLD}Dispositivi:{RESET}")
            for row in report["device_breakdown"][:5]:
                print(f"  • {row['device_type']:<16} {row['count']:>5}")

        if report.get("language_breakdown"):
            print(f"\n{BOLD}Lingue:{RESET}")
            for row in report["language_breakdown"][:5]:
                print(f"  • {row['language']:<16} {row['count']:>5}")

        if report.get("daily"):
            print(f"\n{BOLD}Ultimi giorni:{RESET}")
            for row in report["daily"][:7]:
                print(f"  • {row['day']}  eventi={row['events']:<4}  visitatori={row['visitors']}")
        else:
            print(f"\n{DIM}Nessun evento analytics registrato nel periodo selezionato.{RESET}")

    def _print_website_analytics_recent_events(self, tracker, days: int):
        report, source_name, warning = self._load_website_analytics_report(
            tracker,
            days=days,
            recent_limit=15,
        )
        recent = report.get("recent_events") or []

        print(f"\n{BOLD}─── EVENTI RECENTI ({days} giorni) ───{RESET}")
        print(f"{DIM}Fonte dati: {source_name}{RESET}")
        if warning:
            print(f"{YELLOW}⚠ Fallback locale: {warning}{RESET}")
        if not recent:
            print(f"{DIM}Nessun evento analytics registrato.{RESET}")
            return

        for event in recent:
            label = f" [{event['event_label']}]" if event.get("event_label") else ""
            referrer = f" ref={event['referrer_host']}" if event.get("referrer_host") else ""
            engagement = (
                f" engagement={event['engaged_seconds']:.2f}s"
                if isinstance(event.get("engaged_seconds"), (int, float))
                else ""
            )
            print(
                f"  • {event['created_at']}  {CYAN}{event['event_type']}{RESET}{label}  "
                f"{event['page_path']}{referrer}{engagement}"
            )

    def _export_website_analytics_report(self, tracker, days: int):
        export_dir = _ROOT / "exports"
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        destination = export_dir / f"website_analytics_{days}d_{timestamp}.json"
        report, source_name, warning = self._load_website_analytics_report(
            tracker,
            days=days,
            recent_limit=15,
        )
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        if warning:
            print(f"{YELLOW}⚠ Export in fallback locale: {warning}{RESET}")
        print(f"\n{GREEN}✔ Report analytics esportato da {source_name}: {destination}{RESET}")

    # ── Helper ─────────────────────────────────────────────────

    def _header(self):
        print(f"\n{BOLD}{'═' * 52}{RESET}")
        print(f"{BOLD}      🔐  DELTA — PANNELLO AMMINISTRATORE{RESET}")
        print(f"{BOLD}{'═' * 52}{RESET}")
