import pytest

from gdr import state
from gdr.character_creation import CLASSI, crea_personaggio
from gdr.memory import comprimi_se_serve, costruisci_system
from gdr.models import StatoPartita

from conftest import STATS, nuovo_stato


@pytest.mark.parametrize("classe", list(CLASSI))
def test_creazione_valida(classe):
    p = crea_personaggio("Aldo", classe, STATS)
    assert p.pf == p.pf_max == CLASSI[classe]["dado_vita"] + 2
    assert p.inventario == CLASSI[classe]["equipaggiamento"]


@pytest.mark.parametrize(
    "nome,classe,valori",
    [
        ("", "Guerriero", STATS),
        ("x" * 31, "Guerriero", STATS),
        ("Aldo", "Bardo", STATS),
        ("Aldo", "Guerriero", {"forza": 18, "agilita": 13, "intelletto": 10}),
        ("Aldo", "Guerriero", {"forza": 15, "agilita": 13}),
    ],
)
def test_creazione_non_valida(nome, classe, valori):
    with pytest.raises(ValueError):
        crea_personaggio(nome, classe, valori)


def test_salvataggio_roundtrip(tmp_path, mondo):
    s = nuovo_stato(mondo)
    s.diario.append("nota")
    s.flag["x"] = True
    s.messaggi.append({"role": "user", "content": "ciao"})
    f = tmp_path / "sotto" / "p.json"
    state.salva(s, f)
    assert not list(f.parent.glob("*.tmp"))
    assert state.carica(f) == s


def test_carica_file_inesistente(tmp_path):
    assert state.carica(tmp_path / "no.json") is None


def test_tempo_derivato():
    s = nuovo_stato()
    s.ore_totali = 24 * 2 + 5
    assert (s.giorno, s.ora) == (3, 5)


def test_system_contiene_stato_e_diario(stato, mondo):
    stato.diario.append("Ho incontrato Tobia")
    sp = costruisci_system("PROMPT", stato, mondo)
    assert sp.startswith("PROMPT") and "Ho incontrato Tobia" in sp and "Aldo" in sp and "Pontevecchio" in sp


def test_system_limita_il_diario(stato):
    stato.diario = [f"voce{i}" for i in range(200)]
    sp = costruisci_system("P", stato)
    assert "voce199" in sp and "voce0\n" not in sp


def _chat(n):
    out = []
    for i in range(n):
        out.append({"role": "user", "content": f"u{i}"})
        out.append({"role": "assistant", "content": [{"type": "tool_use", "id": str(i), "name": "x", "input": {}}]})
        out.append({"role": "user", "content": [{"type": "tool_result", "tool_use_id": str(i), "content": "{}"}]})
        out.append({"role": "assistant", "content": f"a{i}"})
    return out


def test_compressione_non_spezza_i_tool():
    s = nuovo_stato()
    s.messaggi = _chat(20)
    assert comprimi_se_serve(s, soglia=40, recenti=12)
    assert len(s.messaggi) < 80
    primo = s.messaggi[0]
    assert primo["role"] == "user" and isinstance(primo["content"], str)  # mai un tool_result orfano


def test_nessuna_compressione_sotto_soglia():
    s = nuovo_stato()
    s.messaggi = _chat(3)
    assert not comprimi_se_serve(s, soglia=40, recenti=12)
