"""Regole del gioco: funzioni pure, senza stato e senza LLM.

È qui che si decidono davvero gli esiti: il modello non tira mai i dadi,
chiede al codice di farlo (tramite i tool).
"""

from __future__ import annotations

import random
import re
import unicodedata

from .models import STATISTICHE

# Formato accettato: [N]dF[+/-M], es. "1d20+3", "2d6", "d8-1".
_RE_FORMULA = re.compile(r"^\s*(\d{0,2})d(\d{1,3})\s*([+-]\s*\d{1,3})?\s*$", re.IGNORECASE)

MAX_DADI = 20
MAX_FACCE = 100


class ErroreRegole(ValueError):
    """Input non valido per una regola. Il messaggio è pensato per essere letto dal modello."""


def tira_formula(formula: str, rng: random.Random) -> dict:
    """Tira una formula di dadi e restituisce singoli tiri, modificatore e totale."""
    if not isinstance(formula, str):
        raise ErroreRegole("La formula deve essere una stringa, es. '1d20+3'.")
    m = _RE_FORMULA.match(formula)
    if not m:
        raise ErroreRegole(f"Formula '{formula}' non valida. Usa il formato NdF+M, es. '1d20+3' o '2d6'.")
    n = int(m.group(1)) if m.group(1) else 1
    facce = int(m.group(2))
    mod = int(m.group(3).replace(" ", "")) if m.group(3) else 0
    if not 1 <= n <= MAX_DADI:
        raise ErroreRegole(f"Il numero di dadi deve essere tra 1 e {MAX_DADI}.")
    if not 2 <= facce <= MAX_FACCE:
        raise ErroreRegole(f"Le facce del dado devono essere tra 2 e {MAX_FACCE}.")
    tiri = [rng.randint(1, facce) for _ in range(n)]
    return {"formula": formula.strip(), "tiri": tiri, "modificatore": mod, "totale": sum(tiri) + mod}


def normalizza_statistica(nome: str) -> str:
    """'Agilità ' -> 'agilita'. Accetta maiuscole e accenti; rifiuta il resto."""
    if not isinstance(nome, str):
        raise ErroreRegole("La statistica deve essere una stringa.")
    pulito = unicodedata.normalize("NFD", nome.strip().lower())
    pulito = "".join(c for c in pulito if unicodedata.category(c) != "Mn")  # toglie gli accenti
    if pulito not in STATISTICHE:
        raise ErroreRegole(f"Statistica '{nome}' sconosciuta. Valide: forza, agilita, intelletto.")
    return pulito


def modificatore(valore: int) -> int:
    """Modificatore stile d20: 10 -> 0, 14 -> +2, 8 -> -1."""
    return (valore - 10) // 2


def prova(valore_stat: int, cd: int, rng: random.Random) -> dict:
    """Prova di caratteristica 5e: d20 + modificatore, riuscita se totale >= CD.

    Come da SRD, nelle prove di abilità 20 e 1 naturali NON sono automatici.
    """
    d20 = rng.randint(1, 20)
    mod = modificatore(valore_stat)
    totale = d20 + mod
    return {"d20": d20, "modificatore": mod, "totale": totale, "cd": cd, "successo": totale >= cd}
