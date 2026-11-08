"""Strumenti comuni ai test: nessun modello vero, nessuna immagine, nessun file nel progetto."""

from __future__ import annotations

import dataclasses
import random
from pathlib import Path

import pytest

from gdr.avventure import Catalogo
from gdr.config import RADICE, carica_config
from gdr.llm.base import ChiamataTool, LLMProvider, RispostaLLM
from gdr.models import Personaggio, StatoPartita
from gdr.tools import Strumenti

STATS = {"forza": 15, "agilita": 13, "intelletto": 10}


class ProviderFinto(LLMProvider):
    """Risponde con una scaletta: ogni elemento è un testo (risposta finale) o una lista di ChiamataTool.

    Finita la scaletta risponde sempre "Narrazione di prova". Salva le chiamate ricevute in `chiamate`.
    """

    def __init__(self, scaletta: list | None = None):
        self.scaletta = list(scaletta or [])
        self.chiamate: list[dict] = []

    def chiama(self, system, messaggi, tools):
        self.chiamate.append({"system": system, "messaggi": [dict(m) for m in messaggi], "tools": tools})
        if not self.scaletta:
            return RispostaLLM(testo="Narrazione di prova")
        passo = self.scaletta.pop(0)
        if isinstance(passo, Exception):
            raise passo
        if isinstance(passo, str):
            return RispostaLLM(testo=passo)
        return RispostaLLM(chiamate_tool=passo)


def tool(nome: str, id: str = "t1", **argomenti) -> ChiamataTool:
    return ChiamataTool(id=id, nome=nome, argomenti=argomenti)


@pytest.fixture(scope="session")
def catalogo() -> Catalogo:
    return Catalogo(RADICE / "avventure")


@pytest.fixture(params=["acquaverde", "vallombra", "marenza"])
def avventura(request, catalogo):
    return catalogo.ottieni(request.param)


@pytest.fixture
def mondo(catalogo):
    return catalogo.ottieni("acquaverde")


def nuovo_stato(mondo=None) -> StatoPartita:
    s = StatoPartita(Personaggio("Aldo", "Guerriero", dict(STATS), 12, 12, ["spada lunga"]), "")
    if mondo:
        mondo.stato_iniziale(s)
    return s


@pytest.fixture
def stato(mondo):
    return nuovo_stato(mondo)


@pytest.fixture
def strumenti(stato, mondo):
    return Strumenti(stato, rng=random.Random(1), mondo=mondo)


@pytest.fixture
def cfg(tmp_path):
    """Config di prova: salvataggi in una cartella temporanea, niente immagini."""
    return dataclasses.replace(
        carica_config(), immagini_attive=False, cartella_salvataggi=tmp_path / "saves", codice_invito="segreto123", admin=("alice",)
    )
