import threading

import pytest

from conftest import ProviderFinto, STATS, tool
from gdr.gestore import GestoreSessioni
from gdr.sessione import PROMPT_INIZIO, SessioneOccupata


@pytest.fixture
def gestore(cfg):
    return GestoreSessioni(cfg, provider=ProviderFinto())


def nuova(gestore, utente="alice", avv="acquaverde"):
    s = gestore.sessione(utente, avv)
    s.nuova("Aldo", "Guerriero", STATS)
    return s


def test_nuova_partita_salva_e_si_riprende(gestore, cfg):
    s = nuova(gestore)
    assert (cfg.cartella_salvataggi / "alice" / "acquaverde.json").exists()
    altro = GestoreSessioni(cfg, provider=ProviderFinto()).sessione("alice", "acquaverde")
    assert altro.carica() and altro.stato.personaggio.nome == "Aldo"


def test_carica_senza_salvataggio(gestore):
    assert not gestore.sessione("bob", "marenza").carica()


def test_partita_conclusa_non_si_riprende(gestore):
    s = nuova(gestore)
    s.stato.finale = "nuovo_patto"
    s._salva()
    assert not GestoreSessioni(gestore.cfg, provider=ProviderFinto()).sessione("alice", "acquaverde").carica()


def test_nuova_non_valida(gestore):
    with pytest.raises(ValueError):
        gestore.sessione("alice", "acquaverde").nuova("", "Guerriero", STATS)


def test_turno_salva_e_il_messaggio_di_avvio_non_e_in_cronologia(gestore, cfg):
    s = nuova(gestore)
    s.inizia()
    s.turno("Saluto tutti")
    v = s.vista()
    assert [m["ruolo"] for m in v["cronologia"]] == ["narratore", "giocatore", "narratore"]
    assert all(m["testo"] != PROMPT_INIZIO for m in v["cronologia"])
    assert gestore.sessione("alice", "acquaverde").stato.turno == 2
    assert '"turno": 2' in (cfg.cartella_salvataggi / "alice" / "acquaverde.json").read_text()


def test_turno_senza_partita(gestore):
    with pytest.raises(RuntimeError):
        gestore.sessione("alice", "acquaverde").turno("x")


def test_errore_del_modello_non_sporca_la_partita(cfg):
    g = GestoreSessioni(cfg, provider=ProviderFinto([RuntimeError("giù")]))
    s = nuova(g)
    with pytest.raises(RuntimeError):
        s.turno("ciao")
    assert s.stato.turno == 0 and s.stato.messaggi == []


def test_turno_in_corso_rifiuta_il_secondo(cfg):
    dentro, via = threading.Event(), threading.Event()

    class Lento(ProviderFinto):
        def chiama(self, *a):
            dentro.set()
            via.wait(5)
            return super().chiama(*a)

    s = nuova(GestoreSessioni(cfg, provider=Lento()))
    t = threading.Thread(target=lambda: s.turno("uno"))
    t.start()
    assert dentro.wait(5)
    with pytest.raises(SessioneOccupata):
        s.turno("due")
    via.set()
    t.join()


def test_eventi_del_mondo_restituiti(cfg):
    g = GestoreSessioni(cfg, provider=ProviderFinto([[tool("avanza_tempo", ore=24)], "Passa un giorno."]))
    esito = nuova(g).turno("Aspetto un giorno")
    assert esito["eventi_mondo"] and esito["narrazione"] == "Passa un giorno."


def test_spostamento_aggiorna_la_vista(cfg):
    g = GestoreSessioni(cfg, provider=ProviderFinto([[tool("sposta_in", luogo="emporio")], "Entri."]))
    s = nuova(g)
    s.turno("Entro nell'emporio")
    v = s.vista()["luogo"]
    assert v["zona"] == "Emporio di Gelsomina" or "mporio" in v["zona"]
    assert any(z["stato"] == "corrente" for z in v["zone"])


def test_sessioni_separate_per_utente_e_avventura(gestore):
    a, b, c = nuova(gestore, "alice"), nuova(gestore, "bob"), nuova(gestore, "alice", "marenza")
    assert a is gestore.sessione("alice", "acquaverde") and a is not b and a is not c
    a.stato.personaggio.nome = "Zed"
    assert b.stato.personaggio.nome == "Aldo"


def test_riepilogo_salvataggi(gestore):
    nuova(gestore, "alice", "vallombra")
    per_id = {r["id"]: r for r in gestore.riepilogo("alice")}
    assert per_id["vallombra"]["salvataggio"]["personaggio"] == "Aldo"
    assert per_id["acquaverde"]["salvataggio"] is None
    assert all(r["salvataggio"] is None for r in gestore.riepilogo("bob"))


