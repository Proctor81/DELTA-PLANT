"""
DELTA - interface/academy.py
=============================
DELTA Academy: modulo di formazione interattiva per l'operatore umano.
Offre tutorial guidati, simulazioni diagnostiche e quiz teorici per
addestrare l'operatore all'uso del sistema DELTA, producendo output
fedeli all'ambiente reale.
"""

import random
import logging
import json
from pathlib import Path

logger = logging.getLogger("delta.interface.academy")

# ── Palette colori terminale ─────────────────────────────────
BOLD    = "\033[1m"
RESET   = "\033[0m"
DIM     = "\033[2m"
ITALIC  = "\033[3m"
GREEN   = "\033[92m"
YELLOW  = "\033[93m"
RED     = "\033[91m"
CYAN    = "\033[96m"
BLUE    = "\033[94m"
MAGENTA = "\033[95m"
WHITE   = "\033[97m"

RISK_COLORS = {
    "nessuno": GREEN,
    "basso":   CYAN,
    "medio":   YELLOW,
    "alto":    RED,
    "critico": "\033[31;1m",
}

# ─────────────────────────────────────────────────────────────
# SCENARI DI SIMULAZIONE
# ─────────────────────────────────────────────────────────────

SCENARIOS = [
    {
        "id": 1,
        "titolo": "Oidio su pomodoro",
        "contesto": "Serra — varieta San Marzano, 45 giorni dalla semina",
        "sintomi_visivi": (
            "Le foglie superiori mostrano una patina bianca polverosa e farinosa. "
            "Le foglie colpite si deformano e accartocciano verso l'alto. "
            "Alcune foglie piu vecchie ingialliscono e cadono."
        ),
        "dati_sensori": {
            "Temperatura":  ("26.5 C",   "Leggermente alta"),
            "Umidita":      ("55.0 %",   "Normale"),
            "Pressione":    ("1013 hPa", "Normale"),
            "Luminosita":   ("15000 lux","Buona"),
            "CO2":          ("420 ppm",  "Normale"),
            "pH":           ("6.8",      "Ottimale"),
            "EC":           ("1.8 mS/cm","Ottimale"),
        },
        "stato_sensori": {
            "Temperatura": "warn", "Umidita": "ok", "Pressione": "ok",
            "Luminosita": "ok", "CO2": "ok", "pH": "ok", "EC": "ok",
        },
        "ai_class": "Oidio (Powdery Mildew)",
        "ai_confidence": 87.3,
        "ai_top3": [
            ("Oidio (Powdery Mildew)",    87.3),
            ("Muffa Grigia (Botrytis)",    6.2),
            ("Pianta Sana",                3.1),
        ],
        "rischio_corretto": "alto",
        "diagnosi": (
            "Rilevata infezione fungina da Erysiphe spp. (oidio). La patina bianca "
            "e il micelio superficiale del fungo. Temperatura 26.5 C e umidita 55% "
            "sono condizioni favorevoli allo sviluppo."
        ),
        "raccomandazioni_corrette": [
            "Applicare fungicida a base di zolfo o bicarbonato di potassio",
            "Aumentare la ventilazione della serra",
            "Evitare l'irrigazione fogliare nelle ore serali",
            "Rimuovere e distruggere le foglie colpite",
        ],
        "spiegazione_finale": (
            "L'oidio si sviluppa meglio a 22-30 C con umidita moderata (40-70%). "
            "A differenza di altri funghi NON richiede foglie bagnate per germogliare. "
            "Il rischio e ALTO perche l'infezione e gia visibile e si diffonde rapidamente. "
            "Intervento tempestivo entro 24-48 ore."
        ),
    },
    {
        "id": 2,
        "titolo": "Carenza di azoto su lattuga",
        "contesto": "Impianto idroponico DFT — lattuga Batavia, 20 giorni",
        "sintomi_visivi": (
            "Le foglie piu vecchie (esterne) mostrano ingiallimento diffuso e uniforme. "
            "Il colore verde si schiarisce progressivamente verso le foglie interne. "
            "La crescita e rallentata rispetto ai cicli precedenti."
        ),
        "dati_sensori": {
            "Temperatura":  ("22.0 C",   "Ottimale"),
            "Umidita":      ("68.0 %",   "Normale"),
            "Pressione":    ("1010 hPa", "Normale"),
            "Luminosita":   ("12000 lux","Buona"),
            "CO2":          ("410 ppm",  "Normale"),
            "pH":           ("7.2",      "Troppo alto!"),
            "EC":           ("0.6 mS/cm","TROPPO BASSA"),
        },
        "stato_sensori": {
            "Temperatura": "ok", "Umidita": "ok", "Pressione": "ok",
            "Luminosita": "ok", "CO2": "ok", "pH": "warn", "EC": "err",
        },
        "ai_class": "Carenza Azoto",
        "ai_confidence": 91.0,
        "ai_top3": [
            ("Carenza Azoto",   91.0),
            ("Pianta Sana",      5.2),
            ("Clorosi Ferrica",  2.1),
        ],
        "rischio_corretto": "medio",
        "diagnosi": (
            "Carenza di azoto confermata. EC di 0.6 mS/cm e insufficiente (ottimale: "
            "1.5-2.5 mS/cm). pH a 7.2 riduce ulteriormente la disponibilita di azoto. "
            "L'ingiallimento parte dalle foglie vecchie perche N e mobile nella pianta."
        ),
        "raccomandazioni_corrette": [
            "Aumentare la concentrazione della soluzione nutritiva (EC target: 1.8)",
            "Correggere il pH a 5.8-6.2 aggiungendo acido nitrico diluito",
            "Controllare la pompa e il sistema di circolazione",
            "Monitorare il miglioramento nelle successive 24-48 ore",
        ],
        "spiegazione_finale": (
            "In idroponica l'EC misura la 'forza' della soluzione nutritiva. "
            "EC 0.6 e tipica dell'acqua di rubinetto, senza nutrienti. "
            "Il pH alto (7.2) blocca anche l'assorbimento di ferro e manganese. "
            "Rischio MEDIO: la carenza e correggibile rapidamente senza danni permanenti."
        ),
    },
    {
        "id": 3,
        "titolo": "Marciume radicale da sovra-irrigazione",
        "contesto": "Vaso 30L — peperoni, substrato torba/perlite, sera",
        "sintomi_visivi": (
            "Le foglie sono flaccide nonostante il substrato sia umido. "
            "Alcune foglie mostrano macchie marroni con alone giallastro. "
            "Il colletto della pianta appare scurito e morbido al tatto. "
            "Odore di terra stagna evidente aprendo il vaso."
        ),
        "dati_sensori": {
            "Temperatura":  ("20.0 C",   "Normale"),
            "Umidita":      ("92.0 %",   "CRITICA — rischio funghi"),
            "Pressione":    ("1008 hPa", "Normale"),
            "Luminosita":   ("5000 lux", "Bassa (sera)"),
            "CO2":          ("430 ppm",  "Normale"),
            "pH":           ("6.5",      "Ottimale"),
            "EC":           ("2.1 mS/cm","Ottimale"),
        },
        "stato_sensori": {
            "Temperatura": "ok", "Umidita": "err", "Pressione": "ok",
            "Luminosita": "warn", "CO2": "ok", "pH": "ok", "EC": "ok",
        },
        "ai_class": "Marciume Radicale",
        "ai_confidence": 78.5,
        "ai_top3": [
            ("Marciume Radicale", 78.5),
            ("Stress Idrico",     12.3),
            ("Carenza Calcio",     5.6),
        ],
        "rischio_corretto": "critico",
        "diagnosi": (
            "RISCHIO CRITICO — Probabile marciume radicale da Pythium spp. "
            "Umidita del 92% con substrato saturo crea condizioni ideali per oomiceti. "
            "Il marciume al colletto e un segno grave. Confidenza 78.5%: revisione umana consigliata."
        ),
        "raccomandazioni_corrette": [
            "SOSPENDERE IMMEDIATAMENTE l'irrigazione",
            "Estrarre la pianta e ispezionare le radici (sane = bianche/gialle)",
            "Applicare fungicida sistemico a base di metalaxyl o fosfonato",
            "Migliorare il drenaggio e ridurre la frequenza di irrigazione",
            "Abbassare l'umidita ambientale sotto il 70%",
        ],
        "spiegazione_finale": (
            "Pythium e Phytophthora sono oomiceti che si muovono nell'acqua. "
            "Substrato saturo + umidita >85% = propagazione esplosiva. "
            "Il rischio e CRITICO: in 24-48h puo portare alla morte della pianta. "
            "Nota: pH ed EC ottimali confermano che il problema e esclusivamente idrico."
        ),
    },
    {
        "id": 4,
        "titolo": "Pianta in condizioni ottimali",
        "contesto": "Serra professionale — basilico, 30 giorni, mattina",
        "sintomi_visivi": (
            "Le foglie sono verde brillante, turgide e di dimensioni uniformi. "
            "Nessuna macchia, decolorazione o deformazione visibile. "
            "La pianta mostra una crescita vigorosa e regolare."
        ),
        "dati_sensori": {
            "Temperatura":  ("24.0 C",   "Ottimale"),
            "Umidita":      ("65.0 %",   "Ottimale"),
            "Pressione":    ("1012 hPa", "Normale"),
            "Luminosita":   ("20000 lux","Ottimale"),
            "CO2":          ("450 ppm",  "Buono"),
            "pH":           ("6.3",      "Ottimale"),
            "EC":           ("1.9 mS/cm","Ottimale"),
        },
        "stato_sensori": {
            "Temperatura": "ok", "Umidita": "ok", "Pressione": "ok",
            "Luminosita": "ok", "CO2": "ok", "pH": "ok", "EC": "ok",
        },
        "ai_class": "Pianta Sana",
        "ai_confidence": 96.2,
        "ai_top3": [
            ("Pianta Sana",            96.2),
            ("Carenza Azoto (lieve)",   2.1),
            ("Stress Luce",             0.9),
        ],
        "rischio_corretto": "nessuno",
        "diagnosi": (
            "Pianta in eccellenti condizioni fitosanitarie. Tutti i parametri "
            "rientrano nei range ottimali. Nessuna anomalia rilevata dal motore "
            "di regole agronomiche. Confidenza AI 96.2%."
        ),
        "raccomandazioni_corrette": [
            "Mantenere le condizioni attuali",
            "Continuare il monitoraggio regolare ogni 6-12 ore",
            "Documentare i parametri per riferimento futuro",
        ],
        "spiegazione_finale": (
            "Scenario di riferimento: tutti i parametri nell'ottimale. "
            "Riconoscere uno stato di salute ottimale e importante quanto identificare "
            "un problema: evita interventi non necessari che potrebbero stressare la pianta."
        ),
    },
    {
        "id": 5,
        "titolo": "Attacco di afidi — rilevazione precoce",
        "contesto": "Tunnel plastica — peperoncino Cayenne, estate",
        "sintomi_visivi": (
            "Foglie giovani accartocciate verso il basso con superficie appiccicosa. "
            "Sotto le foglie si osservano colonie di piccoli insetti verdi (1-2 mm). "
            "Presenza di fumaggine (patina nera) su foglie inferiori."
        ),
        "dati_sensori": {
            "Temperatura":  ("27.5 C",   "Elevata — favorevole agli insetti"),
            "Umidita":      ("58.0 %",   "Normale"),
            "Pressione":    ("1015 hPa", "Normale"),
            "Luminosita":   ("25000 lux","Alta"),
            "CO2":          ("415 ppm",  "Normale"),
            "pH":           ("6.6",      "Ottimale"),
            "EC":           ("2.0 mS/cm","Ottimale"),
        },
        "stato_sensori": {
            "Temperatura": "warn", "Umidita": "ok", "Pressione": "ok",
            "Luminosita": "ok", "CO2": "ok", "pH": "ok", "EC": "ok",
        },
        "ai_class": "Attacco Parassiti (Afidi)",
        "ai_confidence": 83.0,
        "ai_top3": [
            ("Attacco Parassiti (Afidi)",      83.0),
            ("Virus Mosaico (vettore insetto)", 9.5),
            ("Pianta Sana",                     4.1),
        ],
        "rischio_corretto": "alto",
        "diagnosi": (
            "Rilevato attacco attivo di afidi. La mielata appiccicosa favorisce la fumaggine. "
            "Temperatura 27.5 C accelera il ciclo riproduttivo (una generazione ogni 7-10 gg). "
            "FONDAMENTALE la visione artificiale: i sensori ambientali non rilevano insetti."
        ),
        "raccomandazioni_corrette": [
            "Applicare insetticida (es. piretrine naturali o imidacloprid sistemico)",
            "Installare trappole cromotrope gialle per il monitoraggio",
            "Favorire insetti predatori (coccinelle) come lotta biologica",
            "Isolare le piante colpite per evitare la diffusione",
        ],
        "spiegazione_finale": (
            "Gli afidi si moltiplicano per partenogenesi: una femmina genera 80-100 "
            "neanidi in pochi giorni a 27 C. La mielata favorisce Cladosporium (fumaggine) "
            "e gli afidi possono trasmettere virus (top3 mostra 9.5% virus). "
            "Rischio ALTO ma non critico: intervento entro 2-3 giorni."
        ),
    },
    # ── SCENARI v3.1 — Generalizzazione PlantVillage ──────────────────────────
    {
        "id": 6,
        "titolo": "Peperone: maculatura batterica (reclassificazione genus)",
        "contesto": "Tunnel plastica — peperone California Wonder, 60 giorni",
        "sintomi_visivi": (
            "Foglie con piccole macchie acquose circolari, poi necrotiche al centro e con alone giallastro. "
            "Le macchie si concentrano sui bordi fogliari. I frutti mostrano lesioni superficiali ruvide. "
            "La progressione e rapida nelle ultime 48 ore dopo un temporale."
        ),
        "dati_sensori": {
            "Temperatura":  ("24.0 C",   "Favorevole ai batteri"),
            "Umidita":      ("88.0 %",   "CRITICA — sopra soglia fungina"),
            "Pressione":    ("1008 hPa", "Bassa — tempo instabile"),
            "Luminosita":   ("18000 lux","Normale"),
            "CO2":          ("420 ppm",  "Normale"),
            "pH":           ("6.7",      "Ottimale"),
            "EC":           ("2.0 mS/cm","Ottimale"),
        },
        "stato_sensori": {
            "Temperatura": "warn", "Umidita": "err", "Pressione": "warn",
            "Luminosita": "ok", "CO2": "ok", "pH": "ok", "EC": "ok",
        },
        "ai_class": "Maculatura batterica peperone (Bell_pepper_Bacterial_spot)",
        "ai_confidence": 84.2,
        "ai_top3": [
            ("Bell_pepper_Bacterial_spot", 84.2),
            ("Tomato_Bacterial_spot",      10.1),
            ("Bell_pepper_healthy",         3.4),
        ],
        "rischio_corretto": "alto",
        "diagnosi": (
            "Maculatura batterica da Xanthomonas spp. su peperone. "
            "L'operatore ha descritto 'peperone con macchie', quindi DELTA ha correttamente "
            "classificato il genere Bell_pepper e selezionato la classe specifica tra le sole "
            "classi del genere corrispondente — evitando confusione con Tomato_Bacterial_spot. "
            "Umidita 88% e pioggia recente hanno favorito la diffusione batterica."
        ),
        "raccomandazioni_corrette": [
            "Applicare rame ossicloruro o idrossido di rame (a base rameica)",
            "Evitare irrigazione a pioggia o lavori su piante bagnate",
            "Rimuovere foglie gravemente colpite e distruggerle",
            "Abbassare l'umidita relativa sotto il 75% con ventilazione",
        ],
        "spiegazione_finale": (
            "INNOVAZIONE v3.1 — DELTA ora riconosce il genere della pianta dalla descrizione "
            "dell'operatore (es. 'peperone', 'pomodoro', 'uva'). Questo gli permette di filtrare "
            "le classi PlantVillage al solo genere corretto prima di chiedere all'LLM la diagnosi. "
            "Senza questo filtro, 'Bell_pepper_Bacterial_spot' e 'Tomato_Bacterial_spot' hanno "
            "firme visive simili e il modello poteva classificare male. "
            "Il genus-filter a due fasi (multi-parola prima, poi parola singola) garantisce che "
            "'bell pepper' sia riconosciuto prima di 'pepper' o 'peperone'."
        ),
    },
    {
        "id": 7,
        "titolo": "Vite in buona salute — rilevazione contestuale",
        "contesto": "Vigneto biologico — Barbera d'Asti, luglio",
        "sintomi_visivi": (
            "Foglie verde intenso, lamina integra senza macchie o deformazioni. "
            "I grappoli si stanno sviluppando regolarmente. "
            "L'operatore dice: 'la vite sembra stare benone, vediamo come va'."
        ),
        "dati_sensori": {
            "Temperatura":  ("23.5 C",   "Ottimale"),
            "Umidita":      ("62.0 %",   "Nella norma"),
            "Pressione":    ("1016 hPa", "Alta — tempo stabile"),
            "Luminosita":   ("30000 lux","Ottimale per vite"),
            "CO2":          ("415 ppm",  "Normale"),
            "pH":           ("6.2",      "Ottimale"),
            "EC":           ("1.7 mS/cm","Ottimale"),
        },
        "stato_sensori": {
            "Temperatura": "ok", "Umidita": "ok", "Pressione": "ok",
            "Luminosita": "ok", "CO2": "ok", "pH": "ok", "EC": "ok",
        },
        "ai_class": "Grape_healthy",
        "ai_confidence": 93.7,
        "ai_top3": [
            ("Grape_healthy",    93.7),
            ("Grape_Black_rot",   3.1),
            ("Grape_Esca",        1.8),
        ],
        "rischio_corretto": "nessuno",
        "diagnosi": (
            "Vite in ottime condizioni fitosanitarie. "
            "DELTA ha rilevato la parola 'vite' nella descrizione e ha limitato la ricerca "
            "alle classi Grape_* di PlantVillage. "
            "Poiche l'operatore ha descritto la pianta come sana ('sta benone'), "
            "l'analisi LLM contestuale ha confermato SANO e ha prodotto una valutazione "
            "di benessere senza avviare il flusso diagnostico patologico."
        ),
        "raccomandazioni_corrette": [
            "Mantenere le condizioni attuali di irrigazione e fertilizzazione",
            "Monitoraggio preventivo per peronospora e oidio ogni 5-7 giorni",
            "Documentare i parametri attuali come baseline stagionale",
        ],
        "spiegazione_finale": (
            "INNOVAZIONE v3.1 — Il rilevamento contestuale della salute non si basa piu "
            "sulla sola parola 'sano' ma su valutazione LLM dell'intera frase dell'operatore. "
            "Frasi come 'sta benone', 'sembra in forma', 'nessun problema visibile' "
            "vengono ora interpretate correttamente come stato di salute positivo. "
            "L'LLM risponde con SANO/NON_SANO/INCERTO su un prompt stateless (senza memoria) "
            "per evitare contaminazione della conversazione principale."
        ),
    },
]

