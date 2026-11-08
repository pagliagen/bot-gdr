"""Zone, orari di apertura, routine dei PNG e viaggi."""

from conftest import nuovo_stato
from gdr.tools import Strumenti


def test_zone_a_orario_chiusa_poi_aperta(strumenti, stato):
    r = strumenti.esegui("sposta_in", {"luogo": "Locanda del Pesce Pigro"})
    assert not r["ok"] and "10:00" in r["errore"]  # alle 08:00 è chiusa
    strumenti.esegui("avanza_tempo", {"ore": 2})
    assert strumenti.esegui("sposta_in", {"luogo": "Locanda del Pesce Pigro"})["ok"]


def test_spostamento_tra_zone_costa_zero(strumenti, stato):
    r = strumenti.esegui("sposta_in", {"luogo": "emporio"})
    assert r["ok"] and r["ore_viaggio"] == 0 and stato.ora == 8 and stato.zona_id == "emporio"


def test_la_zona_chiude_con_dentro_il_giocatore(strumenti, stato):
    strumenti.esegui("avanza_tempo", {"ore": 2})
    strumenti.esegui("sposta_in", {"luogo": "Locanda del Pesce Pigro"})
    r = strumenti.esegui("avanza_tempo", {"ore": 16})  # 02:00: la locanda ha chiuso
    assert "zona_chiusa" in r and stato.zona_id == "piazza"


def test_viaggio_costa_ore_e_arriva_all_ingresso(strumenti, stato, mondo):
    r = strumenti.esegui("sposta_in", {"luogo": "Mulino Alto"})
    assert r["ok"] and r["ore_viaggio"] > 0
    assert stato.luogo_id == "mulino_alto" and stato.zona_id == mondo.ingresso("mulino_alto")["id"]


def test_zona_di_un_altro_luogo_rifiutata(strumenti, stato):
    strumenti.esegui("sposta_in", {"luogo": "Mulino Alto"})
    assert not strumenti.esegui("sposta_in", {"luogo": "emporio"})["ok"]


def test_luogo_non_collegato_rifiutato(strumenti):
    assert not strumenti.esegui("sposta_in", {"luogo": "Il Regno di Oz"})["ok"]


def test_mappa_mostra_le_zone(strumenti):
    r = strumenti.esegui("descrivi_mappa", {})
    assert r["ok"] and r["zone_del_luogo"]


def test_assicura_zona_per_salvataggi_vecchi(mondo):
    s = nuovo_stato(mondo)
    s.zona_id = ""
    mondo.assicura_zona(s)
    assert s.zona_id == mondo.ingresso(s.luogo_id)["id"]


def test_png_assente_non_e_nella_scena(mondo):
    """Ogni PNG compare solo nella zona dove sta a quell'ora."""
    for p in mondo.png.values():
        for ora in range(24):
            z = mondo.zona_png(p, ora)
            presenti = [n["id"] for n in mondo.png_presenti(p["luogo"], z, ora)] if z else []
            assert (p["id"] in presenti) == bool(z)
