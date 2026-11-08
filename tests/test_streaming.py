"""Streaming: il testo arriva a pezzetti dal provider, attraverso agente e API, fino al browser."""

import json
from types import SimpleNamespace as NS

import pytest
from fastapi.testclient import TestClient

from conftest import ProviderFinto, STATS, nuovo_stato, tool
from gdr.agent import Agente
from gdr.config import RADICE
from gdr.gestore import GestoreSessioni
from gdr.llm.base import RispostaLLM
from gdr.llm.ollama_provider import OllamaProvider
from gdr.web import crea_app

PROMPT = RADICE / "prompts" / "master.md"


class ProviderAPezzi(ProviderFinto):
    """Come ProviderFinto, ma con lo streaming vero: il testo arriva a pezzi da 4 caratteri."""

    def chiama_stream(self, system, messaggi, tools, su_testo):
        r = self.chiama(system, messaggi, tools)
        for i in range(0, len(r.testo), 4):
            su_testo(r.testo[i : i + 4])
        return r


def test_provider_senza_streaming_consegna_tutto_in_un_colpo():
    pezzi = []
    r = ProviderFinto(["Ciao a tutti"]).chiama_stream("s", [], [], pezzi.append)
    assert pezzi == ["Ciao a tutti"] and r.testo == "Ciao a tutti"


def test_agente_inoltra_i_pezzi_e_il_testo_finale_coincide():
    pezzi = []
    a = Agente(ProviderAPezzi(["Benvenuto, viandante."]), nuovo_stato(), PROMPT)
    assert a.turno("ciao", pezzi.append) == "Benvenuto, viandante."
    assert len(pezzi) > 1 and "".join(pezzi) == "Benvenuto, viandante."


def test_testo_prima_di_un_tool_viene_scartato():
    pezzi = []
    prov = ProviderAPezzi([])
    prov.scaletta = [RispostaLLM(testo="", chiamate_tool=[])]  # sostituita sotto
    chiamate = iter([RispostaLLM(testo="Vediamo...", chiamate_tool=[tool("leggi_scheda")]), RispostaLLM(testo="Hai una spada.")])
    prov.chiama = lambda *a: next(chiamate)
    a = Agente(prov, nuovo_stato(), PROMPT)
    assert a.turno("cosa ho?", pezzi.append) == "Hai una spada."
    assert None in pezzi  # segnale "scarta"
    dopo = pezzi[pezzi.index(None) + 1 :]
    assert "".join(dopo) == "Hai una spada."


def test_senza_callback_si_usa_la_chiamata_normale():
    prov = ProviderFinto(["ok"])
    prov.chiama_stream = lambda *a: pytest.fail("non doveva fare streaming")
    assert Agente(prov, nuovo_stato(), PROMPT).turno("x") == "ok"


def test_errore_in_streaming_annulla_il_turno():
    s = nuovo_stato()
    a = Agente(ProviderAPezzi([RuntimeError("giù")]), s, PROMPT)
    with pytest.raises(RuntimeError):
        a.turno("x", lambda p: None)
    assert s.messaggi == [] and s.turno == 0


# --- Provider Ollama con un client finto ---------------------------------------------------
def _pezzo(content="", tool_calls=None):
    return NS(message=NS(content=content, tool_calls=tool_calls, thinking=None))


def _ollama(pezzi):
    p = OllamaProvider.__new__(OllamaProvider)
    p.model, p.num_ctx = "m", 1000
    p.client = NS(chat=lambda **kw: iter(pezzi) if kw.get("stream") else pezzi[-1])
    return p


def test_ollama_stream_testo_e_tool():
    chiamata = NS(function=NS(name="leggi_scheda", arguments={}))
    ricevuti = []
    r = _ollama([_pezzo("Ve"), _pezzo("diamo"), _pezzo("", [chiamata])]).chiama_stream("s", [], [], ricevuti.append)
    assert ricevuti == ["Ve", "diamo"] and r.testo == "Vediamo"
    assert [c.nome for c in r.chiamate_tool] == ["leggi_scheda"]


def test_ollama_senza_stream_resta_uguale():
    r = _ollama([_pezzo(" ciao ")]).chiama("s", [], [])
    assert r.testo == "ciao" and not r.chiamate_tool


# --- API ---------------------------------------------------------------------------------------
def _eventi(risposta):
    assert risposta.status_code == 200, risposta.text
    return [json.loads(r) for r in risposta.text.splitlines() if r.strip()]


@pytest.fixture
def client(cfg):
    prov = ProviderAPezzi(["Apertura della storia.", "Saluti, viandante!"])
    c = TestClient(crea_app(cfg, GestoreSessioni(cfg, provider=prov)))
    assert c.post("/api/registrati", json={"nome": "alice", "password": "password123", "codice": "segreto123"}).status_code == 200
    c.post("/api/partite/acquaverde/nuova", json={"nome": "Aldo", "classe": "Guerriero", "valori": STATS})
    return c


def test_api_stream_pezzi_e_fine(client):
    ev = _eventi(client.post("/api/partite/acquaverde/inizia-stream"))
    assert "".join(e["t"] for e in ev if e["tipo"] == "testo") == "Apertura della storia."
    assert ev[-1]["tipo"] == "fine" and ev[-1]["esito"]["narrazione"] == "Apertura della storia."
    assert ev[-1]["esito"]["vista"]["avventura"]["id"] == "acquaverde"
    ev = _eventi(client.post("/api/partite/acquaverde/turno-stream", json={"testo": "Saluto"}))
    assert ev[-1]["esito"]["narrazione"] == "Saluti, viandante!"
    assert client.post("/api/partite/acquaverde/continua").json()["vista"]["puo_annullare"]  # lo streaming salva e permette l'annulla


def test_api_stream_errori_prima_dello_stream(client, cfg):
    assert client.post("/api/partite/acquaverde/turno-stream", json={"testo": " "}).status_code == 400
    assert TestClient(client.app).post("/api/partite/acquaverde/turno-stream", json={"testo": "x"}).status_code == 401
    assert client.post("/api/partite/marenza/inizia-stream").status_code == 409  # nessuna partita


def test_api_stream_errore_del_modello_diventa_evento(cfg):
    prov = ProviderAPezzi([RuntimeError("ollama spento")])
    c = TestClient(crea_app(cfg, GestoreSessioni(cfg, provider=prov)))
    c.post("/api/registrati", json={"nome": "bob", "password": "password123", "codice": "segreto123"})
    c.post("/api/partite/acquaverde/nuova", json={"nome": "Aldo", "classe": "Guerriero", "valori": STATS})
    ev = _eventi(c.post("/api/partite/acquaverde/inizia-stream"))
    assert ev[-1]["tipo"] == "errore" and ev[-1]["stato"] == 502 and "ollama spento" in ev[-1]["detail"]


def test_api_stream_dettagli_tool_solo_admin(cfg):
    for nome, atteso in [("alice", True), ("bob", False)]:
        prov = ProviderAPezzi([[tool("leggi_scheda")], "ok"])
        c = TestClient(crea_app(cfg, GestoreSessioni(cfg, provider=prov)))
        c.post("/api/registrati", json={"nome": nome, "password": "password123", "codice": "segreto123"})
        c.post("/api/partite/acquaverde/nuova", json={"nome": "Aldo", "classe": "Guerriero", "valori": STATS})
        ev = _eventi(c.post("/api/partite/acquaverde/turno-stream", json={"testo": "x"}))
        assert bool(ev[-1]["esito"]["tool"]) is atteso