QUIZ_QUESTIONS = [
    {
        "domanda": "Quale parametro misura la concentrazione di nutrienti nella soluzione idroponica?",
        "opzioni": [
            "pH — acidita/basicita della soluzione",
            "EC — conducibilita elettrica (mS/cm)",
            "CO2 — concentrazione di anidride carbonica",
            "Pressione atmosferica (hPa)",
        ],
        "corretta": 1,
        "spiegazione": (
            "L'EC (Electrical Conductivity) misura la presenza di ioni disciolti. "
            "Valori tipici: 0.5-1.0 per piantine, 1.5-2.5 per piante adulte, "
            ">3.5 = rischio bruciatura radicale."
        ),
    },
    {
        "domanda": "Quando DELTA richiede obbligatoriamente la revisione umana?",
        "opzioni": [
            "Sempre, dopo ogni diagnosi automatica",
            "Solo durante la notte (sensori meno affidabili)",
            "Quando la confidenza AI scende sotto il 50% o il rischio e critico",
            "Quando i sensori fisici non sono collegati (modalita simulata)",
        ],
        "corretta": 2,
        "spiegazione": (
            "Il sistema di Active Learning chiede conferma quando la confidenza e < 50%. "
            "Nella logica semplificata la revisione umana resta informativa e di controllo qualita operativa."
        ),
    },
    {
        "domanda": "Quale range di pH e ottimale per le colture orticole in idroponica?",
        "opzioni": [
            "3.5 - 4.5  (molto acido)",
            "5.5 - 6.5  (leggermente acido)",
            "7.0 - 7.5  (neutro-basico)",
            "8.0 - 9.0  (basico)",
        ],
        "corretta": 1,
        "spiegazione": (
            "5.5-6.5 e il range in cui tutti i nutrienti essenziali sono massimamente "
            "disponibili. Fuori da questo range alcuni nutrienti precipitano (pH alto) "
            "o diventano tossici (pH molto basso)."
        ),
    },
    {
        "domanda": "Cosa indica un'umidita relativa superiore all'85% per periodi prolungati?",
        "opzioni": [
            "Condizioni ottimali per la fotosintesi accelerata",
            "Alto rischio di malattie fungine (Botrytis, Pythium, Oidio)",
            "Carenza di CO2 nell'aria",
            "Nessun rischio — l'umidita non influenza le malattie",
        ],
        "corretta": 1,
        "spiegazione": (
            "Umidita alta riduce la traspirazione fogliare, favorisce condensazione "
            "e crea l'ambiente ideale per spore fungine. "
            "DELTA segnala rischio fungino sopra la soglia configurata in SENSOR_CONFIG."
        ),
    },
    {
        "domanda": "In DELTA, quale bus di comunicazione usano i sensori ambientali?",
        "opzioni": [
            "SPI (Serial Peripheral Interface)",
            "UART / RS232",
            "I2C (Inter-Integrated Circuit)",
            "USB 2.0",
        ],
        "corretta": 2,
        "spiegazione": (
            "I2C usa 2 fili: SDA (dati) su GPIO 2 (Pin 3) e SCL (clock) su GPIO 3 (Pin 5). "
            "Tutti i sensori DELTA (BME680, VEML7700, SCD41, ADS1115) condividono lo stesso bus."
        ),
    },
    {
        "domanda": "Cosa significa il colore ROSSO BOLD nel terminale DELTA?",
        "opzioni": [
            "Rischio BASSO — solo monitoraggio aggiuntivo",
            "Errore di connessione ai sensori",
            "Rischio CRITICO — intervento urgente necessario",
            "Modalita simulazione attiva",
        ],
        "corretta": 2,
        "spiegazione": (
            "Codice colore DELTA: Verde=nessuno, Ciano=basso, Giallo=medio, "
            "Rosso chiaro=alto, ROSSO BOLD=critico. Il critico richiede intervento "
            "nelle successive 1-6 ore per evitare perdita della coltura."
        ),
    },
    {
        "domanda": "Qual e l'obiettivo principale della logica semplificata AI in DELTA?",
        "opzioni": [
            "Ridurre i flussi runtime non necessari mantenendo diagnosi affidabili",
            "Aumentare la complessita dei menu operatore",
            "Spostare tutta la logica in training on-device continuo",
            "Disattivare completamente la diagnosi automatica",
        ],
        "corretta": 0,
        "spiegazione": (
            "La versione semplificata privilegia stabilita operativa: "
            "meno flussi runtime, meno punti di errore, comportamento piu prevedibile."
        ),
    },
    {
        "domanda": "In quale modalita DELTA puo operare senza sensori fisici collegati?",
        "opzioni": [
            "Non puo operare — i sensori sono obbligatori",
            "Modalita 'emergency' con valori a zero",
            "Modalita 'simulated' — genera dati realistici per sviluppo/test",
            "Modalita 'offline' — legge l'ultimo database salvato",
        ],
        "corretta": 2,
        "spiegazione": (
            "La modalita 'simulated' genera valori random realistici per ogni sensore, "
            "permettendo sviluppo e test completi senza hardware. "
            "Esiste anche la modalita 'manual' per l'inserimento da tastiera."
        ),
    },
    # ── QUIZ v3.1 — Generalizzazione PlantVillage ─────────────────────────────
    {
        "domanda": (
            "v3.1 — Perche DELTA identifica il genere della pianta dalla descrizione "
            "dell'operatore prima di interrogare l'LLM sulla malattia?"
        ),
        "opzioni": [
            "Per ridurre i costi API verso HuggingFace",
            "Per filtrare le classi PlantVillage al solo genere corretto, evitando "
            "che l'LLM confonda classi visivamente simili di generi diversi",
            "Per permettere la diagnosi senza immagine",
            "Per disabilitare il flusso Q&A se la pianta e nota",
        ],
        "corretta": 1,
        "spiegazione": (
            "Il genus-filter programmatico riduce le classi candidate da 33 a poche "
            "(es. 2 classi per Bell_pepper). L'LLM lavora su un sottoinsieme mirato "
            "anziche sull'intera lista, eliminando la confusione tra classi a firma "
            "visiva simile appartenenti a generi diversi (es. Bell_pepper_Bacterial_spot "
            "vs Tomato_Bacterial_spot)."
        ),
    },
    {
        "domanda": (
            "v3.1 — Perche il rilevamento contestuale della salute usa una chiamata "
            "LLM 'stateless' (senza memoria) invece del metodo chat() normale?"
        ),
        "opzioni": [
            "Perche chat() non funziona in Telegram",
            "Per risparmiare tempo: chat() e piu lento",
            "Per evitare che la valutazione salute contamini la ConversationMemory "
            "dell'utente con prompt interni non destinati all'operatore",
            "Perche chat_internal e piu preciso sull'analisi delle piante",
        ],
        "corretta": 2,
        "spiegazione": (
            "chat() scrive sempre nella memoria conversazionale dell'utente. "
            "chat_internal() invia la richiesta all'LLM con history=[] senza "
            "leggere ne scrivere la ConversationMemory. Cosi i prompt tecnici interni "
            "(SANO/NON_SANO/INCERTO, genus detection, follow-up generation) non "
            "appaiono nella storia della chat dell'operatore."
        ),
    },
    {
        "domanda": (
            "v3.1 — Durante il flusso Q&A follow-up (max 5 domande), quale flag "
            "blocca il free_chat_handler dal rispondere in parallelo?"
        ),
        "opzioni": [
            "diagnosis_active — lo stesso flag usato per l'inserimento sensori",
            "diag_qa_active — flag dedicato impostato a True prima di STATE_DIAG_FOLLOWUP",
            "chat_enabled — flag globale del sistema",
            "sensor_lock — blocco hardware per evitare interferenze",
        ],
        "corretta": 1,
        "spiegazione": (
            "diagnosis_active viene resettato a False prima del Q&A follow-up, "
            "percio non puo proteggere quella fase. Il nuovo flag diag_qa_active "
            "viene impostato True appena prima di return STATE_DIAG_FOLLOWUP e "
            "resettato a False solo quando il ConversationHandler torna a END. "
            "Questo impedisce al free_chat_handler (group=99) di rispondere anche "
            "lui alle risposte dell'operatore, eliminando il doppio messaggio."
        ),
    },
]


