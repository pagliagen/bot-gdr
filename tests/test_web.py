"""API web: login, isolamento tra utenti, sicurezza."""

import pytest
from fastapi.testclient import TestClient

from conftest import ProviderFinto, STATS, tool
from gdr.gestore import GestoreSessioni
from gdr.web import crea_app

NUOVA = {"nome": "Aldo", "classe": "Guerriero", "valori": STATS}
PW = "password123"


@pytest.fixture
def provider():
    return ProviderFinto()


@pytest.fixture
def app(cfg, provider):
    return crea_app(cfg, GestoreSessioni(cfg, provider=provider))


@pytest.fixture
def anon(app):
    return TestClient(app)


def accedi(app, nome):
    c = TestClient(app)
    r = c.post("/api/registrati", json={"nome": nome, "password": PW, "codice": "segreto123"})
    assert r.status_code == 200, r.text
    return c


@pytest.fixture
def alice(app):
    return accedi(app, "alice")


@pytest.fixture
def bob(app):
    return accedi(app, "bob")


# --- Accesso -----------------------------------------------------------------------
def test_anonimo_non_entra(anon):
    assert anon.get("/api/avventure").status_code == 401
    assert anon.post("/api/partite/acquaverde/turno", json={"testo": "x"}).status_code == 401
    assert anon.get("/api/io").json()["utente"] is None


def test_registrazione_richiede_il_codice(anon):
    r = anon.post("/api/registrati", json={"nome": "alice", "password": PW, "codice": "no"})
    assert r.status_code == 403


def test_registrazione_chiusa_senza_codice_in_config(cfg, provider):
    import dataclasses

    c = TestClient(crea_app(dataclasses.replace(cfg, codice_invito=None), GestoreSessioni(cfg, provider=provider)))
    assert c.post("/api/registrati", json={"nome": "alice", "password": PW, "codice": ""}).status_code == 403
    assert c.get("/api/io").json()["registrazione_aperta"] is False


def test_registrazione_limitata_per_ip(anon):
    codici = [anon.post("/api/registrati", json={"nome": "alice", "password": PW, "codice": "x"}).status_code for _ in range(7)]
    assert codici[:5] == [403] * 5 and codici[5] == 429


def test_nome_malevolo_e_duplicati(anon, alice):
    assert anon.post("/api/registrati", json={"nome": "../x", "password": PW, "codice": "segreto123"}).status_code == 400
    assert anon.post("/api/registrati", json={"nome": "alice", "password": PW, "codice": "segreto123"}).status_code == 400


def test_login_logout(alice):
    assert alice.get("/api/io").json()["utente"] == "alice"
    alice.post("/api/esci")
    assert alice.get("/api/io").json()["utente"] is None
    assert alice.post("/api/accedi", json={"nome": "alice", "password": "sbagliata1"}).status_code == 401
    assert alice.post("/api/accedi", json={"nome": "alice", "password": PW}).status_code == 200
    assert alice.get("/api/io").json()["utente"] == "alice"


def test_cookie_httponly(app):
    c = TestClient(app)
    r = c.post("/api/registrati", json={"nome": "alice", "password": PW, "codice": "segreto123"})
    assert "httponly" in r.headers["set-cookie"].lower()


def test_admin_solo_da_config(alice, bob):
    assert alice.get("/api/io").json()["admin"] is True and bob.get("/api/io").json()["admin"] is False


# --- Partite ---------------------------------------------------------------------------
def test_elenco_avventure(alice):
    ids = {a["id"] for a in alice.get("/api/avventure").json()["avventure"]}
    assert {"acquaverde", "vallombra", "marenza"} <= ids


def test_continua_senza_partita(alice):
    assert alice.post("/api/partite/acquaverde/continua").status_code == 409


def test_nuova_partita_e_turno(alice):
    r = alice.post("/api/partite/marenza/nuova", json=NUOVA)
    assert r.status_code == 200 and r.json()["vista"]["avventura"]["id"] == "marenza"
    r = alice.post("/api/partite/marenza/inizia")
    assert r.status_code == 200 and r.json()["narrazione"]
    r = alice.post("/api/partite/marenza/turno", json={"testo": "Mi guardo intorno"})
    assert r.status_code == 200
    assert alice.post("/api/partite/marenza/continua").json()["vista"]["personaggio"]["nome"] == "Aldo"


def test_nuova_partita_non_valida(alice):
    r = alice.post("/api/partite/acquaverde/nuova", json={**NUOVA, "classe": "Bardo"})
    assert r.status_code == 400


