"""I tool: l'arbitro del gioco. Non devono mai sollevare eccezioni verso l'agente."""

import pytest

from conftest import nuovo_stato


def test_tool_inesistente_e_argomenti_sbagliati(strumenti):
    assert not strumenti.esegui("vola", {})["ok"]
    assert not strumenti.esegui("tira_dadi", "no")["ok"]
    assert not strumenti.esegui("tira_dadi", {"cosa": 1})["ok"]
    assert not strumenti.esegui("tira_dadi", {"formula": "boh", "motivo": "x"})["ok"]


def test_tira_dadi(strumenti):
    r = strumenti.esegui("tira_dadi", {"formula": "1d20+2", "motivo": "test"})
    assert r["ok"] and 3 <= r["totale"] <= 22


def test_prova_abilita_registra_l_esito(strumenti):
    r = strumenti.esegui("prova_abilita", {"statistica": "Forza", "difficolta": "1"})  # "1" come stringa: i modelli piccoli sbagliano
    assert r["ok"] and r["successo"]
    assert strumenti.ultima_prova["successo"]
    assert not strumenti.esegui("prova_abilita", {"statistica": "forza", "difficolta": 99})["ok"]


def test_punti_vita_con_limiti(strumenti, stato):
    assert strumenti.esegui("modifica_punti_vita", {"delta": -5, "motivo": "x"})["pf_dopo"] == 7
    assert strumenti.esegui("modifica_punti_vita", {"delta": 100, "motivo": "x"})["pf_dopo"] == stato.personaggio.pf_max
    r = strumenti.esegui("modifica_punti_vita", {"delta": -100, "motivo": "x"})
    assert r["pf_dopo"] == 0 and r["personaggio_caduto"]
    assert not strumenti.esegui("modifica_punti_vita", {"delta": 0, "motivo": "x"})["ok"]


def test_inventario(strumenti, stato):
    assert strumenti.esegui("inventario", {"azione": "aggiungi", "oggetto": "Formaggio"})["ok"]
    assert strumenti.esegui("inventario", {"azione": "rimuovi", "oggetto": "formaggio"})["ok"]  # maiuscole indifferenti
    assert not strumenti.esegui("inventario", {"azione": "rimuovi", "oggetto": "formaggio"})["ok"]
    assert not strumenti.esegui("inventario", {"azione": "aggiungi"})["ok"]
    assert not strumenti.esegui("inventario", {"azione": "balla"})["ok"]


def test_inventario_pieno(strumenti, stato):
    stato.personaggio.inventario = [f"o{i}" for i in range(30)]
    assert not strumenti.esegui("inventario", {"azione": "aggiungi", "oggetto": "uno in più"})["ok"]


def test_diario(strumenti, stato):
    assert strumenti.esegui("scrivi_diario", {"evento": "Ho aiutato Tobia"})["ok"]
    assert "Ho aiutato Tobia" in stato.diario[-1]
    assert not strumenti.esegui("scrivi_diario", {"evento": "x" * 400})["ok"]


def test_avanza_tempo(strumenti, stato):
    r = strumenti.esegui("avanza_tempo", {"ore": 3})
    assert r["ok"] and stato.ora == 11
    assert not strumenti.esegui("avanza_tempo", {"ore": 0})["ok"]
    assert not strumenti.esegui("avanza_tempo", {"ore": 25})["ok"]


def test_eventi_del_mondo_scattano_una_volta(strumenti, stato):
    r = strumenti.esegui("avanza_tempo", {"ore": 24})
    assert r["eventi_mondo"], "il giorno 2 ha un evento"
    giorni = len(stato.eventi_scattati)
    strumenti.esegui("avanza_tempo", {"ore": 1})
    assert len(stato.eventi_scattati) == giorni  # niente doppioni
    assert any("EVENTO DEL MONDO" in v for v in stato.diario)


def test_il_tempo_si_ferma_al_momento_finale(strumenti, stato, mondo):
    for _ in range(10):
        r = strumenti.esegui("avanza_tempo", {"ore": 24})
        if r.get("momento_finale_raggiunto"):
            break
    assert r["momento_finale_raggiunto"]
    assert stato.ore_totali == mondo.ore_finali


def test_finale_non_prima_del_tempo(strumenti):
    assert not strumenti.esegui("valuta_finale", {})["ok"]


def test_finale_a_tempo_scaduto(strumenti, stato, mondo):
    stato.ore_totali = mondo.ore_finali
    r = strumenti.esegui("valuta_finale", {})
    assert r["ok"] and stato.finale == "l_acqua_si_prende_tutto"  # nessun flag: finale di default


def test_consulta_lore(strumenti):
    assert strumenti.esegui("consulta_lore", {"argomento": "Tobia"})["ok"]
    assert not strumenti.esegui("consulta_lore", {"argomento": "zzzzzz"})["ok"]


