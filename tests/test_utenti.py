import time

import pytest

from gdr import utenti as mod
from gdr.utenti import ErroreUtente, Utenti


@pytest.fixture
def u(tmp_path):
    return Utenti(tmp_path)


def test_registra_e_verifica(u):
    assert u.registra("Alice", "password123") == "alice"
    assert u.verifica("ALICE", "password123") == "alice"


def test_password_mai_in_chiaro(u, tmp_path):
    u.registra("alice", "password123")
    assert "password123" not in (tmp_path / "utenti.json").read_text()


@pytest.mark.parametrize("nome", ["", "ab", "../x", "a b", "x" * 21, "é_é_é", "a/b"])
def test_nomi_non_validi(u, nome):
    with pytest.raises(ErroreUtente):
        u.registra(nome, "password123")


def test_password_corta_e_duplicato(u):
    with pytest.raises(ErroreUtente):
        u.registra("alice", "corta")
    u.registra("alice", "password123")
    with pytest.raises(ErroreUtente):
        u.registra("alice", "password123")


def test_credenziali_errate_stesso_messaggio(u):
    u.registra("alice", "password123")
    with pytest.raises(ErroreUtente) as a:
        u.verifica("alice", "sbagliata1")
    with pytest.raises(ErroreUtente) as b:
        u.verifica("nessuno", "password123")
    assert str(a.value) == str(b.value)  # non rivela quali utenti esistono


def test_blocco_dopo_troppi_tentativi(u):
    u.registra("alice", "password123")
    for _ in range(mod.TENTATIVI_MAX):
        with pytest.raises(ErroreUtente):
            u.verifica("alice", "sbagliata1")
    with pytest.raises(ErroreUtente, match="Troppi tentativi"):
        u.verifica("alice", "password123")  # anche con la password giusta, finché dura il blocco


def test_token_valido_falso_e_manomesso(u):
    u.registra("alice", "password123")
    t = u.crea_token("alice")
    assert u.utente_da_token(t) == "alice"
    corpo, firma = t.rsplit(".", 1)
    assert u.utente_da_token(corpo + "." + "0" * len(firma)) is None
    assert u.utente_da_token(None) is None and u.utente_da_token("spazzatura") is None


def test_token_firmato_da_un_altro_segreto(u, tmp_path):
    u.registra("alice", "password123")
    altro = Utenti(tmp_path / "altro")
    assert u.utente_da_token(altro.crea_token("alice")) is None


def test_token_scaduto(u, monkeypatch):
    u.registra("alice", "password123")
    t = u.crea_token("alice")
    ora = time.time()
    monkeypatch.setattr(mod.time, "time", lambda: ora + mod.DURATA_LOGIN + 10)
    assert u.utente_da_token(t) is None


def test_token_di_utente_cancellato(u, tmp_path):
    u.registra("alice", "password123")
    t = u.crea_token("alice")
    (tmp_path / "utenti.json").write_text("{}")
    assert u.utente_da_token(t) is None


def test_il_segreto_persiste(tmp_path):
    a = Utenti(tmp_path)
    a.registra("alice", "password123")
    assert Utenti(tmp_path).utente_da_token(a.crea_token("alice")) == "alice"
