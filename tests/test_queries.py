import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import queries

PII = ("cognome", "email", "iban", "telefono", "via ")


class TestQueries(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        queries.init_db(force=True)

    def test_conta_utenti(self):
        self.assertEqual(queries.run_tool("conta_utenti", {})["utenti"], 5)

    def test_utenti_per_abbonamento(self):
        r = {x["tipologia"]: x["utenti"] for x in queries.run_tool("utenti_per_abbonamento", {})}
        self.assertEqual(r, {"SALA PESI": 2, "CORSI": 1, "FISIOTERAPIA": 2})

    def test_articolo_piu_venduto(self):
        top = queries.run_tool("articoli_piu_venduti", {})[0]
        self.assertEqual((top["articolo"], top["pezzi_venduti"]), ("POLSINI", 4))

    def test_incasso_shop(self):
        self.assertEqual(queries.run_tool("riepilogo_vendite_shop", {})["incasso_eur"], 95)

    def test_filtro_periodo(self):
        r = queries.run_tool("riepilogo_vendite_shop", {"dal": "2022-07-19", "al": "2022-07-20"})
        self.assertEqual((r["acquisti"], r["incasso_eur"]), (2, 54))

    def test_consulenze_e_personal(self):
        self.assertEqual(queries.run_tool("riepilogo_consulenze_fisio", {})["totale"], 2)
        p = queries.run_tool("riepilogo_lezioni_personal", {})
        self.assertEqual((p["lezioni"], p["ore"], p["incasso_eur"]), (2, 3.0, 70))

    def test_statistiche(self):
        self.assertEqual(queries.run_tool("statistiche_utenti", {})["eta_media"], 31.8)
        d = queries.run_tool("statistiche_dipendenti", {})
        self.assertEqual((d["dipendenti"], d["assunzione_piu_recente"]), (5, "2022-04-22"))

    def test_nessun_dato_personale(self):
        for name in queries.TOOLS:
            out = str(queries.run_tool(name, {})).lower()
            for p in PII:
                self.assertNotIn(p, out, f"{name} espone {p}")

    def test_strumento_sconosciuto(self):
        self.assertIn("errore", queries.run_tool("DROP TABLE UTENTI", {}))

    def test_db_sola_lettura(self):
        con = queries.get_conn()
        with self.assertRaises(Exception):
            con.execute("DELETE FROM UTENTI")
        con.close()


if __name__ == "__main__":
    unittest.main()