# ─────────────────────────────────────────────────────────────
# CLASSE DELTA ACADEMY
# ─────────────────────────────────────────────────────────────

class DeltaAcademy:
    """
    DELTA Academy — modulo di formazione interattiva per l'operatore.

    Simula scenari reali di diagnosi fitosanitaria per addestrare
    l'operatore all'utilizzo del sistema DELTA con output fedeli
    all'ambiente reale. Include tutorial, simulazioni e quiz.
    """

    PROGRESS_FILE = Path(__file__).resolve().parent.parent / "data" / "academy_progress.json"

    def __init__(self):
        self.progress = self._load_progress()

    # ─── PERSISTENZA PROGRESSO ───────────────────────────────

    def _load_progress(self) -> dict:
        if self.PROGRESS_FILE.exists():
            try:
                return json.loads(self.PROGRESS_FILE.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {
            "total_score":              0,
            "sessions":                 0,
            "quiz_correct":             0,
            "quiz_total":               0,
            "sim_correct":              0,
            "sim_total":                0,
            "training_lab_completed":   0,
            "training_lab_score":       0,
            "badges":                   [],
        }

    def _save_progress(self):
        try:
            self._ensure_progress_keys()
            self.PROGRESS_FILE.parent.mkdir(parents=True, exist_ok=True)
            self.PROGRESS_FILE.write_text(
                json.dumps(self.progress, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception as exc:
            logger.warning("Impossibile salvare progresso Academy: %s", exc)

    def _ensure_progress_keys(self):
        """Garantisce retrocompatibilita con file progresso creati prima di nuove sezioni."""
        defaults = {
            "total_score": 0,
            "sessions": 0,
            "quiz_correct": 0,
            "quiz_total": 0,
            "sim_correct": 0,
            "sim_total": 0,
            "training_lab_completed": 0,
            "training_lab_score": 0,
            "badges": [],
        }
        for key, value in defaults.items():
            self.progress.setdefault(key, value)

    # ─── MENU PRINCIPALE ─────────────────────────────────────

    def run(self):
        """Avvia il menu principale della DELTA Academy."""
        self._print_academy_banner()
        self._ensure_progress_keys()
        self.progress["sessions"] += 1

        while True:
            self._print_academy_menu()
            scelta = input(f"\n{BOLD}> Scelta Academy: {RESET}").strip()

            if scelta == "1":
                self._tutorial_guidato()
            elif scelta == "2":
                self._sim_identifica_malattia()
            elif scelta == "3":
                self._sim_valutazione_rischio()
            elif scelta == "4":
                self._sim_scegli_intervento()
            elif scelta == "5":
                self._quiz_teorico()
            elif scelta == "6":
                self._mostra_progresso()
            elif scelta == "7":
                self._lab_miglioramento_continuo()
            elif scelta == "0":
                print(f"\n{DIM}Uscita da DELTA Academy...{RESET}")
                self._save_progress()
                break
            else:
                print(f"  {YELLOW}Opzione non valida. Scegliere un numero tra 0 e 7.{RESET}")

    # ─── BANNER E MENU ───────────────────────────────────────

    @staticmethod
    def _print_academy_banner():
        print(f"""
{BOLD}{BLUE}
+----------------------------------------------------------+
|                                                          |
|             D E L T A   A C A D E M Y                    |
|                                                          |
|         Formazione Interattiva per Operatori             |
|     Simulazioni Realistiche  *  Quiz  *  Tutorial        |
|                                                          |
+----------------------------------------------------------+
{RESET}""")

    @staticmethod
    def _print_academy_menu():
        print(f"\n{BOLD}=== MENU ACADEMY ==={RESET}")
        print(f"  {CYAN}[1]{RESET} Tutorial Guidato  — Primo utilizzo di DELTA")
        print(f"  {CYAN}[2]{RESET} Simulazione: Identifica la Malattia")
        print(f"  {CYAN}[3]{RESET} Simulazione: Valutazione del Rischio")
        print(f"  {CYAN}[4]{RESET} Simulazione: Scegli l'Intervento Corretto")
        print(f"  {CYAN}[5]{RESET} Quiz Teorico — Conoscenze DELTA")
        print(f"  {CYAN}[6]{RESET} Il Mio Progresso")
        print(f"  {CYAN}[7]{RESET} Lab MLOps Operatore — Miglioramento Continuo")
        print(f"  {CYAN}[0]{RESET} Torna al Menu Principale")

    # ─── TUTORIAL GUIDATO ────────────────────────────────────

    def _tutorial_guidato(self):
        """Tutorial interattivo passo-passo per il primo utilizzo."""
        print(f"\n{BOLD}{'=' * 60}{RESET}")
        print(f"{BOLD}{BLUE}  TUTORIAL GUIDATO — DELTA PLANT{RESET}")
        print(f"{BOLD}{'=' * 60}{RESET}")

        passi = [
            (
                "PASSO 1 — Avvio del sistema",
                "DELTA si avvia eseguendo:\n"
                "    python DELTA.py\n\n"
                "All'avvio il sistema:\n"
                "  * Inizializza il modello AI (carica il file .tflite)\n"
                "  * Avvia il thread sensori in background\n"
                "  * Mostra il banner e il menu principale\n\n"
                "Se i sensori fisici non sono collegati, DELTA passa automaticamente\n"
                "in modalita SIMULATA (dati generati artificialmente per test).",
            ),
            (
                "PASSO 2 — Il Menu Principale",
                "Il menu offre 6 funzioni principali:\n\n"
                "  [1] Diagnosi pianta      — analisi completa (immagine + sensori)\n"
                "  [2] Fine-tuning AI       — disabilitato nella logica semplificata\n"
                "  [3] Dati sensori         — lettura istantanea dell'ambiente\n"
                "  [4] Esporta Excel        — salva tutti i dati in .xlsx\n"
                "  [5] Ultime diagnosi      — storico delle analisi nel database\n"
                "  [6] DELTA Academy        — formazione interattiva (qui!)\n\n"
                "Per ogni funzione basterà digitare il numero e premere INVIO.",
            ),
            (
                "PASSO 3 — Eseguire una Diagnosi",
                "Selezionando [1] il sistema:\n\n"
                "  1. Chiede se inserire i dati sensori manualmente\n"
                "     Rispondere 's' per manuale o 'n' per automatico\n\n"
                "  2. Acquisisce l'immagine dalla camera\n"
                "     Posizionare la foglia al centro dell'inquadratura\n\n"
                "  3. Elabora: AI classifica + sensori analizzano\n\n"
                "  4. Mostra il risultato:\n"
                "     * Stato pianta e livello di rischio (colore)\n"
                "     * Classe AI e percentuale di confidenza\n"
                "     * Spiegazione dettagliata e raccomandazioni",
            ),
            (
                "PASSO 4 — Interpretare i Risultati",
                "Il livello di RISCHIO e codificato per colore:\n\n"
                f"  {GREEN}[NESSUNO]{RESET}  — pianta sana, solo monitoraggio\n"
                f"  {CYAN}[BASSO]{RESET}    — anomalia lieve, osservare\n"
                f"  {YELLOW}[MEDIO]{RESET}    — problema in sviluppo, intervenire a breve\n"
                f"  {RED}[ALTO]{RESET}     — problema grave, intervenire entro 24-48 h\n"
                f"  {RED}{BOLD}[CRITICO]{RESET}  — emergenza, intervenire entro poche ore\n\n"
                "Se la confidenza AI e < 50% il sistema chiedera la tua opinione:\n"
                "questa informazione viene usata per migliorare il modello (Active Learning).",
            ),
            (
                "PASSO 5 — Parametri Ambientali Chiave",
                "I sensori monitorano 7 parametri. Range ottimali:\n\n"
                "  Temperatura  :  18 - 26 C      (dipende dalla coltura)\n"
                "  Umidita      :  50 - 75 %      (sopra 85% = rischio funghi)\n"
                "  Luminosita   :  8000-25000 lux  (dipende dalla coltura)\n"
                "  CO2          :  400 - 600 ppm   (valori alti accelerano la crescita)\n"
                "  pH           :  5.5 - 6.5       (idroponica; 6.0-7.0 per suolo)\n"
                "  EC           :  1.5 - 2.5 mS/cm (soluzione nutritiva)\n"
                "  Pressione    :  980 - 1020 hPa  (indicatore meteorologico)",
            ),
            (
                "PASSO 6 — DELTA impara dalla tua descrizione (v3.1)",
                "Quando avvii una diagnosi DELTA ti chiede:\n"
                "  'Di che pianta si tratta? Descrivimi l'anomalia riscontrata.'\n\n"
                "Cosa fa DELTA con la tua risposta:\n\n"
                "  1. GENUS DETECTION (programmatico)\n"
                "     Rileva il genere PlantVillage dalla descrizione:\n"
                "     'peperone' -> Bell_pepper, 'vite' -> Grape, 'mais' -> Corn...\n"
                "     Le parole multi-termine ('bell pepper') hanno priorita.\n\n"
                "  2. FILTRO CLASSI\n"
                "     Limita la ricerca alle sole classi del genere rilevato.\n"
                "     Es. per 'peperone': solo Bell_pepper_Bacterial_spot e Bell_pepper_healthy\n\n"
                "  3. HEALTHY CHECK (LLM contestuale)\n"
                "     Se descrivi la pianta come sana ('sta benone', 'nessun problema')\n"
                "     DELTA lo rileva e produce una valutazione di benessere anziche\n"
                "     una diagnosi di malattia.\n\n"
                "  4. Q&A FOLLOW-UP (se serve)\n"
                "     Se il genere non e riconosciuto o la classe non corrisponde,\n"
                "     DELTA fa fino a 5 domande di approfondimento per affinare\n"
                "     la diagnosi tramite dialogo Operatore/AI.\n\n"
                "CONSIGLIO: descrivi sempre tipo di pianta, parte colpita e sintomi.\n"
                "  Esempio ottimale: 'Peperone con macchie acquose sulle foglie,\n"
                "                     bordi necrotici e alone giallastro, dopo la pioggia'",
            ),
        ]

        for i, (titolo, contenuto) in enumerate(passi, 1):
            print(f"\n{BOLD}{CYAN}{'─' * 60}{RESET}")
            print(f"{BOLD}  {titolo}{RESET}")
            print(f"{CYAN}{'─' * 60}{RESET}\n")
            print(contenuto)
            if i < len(passi):
                input(f"\n  {DIM}Premi INVIO per il prossimo passo...{RESET}")

        print(f"\n{GREEN}{BOLD}Tutorial completato! +10 punti{RESET}")
        print("  Ora sei pronto per usare DELTA.")
        print("  Prova le simulazioni per mettere alla prova le tue conoscenze!")
        self.progress["total_score"] += 10
        self._check_badges()
        self._save_progress()
        input(f"\n{DIM}Premi INVIO per tornare al menu Academy...{RESET}")

    # ─── SIM: IDENTIFICA LA MALATTIA ─────────────────────────

    def _sim_identifica_malattia(self):
        """Simulazione: l'operatore deve identificare la malattia."""
        print(f"\n{BOLD}{'=' * 60}{RESET}")
        print(f"{BOLD}{BLUE}  SIMULAZIONE — IDENTIFICA LA MALATTIA{RESET}")
        print(f"{'=' * 60}{RESET}\n")
        print("Osserva sintomi visivi e dati sensori, poi seleziona la diagnosi.\n")

        scenario = random.choice(SCENARIOS)
        self._stampa_scenario(scenario)

        tutte_classi = [s["ai_class"] for s in SCENARIOS]
        distrattori  = [c for c in tutte_classi if c != scenario["ai_class"]]
        random.shuffle(distrattori)
        opzioni = [scenario["ai_class"]] + distrattori[:3]
        random.shuffle(opzioni)
        corretta_idx = opzioni.index(scenario["ai_class"])

        print(f"\n{BOLD}Quale malattia/condizione e presente?{RESET}")
        for i, opz in enumerate(opzioni):
            print(f"  [{i + 1}] {opz}")

        risposta = input(f"\n{BOLD}> La tua risposta (1-{len(opzioni)}): {RESET}").strip()
        self.progress["sim_total"] += 1

        try:
            idx = int(risposta) - 1
            if idx == corretta_idx:
                print(f"\n{GREEN}{BOLD}CORRETTO! +15 punti{RESET}")
                print(f"\n{ITALIC}Diagnosi DELTA:{RESET} {scenario['diagnosi']}")
                self.progress["sim_correct"] += 1
                self.progress["total_score"] += 15
            else:
                print(f"\n{RED}Risposta errata.{RESET}")
                print(f"  La risposta corretta era: {BOLD}{scenario['ai_class']}{RESET}")
                print(f"\n{ITALIC}Diagnosi DELTA:{RESET} {scenario['diagnosi']}")
        except (ValueError, IndexError):
            print(f"{YELLOW}Input non valido.{RESET}")

        self._stampa_spiegazione(scenario)
        self._check_badges()
        self._save_progress()
        input(f"\n{DIM}Premi INVIO per tornare al menu Academy...{RESET}")

    # ─── SIM: VALUTAZIONE RISCHIO ────────────────────────────

    def _sim_valutazione_rischio(self):
        """Simulazione: l'operatore valuta il livello di rischio."""
        print(f"\n{BOLD}{'=' * 60}{RESET}")
        print(f"{BOLD}{BLUE}  SIMULAZIONE — VALUTAZIONE DEL RISCHIO{RESET}")
        print(f"{'=' * 60}{RESET}\n")
        print("Analizza il quadro clinico e scegli il livello di rischio.\n")

        scenario = random.choice(SCENARIOS)
        self._stampa_scenario(scenario)

        livelli = ["nessuno", "basso", "medio", "alto", "critico"]
        print(f"\n{BOLD}Quale livello di rischio assegneresti?{RESET}")
        for i, lvl in enumerate(livelli):
            col = RISK_COLORS.get(lvl, "")
            print(f"  [{i + 1}] {col}{lvl.upper()}{RESET}")

        risposta = input(f"\n{BOLD}> La tua risposta (1-5): {RESET}").strip()
        self.progress["sim_total"] += 1

        try:
            idx     = int(risposta) - 1
            scelto  = livelli[idx]
            corretto = scenario["rischio_corretto"]
            col_c   = RISK_COLORS.get(corretto, "")
            col_s   = RISK_COLORS.get(scelto, "")

            if scelto == corretto:
                print(f"\n{GREEN}{BOLD}CORRETTO! Rischio {col_c}{corretto.upper()}{RESET}"
                      f"{GREEN}{BOLD}. +15 punti{RESET}")
                self.progress["sim_correct"] += 1
                self.progress["total_score"] += 15
            else:
                distanza = abs(livelli.index(scelto) - livelli.index(corretto))
                if distanza == 1:
                    print(f"\n{YELLOW}Quasi! Hai risposto {col_s}{scelto.upper()}{RESET}"
                          f"{YELLOW}, corretto era {col_c}{corretto.upper()}{RESET}"
                          f"{YELLOW}. +5 punti{RESET}")
                    self.progress["total_score"] += 5
                else:
                    print(f"\n{RED}Errato. Hai risposto {col_s}{scelto.upper()}{RESET}"
                          f"{RED}, corretto era {col_c}{corretto.upper()}{RESET}")
        except (ValueError, IndexError):
            print(f"{YELLOW}Input non valido.{RESET}")

        self._stampa_spiegazione(scenario)
        self._check_badges()
        self._save_progress()
        input(f"\n{DIM}Premi INVIO per tornare al menu Academy...{RESET}")

    # ─── SIM: SCEGLI L'INTERVENTO ────────────────────────────

    def _sim_scegli_intervento(self):
        """Simulazione: l'operatore sceglie le azioni di intervento corrette."""
        print(f"\n{BOLD}{'=' * 60}{RESET}")
        print(f"{BOLD}{BLUE}  SIMULAZIONE — SCEGLI L'INTERVENTO{RESET}")
        print(f"{'=' * 60}{RESET}\n")
        print("Sulla base della diagnosi, seleziona le 2 azioni corrette.\n")

        scenario = random.choice(SCENARIOS)
        self._stampa_scenario_breve(scenario)

        col = RISK_COLORS.get(scenario["rischio_corretto"], "")
        print(f"\n{BOLD}Diagnosi DELTA confermata:{RESET}")
        print(f"  Malattia : {BOLD}{scenario['ai_class']}{RESET}")
        print(f"  Rischio  : {col}{scenario['rischio_corretto'].upper()}{RESET}")
        print(f"  {DIM}{scenario['diagnosi']}{RESET}\n")

        corrette    = scenario["raccomandazioni_corrette"]
        errate_pool = [
            "Aumentare la temperatura a 35 C per accelerare la crescita",
            "Interrompere la fertilizzazione per 30 giorni",
            "Aumentare l'irrigazione alla massima portata disponibile",
            "Applicare concime fogliare azotato ad alta concentrazione",
            "Ridurre la luminosita al 10% per ridurre lo stress",
            "Aggiungere sale da cucina alla soluzione nutritiva",
        ]
        random.shuffle(errate_pool)
        corrette_sc = corrette[:2]
        errate_sc   = errate_pool[:2]
        opzioni_all = corrette_sc + errate_sc
        random.shuffle(opzioni_all)

        print(f"{BOLD}Seleziona le 2 azioni CORRETTE da eseguire:{RESET}")
        for i, opz in enumerate(opzioni_all):
            print(f"  [{i + 1}] {opz}")

        print(f"\n{DIM}Inserisci due numeri separati da spazio (es: 1 3){RESET}")
        risposta = input(f"{BOLD}> Le tue scelte: {RESET}").strip()
        self.progress["sim_total"] += 1

        try:
            scelte_idx = [int(x) - 1 for x in risposta.split()[:2]]
            scelte     = [opzioni_all[i] for i in scelte_idx if 0 <= i < len(opzioni_all)]
            giuste     = set(corrette_sc) & set(scelte)

            if giuste == set(corrette_sc):
                print(f"\n{GREEN}{BOLD}PERFETTO! Entrambe le azioni corrette. +20 punti{RESET}")
                self.progress["sim_correct"] += 1
                self.progress["total_score"] += 20
            elif len(giuste) == 1:
                print(f"\n{YELLOW}Una risposta corretta su due. +5 punti{RESET}")
                print(f"  Azione corretta trovata: {GREEN}{list(giuste)[0]}{RESET}")
                self.progress["total_score"] += 5
            else:
                print(f"\n{RED}Nessuna azione corretta selezionata.{RESET}")

            print(f"\n{BOLD}Raccomandazioni complete DELTA:{RESET}")
            for r in corrette:
                print(f"  {GREEN}[OK]{RESET} {r}")
        except (ValueError, IndexError):
            print(f"{YELLOW}Input non valido. Inserire due numeri separati da spazio.{RESET}")

        self._stampa_spiegazione(scenario)
        self._check_badges()
        self._save_progress()
        input(f"\n{DIM}Premi INVIO per tornare al menu Academy...{RESET}")

    # ─── QUIZ TEORICO ────────────────────────────────────────

    def _quiz_teorico(self):
        """Quiz a risposta multipla sulle conoscenze teoriche DELTA."""
        print(f"\n{BOLD}{'=' * 60}{RESET}")
        print(f"{BOLD}{BLUE}  QUIZ TEORICO — CONOSCENZE DELTA{RESET}")
        print(f"{'=' * 60}{RESET}\n")
        print(f"  {DIM}5 domande a risposta multipla. Ogni corretta vale 10 punti.{RESET}\n")

        domande     = random.sample(QUIZ_QUESTIONS, min(5, len(QUIZ_QUESTIONS)))
        score_round = 0

        for i, q in enumerate(domande, 1):
            print(f"{BOLD}Domanda {i}/{len(domande)}:{RESET}")
            print(f"  {q['domanda']}\n")
            for j, opz in enumerate(q["opzioni"]):
                print(f"    [{j + 1}] {opz}")

            risposta = input(f"\n  {BOLD}> Risposta (1-{len(q['opzioni'])}): {RESET}").strip()
            self.progress["quiz_total"] += 1

            try:
                idx = int(risposta) - 1
                if idx == q["corretta"]:
                    print(f"  {GREEN}{BOLD}Corretto! +10 punti{RESET}")
                    score_round += 10
                    self.progress["quiz_correct"] += 1
                    self.progress["total_score"] += 10
                else:
                    print(f"  {RED}Errato.{RESET} Corretta: {BOLD}{q['opzioni'][q['corretta']]}{RESET}")
            except (ValueError, IndexError):
                print(f"  {YELLOW}Input non valido.{RESET}")

            print(f"  {DIM}{q['spiegazione']}{RESET}\n")
            if i < len(domande):
                input(f"  {DIM}Premi INVIO per la prossima domanda...{RESET}\n")

        max_sc = len(domande) * 10
        pct    = (score_round / max_sc * 100) if max_sc > 0 else 0

        print(f"\n{'=' * 60}")
        print(f"{BOLD}Risultato Quiz:{RESET} {score_round}/{max_sc} punti ({pct:.0f}%)")
        if pct >= 90:
            print(f"{GREEN}{BOLD}Eccellente! Sei un esperto DELTA!{RESET}")
        elif pct >= 70:
            print(f"{CYAN}{BOLD}Buono! Sei pronto per operare in autonomia.{RESET}")
        elif pct >= 50:
            print(f"{YELLOW}Sufficiente. Rileggi il manuale per le parti mancanti.{RESET}")
        else:
            print(f"{RED}Insufficiente. Si consiglia di rifare il Tutorial Guidato.{RESET}")

        self._check_badges()
        self._save_progress()
        input(f"\n{DIM}Premi INVIO per tornare al menu Academy...{RESET}")

    # ─── LAB: MIGLIORAMENTO CONTINUO MODELLO ────────────────

    def _lab_miglioramento_continuo(self):
        """Percorso formativo per addestrare l'operatore al training continuo del modello."""
        print(f"\n{BOLD}{'=' * 60}{RESET}")
        print(f"{BOLD}{BLUE}  LAB MLOPS OPERATORE — MIGLIORAMENTO CONTINUO{RESET}")
        print(f"{'=' * 60}{RESET}\n")

        print("Obiettivo: imparare il ciclo completo dati -> training -> conversione -> validazione.")
        print("Checklist operativa:")
        steps = [
            "1) Qualita dati: immagini nitide, luce stabile, etichetta corretta.",
            "2) Bilanciamento classi: evitare classi con pochi campioni.",
            "3) Training Keras: monitorare val_accuracy e overfitting.",
            "4) Conversione TFLite float16 (default) o INT8 con representative dataset.",
            "5) Preflight: validare modello + labels + immagine test prima del deploy.",
            "6) Monitoraggio in campo: raccogliere casi a bassa confidenza per retraining.",
        ]
        for line in steps:
            print(f"  {line}")

        print(f"\n{BOLD}Mini verifica rapida (3 domande){RESET}")
        questions = [
            {
                "q": "Se una classe ha poche immagini rispetto alle altre, il rischio principale e...",
                "options": [
                    "A) Overfitting e bias verso classi dominanti",
                    "B) Migliore generalizzazione",
                    "C) Conversione TFLite piu veloce",
                ],
                "ok": 0,
            },
            {
                "q": "Per quantizzazione INT8 in conversione TFLite serve...",
                "options": [
                    "A) Solo il file labels.txt",
                    "B) Representative dataset con immagini reali",
                    "C) Disabilitare la validazione preflight",
                ],
                "ok": 1,
            },
            {
                "q": "Prima della messa in produzione bisogna sempre...",
                "options": [
                    "A) Usare dummy model in fallback",
                    "B) Eseguire preflight su modello, labels e immagine test",
                    "C) Aumentare i thread senza test",
                ],
                "ok": 1,
            },
        ]

        score = 0
        for i, item in enumerate(questions, 1):
            print(f"\n{BOLD}Domanda {i}:{RESET} {item['q']}")
            for idx, opt in enumerate(item["options"], 1):
                print(f"  [{idx}] {opt}")
            raw = input(f"{BOLD}> Risposta (1-3): {RESET}").strip()
            try:
                ans = int(raw) - 1
                if ans == item["ok"]:
                    score += 1
                    print(f"  {GREEN}Corretto{RESET}")
                else:
                    print(f"  {YELLOW}Non corretto{RESET}")
            except (ValueError, IndexError):
                print(f"  {YELLOW}Input non valido{RESET}")

        gained = score * 10
        self.progress["training_lab_completed"] += 1
        self.progress["training_lab_score"] += gained
        self.progress["total_score"] += gained

        print(f"\n{BOLD}Esito Lab:{RESET} {score}/3 corrette | +{gained} punti")
        print("Comandi operativi da ricordare:")
        print("  python ai/train_keras_classifier.py --dataset datasets/training --output models")
        print("  python ai/convert_keras_to_tflite.py --keras-model models/plant_disease_model.keras --output models/plant_disease_model_39classes.tflite --quantization float16")
        print("  # opzionale INT8: --quantization int8 --representative-data datasets/training")
        print("  python main.py --preflight-only --validation-image models/validation_sample.jpg")

        self._check_badges()
        self._save_progress()
        input(f"\n{DIM}Premi INVIO per tornare al menu Academy...{RESET}")

    # ─── PROGRESSO ───────────────────────────────────────────

    def _mostra_progresso(self):
        """Visualizza il progresso dell'operatore nella Academy."""
        p = self.progress
        print(f"\n{BOLD}{'=' * 60}{RESET}")
        print(f"{BOLD}{BLUE}  IL MIO PROGRESSO ACADEMY{RESET}")
        print(f"{'=' * 60}{RESET}\n")

        print(f"  {BOLD}Punteggio totale :{RESET}  {CYAN}{p['total_score']}{RESET} punti")
        print(f"  {BOLD}Sessioni avviate :{RESET}  {p['sessions']}")

        sim_pct  = (p["sim_correct"]  / p["sim_total"]  * 100) if p["sim_total"]  > 0 else 0
        quiz_pct = (p["quiz_correct"] / p["quiz_total"] * 100) if p["quiz_total"] > 0 else 0

        print(f"\n  {BOLD}Simulazioni  :{RESET} {GREEN}{p['sim_correct']}/{p['sim_total']}{RESET} "
              f"corrette ({sim_pct:.0f}%)")
        print(f"  {BOLD}Quiz Teorico :{RESET} {GREEN}{p['quiz_correct']}/{p['quiz_total']}{RESET} "
              f"corrette ({quiz_pct:.0f}%)")

        if p["badges"]:
            print(f"\n  {BOLD}Badge ottenuti:{RESET}")
            for badge in p["badges"]:
                print(f"    [*] {badge}")

        print(f"\n  {BOLD}Training continuo:{RESET} {p['training_lab_completed']} sessioni "
              f"| punteggio lab: {p['training_lab_score']}")

        # Livello operatore
        score = p["total_score"]
        if score < 50:
            level, col = "Principiante", DIM
        elif score < 150:
            level, col = "Apprendista",  CYAN
        elif score < 300:
            level, col = "Operatore",    GREEN
        elif score < 500:
            level, col = "Esperto",      YELLOW
        else:
            level, col = "Maestro DELTA","\033[93;1m"

        print(f"\n  {BOLD}Livello operatore :{RESET} {col}{level}{RESET}")
        soglie = [50, 150, 300, 500]
        next_t = next((t for t in soglie if t > score), None)
        if next_t:
            print(f"  {DIM}Mancano {next_t - score} punti al prossimo livello{RESET}")

        input(f"\n{DIM}Premi INVIO per tornare al menu Academy...{RESET}")

    # ─── HELPERS STAMPA SCENARIO ─────────────────────────────

    @staticmethod
    def _stampa_scenario(scenario: dict):
        """Stampa il quadro clinico completo dello scenario."""
        print(f"{BOLD}{CYAN}--- SCENARIO: {scenario['titolo'].upper()} ---{RESET}")
        print(f"{DIM}Contesto: {scenario['contesto']}{RESET}\n")

        print(f"{BOLD}Sintomi visivi osservati:{RESET}")
        print(f"  {scenario['sintomi_visivi']}\n")

        print(f"{BOLD}Dati sensori rilevati:{RESET}")
        print(f"  {'Parametro':<22} {'Valore':<16} Stato")
        print(f"  {'─' * 55}")
        stati = scenario.get("stato_sensori", {})
        for param, (valore, stato) in scenario["dati_sensori"].items():
            s = stati.get(param, "ok")
            col = GREEN if s == "ok" else (YELLOW if s == "warn" else RED)
            marker = "[OK]" if s == "ok" else ("[!!]" if s == "err" else "[!]")
            print(f"  {param:<22} {valore:<16} {col}{marker} {stato}{RESET}")

        print(f"\n{BOLD}Risultato AI DELTA:{RESET}")
        print(f"  Classe rilevata : {BOLD}{scenario['ai_class']}{RESET}")
        print(f"  Confidenza      : {scenario['ai_confidence']:.1f}%\n")
        print(f"  Top 3 classifiche:")
        for cls, conf in scenario["ai_top3"]:
            bar = "=" * int(conf / 5)
            marker = ">" if cls == scenario["ai_class"] else " "
            print(f"  {marker} {cls:<42} {bar} {conf:.1f}%")

    @staticmethod
    def _stampa_scenario_breve(scenario: dict):
        """Stampa una versione compatta dello scenario."""
        print(f"{BOLD}{CYAN}--- SCENARIO: {scenario['titolo'].upper()} ---{RESET}")
        print(f"\n{BOLD}Sintomi:{RESET} {scenario['sintomi_visivi'][:130]}...")

        stati = scenario.get("stato_sensori", {})
        anomalie = [
            (p, v, s)
            for p, (v, s) in scenario["dati_sensori"].items()
            if stati.get(p) in ("warn", "err")
        ]
        if anomalie:
            print(f"\n{BOLD}Parametri critici:{RESET}")
            for param, valore, stato in anomalie:
                col = YELLOW if stati.get(param) == "warn" else RED
                print(f"  {col}[!] {param}: {valore} — {stato}{RESET}")

    @staticmethod
    def _stampa_spiegazione(scenario: dict):
        """Stampa la spiegazione didattica finale dello scenario."""
        print(f"\n{BOLD}{'─' * 60}{RESET}")
        print(f"{BOLD}Spiegazione didattica:{RESET}")
        print(f"  {scenario['spiegazione_finale']}")
        print(f"\n{BOLD}Raccomandazioni complete DELTA:{RESET}")
        for r in scenario["raccomandazioni_corrette"]:
            print(f"  {GREEN}[OK]{RESET} {r}")
        print(f"{BOLD}{'─' * 60}{RESET}")

    # ─── BADGE ───────────────────────────────────────────────

    def _check_badges(self):
        """Controlla e assegna badge in base al progresso."""
        p = self.progress
        nuovi = []
        defs = [
            (p["total_score"] >= 50,   "Primo Passo — Hai guadagnato i tuoi primi 50 punti!"),
            (p["quiz_correct"] >= 5,   "Studioso — 5 domande di quiz corrette"),
            (p["sim_correct"] >= 3,    "Diagnosta — 3 simulazioni corrette"),
            (p["training_lab_completed"] >= 1, "MLOps Base — prima sessione di miglioramento continuo"),
            (p["total_score"] >= 200,  "Esperto in Formazione — 200 punti raggiunti"),
            (p["sim_correct"] >= 10,   "Agronomo Digitale — 10 simulazioni corrette"),
            (p["training_lab_completed"] >= 5, "Coach AI — 5 sessioni complete di training operatore"),
            (p["total_score"] >= 500,  "Maestro DELTA — 500 punti raggiunti"),
        ]
        for cond, badge in defs:
            if cond and badge not in p["badges"]:
                nuovi.append(badge)
        for badge in nuovi:
            p["badges"].append(badge)
            print(f"\n  {YELLOW}{BOLD}[*] NUOVO BADGE: {badge}{RESET}")
