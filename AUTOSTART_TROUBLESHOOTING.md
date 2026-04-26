# 🔧 Troubleshooting Autostart DELTA su Raspberry Pi 5

## 📋 Indice

- [Diagnosi rapida](#diagnosi-rapida)
- [Problemi comuni e soluzioni](#problemi-comuni-e-soluzioni)
- [Verificare lo stato del servizio](#verificare-lo-stato-del-servizio)
- [Reset e recovery](#reset-e-recovery)
- [Log e debug](#log-e-debug)

---

## 🔍 Diagnosi rapida

Esegui questo comando per un controllo completo:

```bash
sudo bash diagnose_autostart.sh
```

Lo script verificherà automaticamente:
- ✅ Se il servizio è registrato e abilitato
- ✅ Se il token Telegram è configurato
- ✅ Se i file del modello AI sono presenti
- ✅ Se l'ambiente virtuale Python è corretto
- ✅ Se la connessione Telegram è disponibile
- ✅ Se ci sono processi stale

---

## ❌ Problemi comuni e soluzioni

### 1. **"Il bot Telegram non risponde"**

**Sintomi:**
- Il servizio sembra attivo ma il bot non riceve messaggi
- `journalctl -u delta` mostra errori di connessione

**Soluzioni:**

a) **Verifica il token:**
```bash
grep DELTA_TELEGRAM_TOKEN /home/pi/DELTA\ 2.0/.env
```

Se è vuoto o contiene "inserisci_qui_il_token_del_bot":
```bash
nano /home/pi/DELTA\ 2.0/.env
# Modifica: DELTA_TELEGRAM_TOKEN=<il_tuo_token_da_@BotFather>
```

b) **Riavvia il servizio:**
```bash
sudo systemctl restart delta
```

c) **Verifica la connessione Telegram:**
```bash
ping api.telegram.org
```

Se non risponde → problema di rete/firewall.

---

### 2. **"Servizio non si avvia" / "Crashed"**

**Sintomi:**
- `sudo systemctl status delta` mostra **inactive** o **failed**
- Boot machine non vede il bot attivo

**Soluzioni rapide:**

**Opzione A: Reset leggero**
```bash
sudo systemctl stop delta
rm -f ~/DELTA\ 2.0/delta.pid
sudo systemctl start delta
```

**Opzione B: Hard recovery** (reinstalla tutto)
```bash
sudo bash ~/DELTA\ 2.0/fix_autostart.sh --hard-reset
```

**Opzione C: Test manuale**
```bash
cd ~/DELTA\ 2.0
./.venv/bin/python main.py --enable-api --enable-telegram --daemon
```

Se non dai errori, il problema è nel servizio systemd. Procedi con Opzione B.

---

### 3. **"Errore: `json.decoder.JSONDecodeError`" in telegram_bot.py**

**Causa:** API non abilitata quando il bot tenta di avviarsi

**Soluzione:**

Verifica che `delta.service` contenga:
```ini
ExecStart=DELTA_DIR/.venv/bin/python DELTA_DIR/main.py --enable-api --enable-telegram --daemon
```

Se manca `--enable-api`, aggiungi e reinstalla:
```bash
sudo bash ~/DELTA\ 2.0/install_service.sh
```

---

### 4. **"Modulo non trovato: tensorflow / telegram"**

**Sintomi:**
- Log mostra `ModuleNotFoundError: No module named 'tensorflow'`
- Servizio muore dopo pochi secondi

**Soluzioni:**

```bash
# Installa dipendenze mancanti
cd ~/DELTA\ 2.0
./.venv/bin/pip install -r requirements.txt

# Riavvia
sudo systemctl restart delta
```

Se continua a fallire:
```bash
# Ricrea venv completo
rm -rf ~/.DELTA\ 2.0/.venv
python3 -m venv ~/.DELTA\ 2.0/.venv
~/.DELTA\ 2.0/.venv/bin/pip install -r ~/DELTA\ 2.0/requirements.txt

# Reinstalla servizio
sudo bash ~/DELTA\ 2.0/fix_autostart.sh --hard-reset
```

---

### 5. **"Timeout di avvio" / "RestartSec=15 ripete"**

**Sintomi:**
- Il servizio riavvia ogni 15 secondi
- Log mostra timeout nella lettura della rete o Telegram

**Cause comuni:**
- Rete non pronta al boot
- DNS non disponibile
- Telegram timeout per connessione lenta

**Soluzioni:**

a) **Aumentare il delay di avvio:**
```bash
sudo nano /etc/systemd/system/delta.service
# Modifica: RestartSec=30
# (o più se la rete è veramente lenta)
```

b) **Assicurare che la rete sia pronta:**
```bash
sudo systemctl enable NetworkManager-wait-online.service
# oppure
sudo systemctl enable systemd-networkd-wait-online.service
```

