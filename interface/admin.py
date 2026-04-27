"""
DELTA - interface/admin.py
Pannello Amministratore DELTA — accesso protetto da password.
Funzionalità: cambio password, log di sistema, statistiche DB,
configurazione, backup, reset Academy.
"""

import json
import logging
import shutil
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

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
            return False
        if verify_password(pw):
            print(f"{GREEN}✔ Accesso autorizzato.{RESET}")
            logger.info("Accesso admin riuscito.")
            return True
        print(f"{RED}✘ Password errata. Accesso negato.{RESET}")
        logger.warning("Tentativo di accesso admin FALLITO.")
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
        return _ROOT / "data" / "telegram_scientists.json"

    def _load_scientists(self) -> list[str]:
        path = self._scientists_path()
        if not path.exists():
            return ["@paolo_81_paolo"]
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

    # ── Helper ─────────────────────────────────────────────────

    def _header(self):
        print(f"\n{BOLD}{'═' * 52}{RESET}")
        print(f"{BOLD}      🔐  DELTA — PANNELLO AMMINISTRATORE{RESET}")
        print(f"{BOLD}{'═' * 52}{RESET}")
