"""Il ciclo dell'agente con un modello finto."""

import json
from pathlib import Path

import pytest

from conftest import ProviderFinto, nuovo_stato, tool
from gdr.agent import Agente
from gdr.config import RADICE

PROMPT = RADICE / "prompts" / "master.md"


def agente(scaletta, mondo=None, **kw):
    s = nuovo_stato(mondo)
    prov = ProviderFinto(scaletta)
    return Agente(prov, s, PROMPT, mondo=mondo, **kw), s, prov


def test_risposta_semplice():
    a, s, _ = agente(["Benvenuto!"])
    assert a.turno("ciao") == "Benvenuto!"
    assert s.turno == 1 and s.messaggi[-1] == {"role": "assistant", "content": "Benvenuto!"}


def test_ciclo_con_tool_e_risultato_al_modello():
    a, s, prov = agente([[tool("leggi_scheda")], "Hai la spada."])
    eventi = []
    a.su_evento = lambda t, d: eventi.append(t)
    assert a.turno("cosa ho?") == "Hai la spada."
    assert eventi == ["tool_call", "tool_result"]
    ultimo = prov.chiamate[1]["messaggi"][-1]
    assert ultimo["role"] == "user" and ultimo["content"][0]["type"] == "tool_result"
    assert "spada lunga" in ultimo["content"][0]["content"]


def test_piu_tool_nello_stesso_giro_un_solo_messaggio_di_risultati():
    a, s, prov = agente([[tool("leggi_scheda", id="a"), tool("inventario", id="b", azione="elenca")], "ok"])
    a.turno("x")
    risultati = prov.chiamate[1]["messaggi"][-1]["content"]
    assert [r["tool_use_id"] for r in risultati] == ["a", "b"]


def test_errore_del_tool_torna_al_modello_senza_rompere():
    a, s, prov = agente([[tool("tira_dadi", formula="boh", motivo="x")], "Ritiro."])
    assert a.turno("tiro") == "Ritiro."
    r = prov.chiamate[1]["messaggi"][-1]["content"][0]
    assert r["is_error"] and not json.loads(r["content"])["ok"]


def test_errore_del_provider_annulla_il_turno():
    a, s, _ = agente([RuntimeError("rete giù")])
    with pytest.raises(RuntimeError):
        a.turno("ciao")
    assert s.turno == 0 and s.messaggi == []


def test_errore_dopo_un_tool_annulla_tutto_il_turno():
    a, s, _ = agente([[tool("scrivi_diario", evento="x")], RuntimeError("giù")])
    with pytest.raises(RuntimeError):
        a.turno("ciao")
    assert s.messaggi == [] and s.turno == 0


def test_limite_iterazioni():
    a, s, _ = agente([[tool("leggi_scheda")]] * 10, max_iterazioni=3)
    assert "perde il filo" in a.turno("x")
    assert s.messaggi[-1]["role"] == "assistant"


def test_risposta_vuota_ha_un_testo_di_riserva():
    a, s, _ = agente([""])
    assert "silenzio" in a.turno("x")


def test_il_prompt_arriva_al_modello_con_lo_stato(mondo):
    a, s, prov = agente(["ok"], mondo=mondo)
    a.turno("x")
    assert "Aldo" in prov.chiamate[0]["system"] and "Pontevecchio" in prov.chiamate[0]["system"]
