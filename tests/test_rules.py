import random

import pytest

from gdr import rules


def test_formula_valida():
    r = rules.tira_formula("2d6+3", random.Random(0))
    assert len(r["tiri"]) == 2 and r["modificatore"] == 3
    assert r["totale"] == sum(r["tiri"]) + 3


@pytest.mark.parametrize("f", ["", "abc", "1d1", "0d6", "21d6", "1d101", "1d20++3", 5])
def test_formula_non_valida(f):
    with pytest.raises(rules.ErroreRegole):
        rules.tira_formula(f, random.Random(0))


def test_formula_senza_numero_di_dadi():
    assert len(rules.tira_formula("d8-1", random.Random(0))["tiri"]) == 1


def test_dadi_sempre_nel_range():
    rng = random.Random(0)
    assert all(1 <= rules.tira_formula("1d6", rng)["totale"] <= 6 for _ in range(200))


@pytest.mark.parametrize("nome,atteso", [("Agilità ", "agilita"), ("FORZA", "forza"), ("intelletto", "intelletto")])
def test_normalizza_statistica(nome, atteso):
    assert rules.normalizza_statistica(nome) == atteso


def test_statistica_sconosciuta():
    with pytest.raises(rules.ErroreRegole):
        rules.normalizza_statistica("carisma")


@pytest.mark.parametrize("valore,mod", [(10, 0), (11, 0), (14, 2), (15, 2), (8, -1), (7, -2)])
def test_modificatore(valore, mod):
    assert rules.modificatore(valore) == mod


def test_prova_esito_coerente():
    rng = random.Random(3)
    for _ in range(100):
        r = rules.prova(14, 15, rng)
        assert r["totale"] == r["d20"] + 2
        assert r["successo"] == (r["totale"] >= 15)