def test_percorso_rifiuta_input_pericolosi(gestore):
    for utente, avv in [("../x", "acquaverde"), ("alice", "../../etc"), ("alice", "nonesiste"), ("A b", "marenza")]:
        with pytest.raises(ValueError):
            gestore.percorso(utente, avv)


def test_la_vista_nasconde_i_luoghi_ignoti(gestore):
    pins = nuova(gestore).vista()["mappa"]["pins"]
    assert pins[0]["stato"] == "corrente" and all(p["nome"] == "?" for p in pins if p["stato"] == "vicino")
    assert len(pins) < len(gestore.catalogo.ottieni("acquaverde").luoghi)


# --- Annulla ultimo turno ----------------------------------------------------------------
def test_annulla_ripristina_lo_stato_e_restituisce_il_testo(cfg):
    g = GestoreSessioni(cfg, provider=ProviderFinto(["Apertura.", [tool("avanza_tempo", ore=3), tool("modifica_punti_vita", id="t2", delta=-4, motivo="x")], "Sei ferito."]))
    s = nuova(g)
    s.inizia()
    s.turno("Aspetto e mi faccio male")
    assert s.stato.ora == 11 and s.stato.personaggio.pf == 8 and s.vista()["puo_annullare"]
    assert s.annulla() == "Aspetto e mi faccio male"
    assert s.stato.ora == 8 and s.stato.personaggio.pf == 12 and s.stato.turno == 1
    assert [m["testo"] for m in s.vista()["cronologia"]] == ["Apertura."]
    assert not s.vista()["puo_annullare"]


def test_annulla_e_persistente_e_a_un_solo_livello(cfg):
    g = GestoreSessioni(cfg, provider=ProviderFinto())
    s = nuova(g)
    s.inizia()
    s.turno("uno")
    s.turno("due")
    assert s.annulla() == "due"
    with pytest.raises(RuntimeError):  # un solo livello
        s.annulla()
    # sopravvive al riavvio: il salvataggio è quello di prima del turno annullato
    ripreso = GestoreSessioni(cfg, provider=ProviderFinto()).sessione("alice", "acquaverde")
    assert ripreso.carica() and ripreso.stato.turno == 2
    assert [m["testo"] for m in ripreso.vista()["cronologia"] if m["ruolo"] == "giocatore"] == ["uno"]


def test_apertura_non_si_annulla(cfg):
    s = nuova(GestoreSessioni(cfg, provider=ProviderFinto()))
    s.inizia()
    assert not s.puo_annullare()
    with pytest.raises(RuntimeError):
        s.annulla()


def test_turno_fallito_non_crea_un_annulla(cfg):
    s = nuova(GestoreSessioni(cfg, provider=ProviderFinto(["Apertura.", "uno", RuntimeError("giù")])))
    s.inizia()
    s.turno("uno")
    with pytest.raises(RuntimeError):
        s.turno("due")
    assert s.annulla() == "uno"  # annulla il turno riuscito, non quello fallito


def test_nuova_partita_cancella_l_annulla(cfg):
    s = nuova(GestoreSessioni(cfg, provider=ProviderFinto()))
    s.inizia()
    s.turno("uno")
    assert s.puo_annullare()
    s.nuova("Bea", "Mago", STATS)
    assert not s.puo_annullare()


def test_annulla_dopo_il_finale_riapre_la_partita(cfg):
    g = GestoreSessioni(cfg, provider=ProviderFinto(["Apertura.", [tool("valuta_finale")], "Fine."]))
    s = nuova(g)
    s.inizia()
    s.stato.ore_totali = s.mondo.ore_finali
    s.turno("Aspetto la fine")
    assert s.stato.finale
    s.annulla()
    assert s.stato.finale is None and s.vista()["fine"] is None


def test_annulla_durante_un_turno_e_rifiutato(cfg):
    dentro, via = threading.Event(), threading.Event()

    class Lento(ProviderFinto):
        def chiama(self, *a):
            dentro.set()
            via.wait(5)
            return super().chiama(*a)

    s = nuova(GestoreSessioni(cfg, provider=Lento()))
    via.set()
    s.inizia()
    s.turno("uno")
    via.clear()
    dentro.clear()
    t = threading.Thread(target=lambda: s.turno("due"))
    t.start()
    assert dentro.wait(5)
    with pytest.raises(SessioneOccupata):
        s.annulla()
    via.set()
    t.join()
