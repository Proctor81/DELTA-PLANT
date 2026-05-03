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
            "L'etichetta fornita dall'operatore viene usata per il futuro fine-tuning del modello."
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
        "domanda": "Qual e lo scopo principale del fine-tuning del modello AI in DELTA?",
        "opzioni": [
            "Aumentare la velocita di acquisizione delle immagini",
            "Adattare il modello alle specie e condizioni locali specifiche",
            "Aggiornare il firmware dell'AI HAT 2+",
            "Ridurre il consumo energetico del Raspberry Pi",
        ],
        "corretta": 1,
        "spiegazione": (
            "Il fine-tuning specializza il modello pre-addestrato per le varieta locali, "
            "le condizioni di luce specifiche e le patologie piu comuni "
            "nell'area geografica dell'utente."
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
                "  [2] Fine-tuning AI       — migliora il modello con nuovi dati\n"
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