c) **Riavvia il servizio:**
```bash
sudo systemctl daemon-reload
sudo systemctl restart delta
```

---

### 6. **"Permission denied" / "Cannot write to logs"**

**Sintomi:**
- Log: `Permission denied: '/DELTA_DIR/logs/...`
- Servizio muore durante scrittura

**Soluzioni:**

```bash
# Verifica proprietario
ls -la ~/DELTA\ 2.0/logs

# Se non è l'utente 'pi', cambia:
sudo chown -R pi:pi ~/DELTA\ 2.0

# Riavvia
sudo systemctl restart delta
```

---

## 📊 Verificare lo stato del servizio

### Status
```bash
sudo systemctl status delta
```

Output atteso se funziona:
```
● delta.service - DELTA AI Agent — Diagnosi Piante & Bot Telegram
     Loaded: loaded (/etc/systemd/system/delta.service; enabled; vendor preset: disabled)
     Active: active (running) since ...
```

### Abilitato al boot?
```bash
sudo systemctl is-enabled delta
# Output: enabled
```

### È in esecuzione?
```bash
sudo systemctl is-active delta
# Output: active
```

---

## 🔄 Reset e Recovery

### Reset leggero (senza riconfigurare)
```bash
sudo systemctl stop delta
rm -f ~/DELTA\ 2.0/delta.pid
sudo systemctl start delta
```

### Recovery completo
```bash
sudo bash ~/DELTA\ 2.0/fix_autostart.sh
```

### Hard reset (riconfigura da zero)
```bash
sudo bash ~/DELTA\ 2.0/fix_autostart.sh --hard-reset
```

---

## 📝 Log e Debug

### Visualizzare i log in tempo reale
```bash
sudo journalctl -u delta -f
```

### Ultime 50 linee di log
```bash
sudo journalctl -u delta -n 50 --no-pager
```

### Log dal boot più recente
```bash
sudo journalctl -u delta -b
```

### Salva i log in un file
```bash
sudo journalctl -u delta > /tmp/delta_logs.txt
cat /tmp/delta_logs.txt
```

### Cerca errori specifici
```bash
sudo journalctl -u delta | grep ERROR
sudo journalctl -u delta | grep Traceback
```

---

## 🆘 Se niente funziona

1. **Esegui la diagnostica completa:**
   ```bash
   sudo bash ~/DELTA\ 2.0/diagnose_autostart.sh
   ```

2. **Hard reset:**
   ```bash
   sudo bash ~/DELTA\ 2.0/fix_autostart.sh --hard-reset
   ```

3. **Verifica i log di boot:**
   ```bash
   sudo systemctl restart delta
   sleep 5
   sudo journalctl -u delta -n 100
   ```

4. **Se persiste, raccogli dati per issue:**
   ```bash
   sudo bash ~/DELTA\ 2.0/diagnose_autostart.sh > /tmp/delta_diagnostic.txt 2>&1
   sudo journalctl -u delta -n 200 >> /tmp/delta_diagnostic.txt
   # Condividi il file in una issue su GitHub
   cat /tmp/delta_diagnostic.txt
   ```

---

## 📞 Supporto

Se il problema persiste:
1. Esegui `diagnose_autostart.sh`
2. Salva l'output completo
3. Apri una issue su GitHub con:
   - Output di `diagnose_autostart.sh`
   - Output di `journalctl -u delta -n 200`
   - Descrizione di cosa stavi facendo

---

**Ultima modifica:** 26 aprile 2026  
**Versione DELTA:** 2.0.5+
