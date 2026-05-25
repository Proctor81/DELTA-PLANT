# DELTA Plant — Knowledge Base LLM (estratto dal Manuale)

## Executive Summary
- DELTA è un sistema edge-AI per la salute delle piante: sensori, visione artificiale, deep learning, diagnosi e raccomandazioni.
- Funziona su Raspberry Pi 5 con AI HAT 2+, sensori ambientali e camera.
- Diagnosi in tempo reale, explainability LayerCAM, raccomandazioni agronomiche, export Excel, Telegram bot.

## Flusso Diagnosi
1. Acquisizione immagine (camera o upload)
2. Rilevamento organo (foglia)
3. Preprocessing e segmentazione
4. Inferenza AI (MobileNetV2/EfficientFormer)
5. Lettura sensori (temperatura, umidità, luce, CO2, pH, EC)
6. Applicazione regole agronomiche
7. Calcolo Quantum Risk Score (Grover)
8. Raccomandazioni pratiche
9. Output su Telegram/CLI/API

## Hardware
- Raspberry Pi 5, AI HAT 2+, Camera Module 3, sensori BME680, VEML7700, SCD41, ADS1115, elettrodi pH/EC.
- Collegamento via I2C, calibrazione sensori, alimentazione consigliata 27W.

## AI e Explainability
- Classificazione fogliare 33 classi PlantVillage.
- Backend MobileNetV2 (baseline) e EfficientFormerV2-S1 (avanzato, int8 quantized, explainability LayerCAM).
- Explainability: heatmap LayerCAM sovrapposta alla foglia, aiuta a capire la decisione AI.

## Uso Software
- Avvio: comando `delta` o `python main.py`.
- Menu CLI: diagnosi, dati sensori, export Excel, Academy, pannello admin, chat libera.
- Export Excel: il report esporta la finestra mobile degli ultimi 30 giorni e rimuove automaticamente i record più vecchi.
- Pipeline X: flusso MLOps per training, export, benchmark, dissemination, manuale.

## Telegram Bot
- Diagnosi guidata: invio foto, descrizione, sensori, inferenza, raccomandazioni.
- Chat libera: domande su stato, raccomandazioni, troubleshooting.
- Export Excel e storico diagnosi direttamente in chat, limitati agli ultimi 30 giorni.
- Academy, preflight AI, dati sensori via Telegram.

## Chat AI e Manuale
- L'operatore puo fare domande operative sul Manuale DELTA Plant senza dover scrivere per forza la parola "manuale".
- Il motore LLM usa la knowledge base del manuale per rispondere su installazione, menu, export Excel, Telegram bot, NASA-ISRO/SAR, preflight, API e troubleshooting.
- Se la domanda richiede una formula o una definizione presente nel manuale, la risposta deve riportare il testo tecnico corrispondente in modo fedele.

## Database
- SQLite, tabella `diagnoses` con tutti i parametri.
- Backup manuale: copia file delta.db.

## Troubleshooting
- Sensori non rilevati: controlla collegamenti, I2C, driver.
- Camera non funziona: verifica cavo, abilitazione, test con libcamera.
- AI non disponibile: controlla venv, dipendenze, versione ai-edge-litert.
- Export Excel: installa openpyxl e verifica che esistano diagnosi registrate negli ultimi 30 giorni.
- Database corrotto: ripristina da backup, verifica integrità.
- Bot Telegram non risponde: verifica servizio, token, rete.
- LLM non risponde: verifica token HuggingFace, connettività, variabili .env.

## Calcolo del rischio fungino (modalità NASA-ISRO/SAR)
La formula attualmente implementata in DELTA per il rischio fungino giornaliero è:

```
humidity_factor = clamp((umidita_relativa - 60) / 40, 0, 1)
temp_factor = clamp((temperatura_media_c - 12) / 18, 0, 1)
rain_factor = clamp(precipitazioni_mm / 14, 0, 1)
persistenza = rischio_precedente * 0.05

rischio_fungino = clamp(
	0.40 * humidity_factor
	+ 0.35 * temp_factor
	+ 0.25 * rain_factor
	+ persistenza,
	0,
	1,
)
```

Dove:
- **humidity_factor** misura quanto l'umidita supera la soglia di 60% ed e normalizzato nel range 0..1.
- **temp_factor** cresce da 0 a 1 tra 12 C e 30 C.
- **rain_factor** normalizza la pioggia giornaliera considerando saturazione a 14 mm.
- **persistenza** conserva il 5% del rischio del giorno precedente.

Il dashboard settimanale riporta la media aritmetica degli ultimi 7 valori giornalieri e la traduce in etichetta BASSO, MEDIO o ALTO.

---
## Esempi di Domande e Prompt Few-Shot
### Domanda: "Come si avvia una diagnosi?"
Risposta: "Per avviare una diagnosi, seleziona 'Avvia diagnosi pianta' dal menu CLI o invia una foto al bot Telegram. Segui le istruzioni per descrivere la pianta e acquisire i dati sensori."

### Domanda: "Cosa significa il Quantum Risk Score?"
Risposta: "Il Quantum Risk Score (QRS) è un indice tra 0 e 1 calcolato dall'Oracolo Quantistico di Grover. Indica il rischio complessivo della pianta considerando tutti i fattori ambientali e i sintomi rilevati."

### Domanda: "Come si aggiorna il manuale?"
Risposta: "Esegui il comando: python Manuale/genera_manuale.py. Il manuale PDF verrà rigenerato automaticamente con le ultime modifiche."

### Domanda: "Come si esportano i dati in Excel?"
Risposta: "Dal menu CLI o dal bot Telegram, seleziona 'Report Excel'. Verrà generato/aggiornato il file exports/delta_diagnoses.xlsx con le diagnosi degli ultimi 30 giorni; i record più vecchi vengono eliminati automaticamente."

### Domanda: "Cosa fare se il bot Telegram non risponde?"
Risposta: "Verifica che il servizio sia attivo (systemctl is-active delta), che il token Telegram sia corretto nel file .env e che la rete sia disponibile. Consulta la sezione troubleshooting del manuale."

### Domanda: "Come funziona la explainability LayerCAM?"
Risposta: "LayerCAM genera una heatmap che evidenzia le aree della foglia più rilevanti per la decisione AI. L'overlay aiuta a capire se il modello sta osservando sintomi reali."

---

Questa knowledge base può essere usata per rispondere a domande frequenti, generare prompt few-shot per l’LLM, o come contesto dinamico per risposte accurate all’operatore.

## Indice dettagliato del Manuale
Ecco l’indice completo del Manuale Utente DELTA (aggiornato automaticamente):

1. Introduzione
Scientific Paper
2. Hardware — Componenti e configurazione
3. Hardware — Modello AI e visione
4. Software — Installazione
5. Software — Utilizzo del sistema
6. Software — API REST e Telegram
7. Database e persistenza
8. Architettura software — Moduli
9. Risoluzione problemi
10. Aggiornamento del manuale
11. DELTA Academy — Formazione operatore
12. Analisi multi-organo — Foglia/Fiore/Frutto
13. Oracolo Quantistico di Grover
14b. Chat AI — HuggingFace LLM e «Chiedi a DELTA»
15. Sicurezza e Pannello Amministratore
16. Input immagini da cartella — No-Camera
17. Installazione automatica Raspberry Pi 5
18. MLOps — Addestramento e Miglioramento Continuo
19. Modello Pre-addestrato — Download automatico
20. GitHub Publisher — Pubblicazione automatica
Appendice Hardware — Assemblaggio e Schema elettrico
Appendice Licenza — DELTA PLANT SOFTWARE LICENSE