def test_illustra_scena_offerto_solo_se_attivo(strumenti):
    assert "illustra_scena" not in [t["name"] for t in strumenti.schemi()]
    strumenti.su_scena = lambda d, c: None
    assert "illustra_scena" in [t["name"] for t in strumenti.schemi()]


def test_illustra_scena_limita_la_frequenza(strumenti, stato):
    chiamate = []
    strumenti.su_scena = lambda d, c: chiamate.append(d)
    stato.turno = 10
    assert strumenti.esegui("illustra_scena", {"descrizione": "un ponte"})["ok"]
    assert not strumenti.esegui("illustra_scena", {"descrizione": "un altro ponte"})["ok"]
    assert len(chiamate) == 1


# --- Flag: il master non può regalare progressi a parole ----------------------------------
def _prova(strumenti, stat, cd, successo=True):
    strumenti.ultima_prova = {"statistica": stat, "cd": cd, "successo": successo}


def vai(strumenti, stato, mondo, luogo, zona=None):
    stato.luogo_id, stato.luogo_corrente = luogo, mondo.nome_luogo(luogo)
    stato.zona_id = zona or mondo.ingresso(luogo)["id"]


def test_flag_sconosciuto(strumenti):
    assert not strumenti.esegui("imposta_flag", {"flag": "inventato"})["ok"]


def test_flag_senza_prova(strumenti, stato, mondo):
    vai(strumenti, stato, mondo, "la_diga")
    assert not strumenti.esegui("imposta_flag", {"flag": "pietra_recuperata"})["ok"]


def test_flag_prova_fallita_o_debole_o_sbagliata(strumenti, stato, mondo):
    vai(strumenti, stato, mondo, "la_diga")
    for stat, cd, ok in [("forza", 18, False), ("forza", 10, True), ("intelletto", 20, True)]:
        _prova(strumenti, stat, cd, ok)
        assert not strumenti.esegui("imposta_flag", {"flag": "pietra_recuperata"})["ok"]
    assert not stato.flag.get("pietra_recuperata")


def test_flag_luogo_sbagliato(strumenti, stato, mondo):
    _prova(strumenti, "forza", 18)
    assert not strumenti.esegui("imposta_flag", {"flag": "pietra_recuperata"})["ok"]  # si parte a Pontevecchio


def test_flag_ok_e_prova_consumata(strumenti, stato, mondo):
    vai(strumenti, stato, mondo, "la_diga")
    _prova(strumenti, "forza", 18)
    assert strumenti.esegui("imposta_flag", {"flag": "pietra_recuperata"})["ok"]
    assert stato.flag["pietra_recuperata"] and "PROGRESSO" in stato.diario[-1]
    assert not strumenti.esegui("imposta_flag", {"flag": "paratoie_aperte"})["ok"]  # una prova vale per un solo flag


def test_flag_richiede_zona(strumenti, stato, mondo):
    vai(strumenti, stato, mondo, "mulino_alto")
    _prova(strumenti, "intelletto", 12)
    assert not strumenti.esegui("imposta_flag", {"flag": "fiammetta_alleata"})["ok"]  # nell'ingresso, non in officina
    vai(strumenti, stato, mondo, "mulino_alto", "officina")
    assert strumenti.esegui("imposta_flag", {"flag": "fiammetta_alleata"})["ok"]


def test_flag_richiede_flag_e_oggetto_e_lo_consuma(strumenti, stato, mondo):
    vai(strumenti, stato, mondo, "la_diga")
    _prova(strumenti, "intelletto", 15)
    assert not strumenti.esegui("imposta_flag", {"flag": "patto_rinnovato"})["ok"]  # manca contratto_trovato
    stato.flag["contratto_trovato"] = True
    assert not strumenti.esegui("imposta_flag", {"flag": "patto_rinnovato"})["ok"]  # manca il formaggio
    stato.personaggio.inventario.append("formaggio stagionato")
    assert strumenti.esegui("imposta_flag", {"flag": "patto_rinnovato"})["ok"]
    assert "formaggio stagionato" not in stato.personaggio.inventario


def test_nuovo_turno_azzera_la_prova(strumenti):
    _prova(strumenti, "forza", 20)
    strumenti.nuovo_turno()
    assert strumenti.ultima_prova is None


def test_senza_lore_i_tool_del_mondo_sono_disattivati():
    from gdr.tools import Strumenti

    s = Strumenti(nuovo_stato())
    assert not s.esegui("imposta_flag", {"flag": "x"})["ok"]
    assert not s.esegui("valuta_finale", {})["ok"]
    assert s.esegui("sposta_in", {"luogo": "Bosco"})["ok"]  # modalità libera
