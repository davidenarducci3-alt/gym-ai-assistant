"""Catalogo di query predefinite, parametrizzate e di SOLA LETTURA.
L'LLM non scrive mai SQL: sceglie solo uno strumento tra quelli di TOOLS."""
import sqlite3
from pathlib import Path

BASE = Path(__file__).parent
DB_PATH = BASE / "gym.db"


def init_db(force=False):
    if DB_PATH.exists() and not force:
        return
    DB_PATH.unlink(missing_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.executescript((BASE / "schema.sql").read_text(encoding="utf-8"))
    con.commit()
    con.close()


def get_conn():
    """Connessione in sola lettura: anche un bug non potrebbe modificare i dati."""
    con = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    return con


def _q(con, sql, params=None):
    return [dict(r) for r in con.execute(sql, params or {}).fetchall()]


def _period(args):
    return {"dal": args.get("dal"), "al": args.get("al")}


PERIOD_SCHEMA = {
    "dal": {"type": "string", "description": "Data iniziale (YYYY-MM-DD), opzionale"},
    "al": {"type": "string", "description": "Data finale (YYYY-MM-DD), opzionale"},
}
NO_ARGS = {}


def conta_utenti(con, a):
    return _q(con, "SELECT COUNT(*) AS utenti FROM UTENTI")[0]


def utenti_per_abbonamento(con, a):
    return _q(con, """SELECT ab.TIPOLOGIA AS tipologia, COUNT(*) AS utenti FROM UTENTI u
                      JOIN ABBONAMENTI ab ON ab.ID = u.ABBONAMENTO GROUP BY ab.TIPOLOGIA ORDER BY utenti DESC""")


def elenco_abbonamenti(con, a):
    return _q(con, "SELECT TIPOLOGIA AS tipologia, DURATA AS durata, COSTO_EUR AS costo_eur FROM ABBONAMENTI")


def elenco_pacchetti_fisio(con, a):
    return _q(con, "SELECT TIPOLOGIA AS tipologia, COSTO AS costo_eur FROM PACCHETTI_FISIOTERAPIA ORDER BY CAST(ID AS INT)")


def prenotazioni_pacchetti_fisio(con, a):
    return _q(con, """SELECT p.TIPOLOGIA AS pacchetto, COUNT(*) AS prenotazioni FROM PRENOTA pr
                      JOIN PACCHETTI_FISIOTERAPIA p ON p.ID = pr.PACCHETTO_FISIO GROUP BY p.ID""")


def elenco_articoli_shop(con, a):
    return _q(con, "SELECT NOME AS articolo, TAGLIA AS taglia, PREZZO AS prezzo_eur, QUANT_DISPONIBILE AS disponibili FROM ARTICOLI")


def articoli_piu_venduti(con, a):
    return _q(con, """SELECT r.NOME AS articolo, SUM(a.QUANTITA) AS pezzi_venduti FROM ACQUISTI a
                      JOIN ARTICOLI r ON r.CODICE = a.ARTICOLO GROUP BY r.CODICE ORDER BY pezzi_venduti DESC""")


def riepilogo_vendite_shop(con, a):
    return _q(con, """SELECT COUNT(*) AS acquisti, COALESCE(SUM(a.QUANTITA),0) AS pezzi,
                      COALESCE(SUM(a.QUANTITA * r.PREZZO),0) AS incasso_eur FROM ACQUISTI a
                      JOIN ARTICOLI r ON r.CODICE = a.ARTICOLO
                      WHERE (:dal IS NULL OR a.DATA >= :dal) AND (:al IS NULL OR a.DATA <= :al)""", _period(a))[0]


def riepilogo_consulenze_fisio(con, a):
    righe = _q(con, """SELECT DATA AS data, COUNT(*) AS consulenze FROM CONSULENZA_FISIO
                       WHERE (:dal IS NULL OR DATA >= :dal) AND (:al IS NULL OR DATA <= :al)
                       GROUP BY DATA ORDER BY DATA""", _period(a))
    return {"totale": sum(r["consulenze"] for r in righe), "per_data": righe}


def riepilogo_lezioni_personal(con, a):
    return _q(con, """SELECT COUNT(*) AS lezioni,
                      ROUND(COALESCE(SUM((julianday('2000-01-01 '||ORA_FINE) - julianday('2000-01-01 '||ORA_INIZIO))*24),0),1) AS ore,
                      COALESCE(SUM(COSTO_EUR),0) AS incasso_eur FROM RICHIEDERE_PERSONAL
                      WHERE (:dal IS NULL OR DATA >= :dal) AND (:al IS NULL OR DATA <= :al)""", _period(a))[0]


def statistiche_utenti(con, a):
    s = _q(con, "SELECT COUNT(*) AS utenti, ROUND(AVG(ETA),1) AS eta_media, MIN(ETA) AS eta_min, MAX(ETA) AS eta_max FROM UTENTI")[0]
    s["per_citta"] = _q(con, "SELECT CITTA AS citta, COUNT(*) AS utenti FROM UTENTI GROUP BY CITTA")
    return s


def statistiche_dipendenti(con, a):
    return _q(con, """SELECT COUNT(*) AS dipendenti, ROUND(AVG(ETA),1) AS eta_media,
                      MAX(DATA_ASSUNZIONE) AS assunzione_piu_recente FROM DIPENDENTI""")[0]


# nome -> (descrizione per l'LLM, proprietà input, funzione)
TOOLS = {
    "conta_utenti": ("Numero totale di utenti registrati.", NO_ARGS, conta_utenti),
    "utenti_per_abbonamento": ("Utenti raggruppati per tipologia di abbonamento.", NO_ARGS, utenti_per_abbonamento),
    "elenco_abbonamenti": ("Tipologie di abbonamento con durata e costo.", NO_ARGS, elenco_abbonamenti),
    "elenco_pacchetti_fisio": ("Pacchetti di fisioterapia con costo.", NO_ARGS, elenco_pacchetti_fisio),
    "prenotazioni_pacchetti_fisio": ("Numero di prenotazioni per pacchetto di fisioterapia.", NO_ARGS, prenotazioni_pacchetti_fisio),
    "elenco_articoli_shop": ("Articoli dello shop con taglie, prezzi e disponibilità.", NO_ARGS, elenco_articoli_shop),
    "articoli_piu_venduti": ("Classifica degli articoli per pezzi venduti.", NO_ARGS, articoli_piu_venduti),
    "riepilogo_vendite_shop": ("Numero acquisti, pezzi venduti e incasso dello shop, con periodo opzionale.", PERIOD_SCHEMA, riepilogo_vendite_shop),
    "riepilogo_consulenze_fisio": ("Numero di consulenze di fisioterapia e date, con periodo opzionale.", PERIOD_SCHEMA, riepilogo_consulenze_fisio),
    "riepilogo_lezioni_personal": ("Lezioni con personal trainer: numero, ore e incasso, con periodo opzionale.", PERIOD_SCHEMA, riepilogo_lezioni_personal),
    "statistiche_utenti": ("Età media/min/max degli utenti e utenti per città.", NO_ARGS, statistiche_utenti),
    "statistiche_dipendenti": ("Numero di dipendenti, età media, data di assunzione più recente.", NO_ARGS, statistiche_dipendenti),
}


def anthropic_tool_defs():
    return [{"name": n, "description": d,
             "input_schema": {"type": "object", "properties": p}} for n, (d, p, _) in TOOLS.items()]


def run_tool(name, args):
    if name not in TOOLS:
        return {"errore": "Strumento non autorizzato"}
    con = get_conn()
    try:
        return TOOLS[name][2](con, args or {})
    except Exception as e:  # il dettaglio resta nei log, non nella risposta
        print(f"[tool error] {name}: {e}")
        return {"errore": "Impossibile completare la richiesta"}
    finally:
        con.close()