def test_turno_vuoto_e_troppo_lungo(alice):
    alice.post("/api/partite/acquaverde/nuova", json=NUOVA)
    assert alice.post("/api/partite/acquaverde/turno", json={"testo": "   "}).status_code == 400
    assert alice.post("/api/partite/acquaverde/turno", json={"testo": "x" * 1001}).status_code == 422


def test_utenti_isolati(alice, bob):
    alice.post("/api/partite/acquaverde/nuova", json=NUOVA)
    assert bob.post("/api/partite/acquaverde/continua").status_code == 409
    bob.post("/api/partite/acquaverde/nuova", json={**NUOVA, "nome": "Bea"})
    assert alice.post("/api/partite/acquaverde/continua").json()["vista"]["personaggio"]["nome"] == "Aldo"
    assert bob.post("/api/partite/acquaverde/continua").json()["vista"]["personaggio"]["nome"] == "Bea"
    assert alice.get("/api/avventure").json()["avventure"][0]["salvataggio"]["personaggio"] == "Aldo"


@pytest.mark.parametrize("avv", ["nonesiste", "..%2F..%2Fetc", "%2e%2e", "ACQUAVERDE"])
def test_avventura_inesistente(alice, avv):
    assert alice.post(f"/api/partite/{avv}/continua").status_code in (404, 405)


def test_errore_del_modello_diventa_502(cfg):
    prov = ProviderFinto([RuntimeError("ollama spento")])
    c = accedi(crea_app(cfg, GestoreSessioni(cfg, provider=prov)), "alice")
    c.post("/api/partite/acquaverde/nuova", json=NUOVA)
    assert c.post("/api/partite/acquaverde/turno", json={"testo": "ciao"}).status_code == 502


def test_dettaglio_tool_solo_per_admin(cfg):
    def giro():
        return ProviderFinto([[tool("leggi_scheda")], "ok"])

    for nome, atteso in [("alice", True), ("bob", False)]:
        c = accedi(crea_app(cfg, GestoreSessioni(cfg, provider=giro())), nome)
        c.post("/api/partite/acquaverde/nuova", json=NUOVA)
        assert bool(c.post("/api/partite/acquaverde/turno", json={"testo": "x"}).json()["tool"]) is atteso


# --- File statici e intestazioni --------------------------------------------------------
def test_immagini_si_ma_yaml_e_saves_no(anon):
    assert anon.get("/avventure/acquaverde/assets/mappa.webp").status_code == 200
    for percorso in ["/avventure/acquaverde/png.yaml", "/avventure/acquaverde/assets/../png.yaml", "/saves/utenti.json", "/gdr/web.py", "/.env"]:
        assert anon.get(percorso).status_code == 404, percorso


def test_pagina_e_intestazioni_di_sicurezza(anon):
    r = anon.get("/")
    assert r.status_code == 200
    assert r.headers["x-frame-options"] == "DENY" and "default-src 'self'" in r.headers["content-security-policy"]
    assert anon.get("/api/io").headers["cache-control"] == "no-store"


def test_documentazione_api_spenta(anon):
    assert anon.get("/docs").status_code == 404 and anon.get("/openapi.json").status_code == 404


# --- Annulla ----------------------------------------------------------------------------
def test_annulla_via_api(alice):
    alice.post("/api/partite/acquaverde/nuova", json=NUOVA)
    alice.post("/api/partite/acquaverde/inizia")
    assert alice.post("/api/partite/acquaverde/turno", json={"testo": "Saluto"}).json()["vista"]["puo_annullare"]
    r = alice.post("/api/partite/acquaverde/annulla")
    assert r.status_code == 200 and r.json()["testo"] == "Saluto" and not r.json()["vista"]["puo_annullare"]
    assert alice.post("/api/partite/acquaverde/annulla").status_code == 409  # niente più da annullare


def test_annulla_senza_partita_o_senza_login(alice, anon):
    assert alice.post("/api/partite/acquaverde/annulla").status_code == 409
    assert anon.post("/api/partite/acquaverde/annulla").status_code == 401


def test_annulla_non_tocca_la_partita_di_un_altro(alice, bob):
    for c in (alice, bob):
        c.post("/api/partite/acquaverde/nuova", json=NUOVA)
        c.post("/api/partite/acquaverde/inizia")
        c.post("/api/partite/acquaverde/turno", json={"testo": "uno"})
    alice.post("/api/partite/acquaverde/annulla")
    assert bob.post("/api/partite/acquaverde/continua").json()["vista"]["puo_annullare"]
