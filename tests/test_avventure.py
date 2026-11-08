"""Le tre avventure: dati coerenti e finali tutti raggiungibili giocando davvero."""

from collections import deque

import pytest

from conftest import nuovo_stato
from gdr.tools import Strumenti
from verifica_avventure import verifica


def test_dati_coerenti(avventura):
    errori, _avvisi = verifica(avventura)
    assert errori == []


def test_il_catalogo_trova_le_tre_avventure(catalogo):
    assert set(catalogo.ids()) >= {"acquaverde", "vallombra", "marenza"}
    assert catalogo.ottieni("../etc") is None and catalogo.ottieni("nonesiste") is None


def test_ogni_luogo_ha_un_solo_ingresso_sempre_aperto(avventura):
    for lid in avventura.luoghi:
        zone = avventura.zone(lid)
        assert sum(1 for z in zone if z.get("ingresso")) == 1
        ing = avventura.ingresso(lid)
        assert not ing.get("orari") and not ing.get("richiede_flag")


def test_il_riassunto_per_il_prompt_non_svela_i_segreti(avventura):
    s = nuovo_stato(avventura)
    testo = avventura.riassunto_prompt(s)
    for p in avventura.png.values():
        if p.get("segreto"):
            assert p["segreto"] not in testo


# --- Finali: per ogni avventura, un percorso di flag che porta a ciascun finale ---------
SCENARI = {
    "acquaverde": {
        "nuovo_patto": ["contratto_trovato", "patto_rinnovato"],
        "liberazione": ["pietra_recuperata", "paratoie_aperte"],
        "diga_rinforzata": ["diga_rinforzata"],
        "evacuazione": ["borgo_evacuato"],
        "l_acqua_si_prende_tutto": [],
    },
    "vallombra": {
        "L'Alba Senza Pastore": ["diario_trovato", "cripta_aperta", "nome_scoperto", "sale_ottenuto"],
        "La Verità sul Sagrato": ["verita_scoperta", "costanza_alleata", "diario_trovato"],
        "La Fuga nella Notte": ["verita_scoperta", "via_di_fuga"],
        "L'Ospite Gradito": ["verita_scoperta", "sostituto_offerto"],
        "L'Ultimo Ospite": [],
    },
    "marenza": {
        "Il Lume Torna a Casa": ["tempio_ispezionato", "testimone_barcaiolo", "pico_trovato", "lume_convinto"],
        "La Lanterna Libera": ["testimone_barcaiolo", "pico_trovato", "lume_liberato"],
        "La Copia che Brilla": ["copia_scoperta", "contessa_smascherata"],
        "Il Colpevole Sbagliato": ["accusa_pubblica"],
        "La Nebbia Grigia": [],
    },
}


def _cammina(t, s, m, luogo_id, zona_id):
    """Percorso più breve fino al luogo, poi entra nella zona aspettando che apra (se ha un orario)."""
    q, prev = deque([s.luogo_id]), {s.luogo_id: None}
    while q:
        x = q.popleft()
        for y in m.raggiungibili(x):
            if y not in prev:
                prev[y] = x
                q.append(y)
    path, x = [], luogo_id
    while x != s.luogo_id:
        path.append(x)
        x = prev[x]
    for l in reversed(path):
        assert t.esegui("sposta_in", {"luogo": m.luoghi[l]["nome"]})["ok"]
    z = m.zona(luogo_id, zona_id)
    for _ in range(30):
        r = t.esegui("sposta_in", {"luogo": z["nome"]})
        if r["ok"]:
            return
        assert z.get("orari"), r  # se il blocco non è un orario, è un errore dei dati
        t.esegui("avanza_tempo", {"ore": 1})
    raise AssertionError(f"non riesco a entrare in {zona_id}: {r}")


def _gioca(m, flags):
    s = nuovo_stato(m)
    t = Strumenti(s, mondo=m)
    for f in flags:
        r = m.prove_flag[f]
        if r.get("zona"):
            _cammina(t, s, m, r["luogo"], r["zona"])
        elif s.luogo_id != r["luogo"]:
            _cammina(t, s, m, r["luogo"], m.ingresso(r["luogo"])["id"])
        if r.get("richiede_oggetto"):  # il giocatore se lo procura nel gioco
            s.personaggio.inventario.append(r["richiede_oggetto"])
        t.ultima_prova = {"statistica": r["statistica"], "cd": r["cd"], "successo": True}
        res = t.esegui("imposta_flag", {"flag": f})
        assert res["ok"], (f, res)
    s.ore_totali = m.ore_finali
    return t.esegui("valuta_finale", {})


def _casi():
    for avv, scen in SCENARI.items():
        for atteso, flags in scen.items():
            yield pytest.param(avv, atteso, flags, id=f"{avv}-{atteso}")


@pytest.mark.parametrize("avv,atteso,flags", list(_casi()))
def test_finale_raggiungibile(catalogo, avv, atteso, flags):
    m = catalogo.ottieni(avv)
    r = _gioca(m, flags)
    assert r["ok"]
    nomi = {f["id"]: f["nome"] for f in m.finali}
    assert r["finale"] == nomi.get(atteso, atteso)  # la chiave è l'id oppure il nome del finale


@pytest.mark.parametrize("avv", list(SCENARI))
def test_gli_scenari_coprono_tutti_i_finali(catalogo, avv):
    m = catalogo.ottieni(avv)
    previsti = set(SCENARI[avv])
    assert all(f["id"] in previsti or f["nome"] in previsti for f in m.finali)
