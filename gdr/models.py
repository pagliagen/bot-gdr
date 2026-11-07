"""Modelli di dati della partita.

Tutto lo stato del gioco vive in un unico oggetto (`StatoPartita`) che si può
convertire in dizionario e quindi salvare come JSON. Nessuna logica di gioco
qui dentro: solo dati.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

# Le tre statistiche del gioco (chiavi senza accenti, usate ovunque nel codice).
STATISTICHE = ("forza", "agilita", "intelletto")


@dataclass
class Personaggio:
    nome: str
    classe: str
    statistiche: dict[str, int]  # es. {"forza": 14, "agilita": 10, "intelletto": 8}
    pf: int  # punti vita attuali
    pf_max: int
    inventario: list[str] = field(default_factory=list)


@dataclass
class StatoPartita:
    personaggio: Personaggio
    luogo_corrente: str
    luoghi_visitati: list[str] = field(default_factory=list)
    diario: list[str] = field(default_factory=list)
    # Cronologia della conversazione col modello, in formato neutro (vedi llm/base.py).
    # Ogni elemento: {"role": "user"|"assistant", "content": str | list[blocchi]}
    messaggi: list[dict[str, Any]] = field(default_factory=list)
    turno: int = 0
    # --- Il mondo che avanza da solo ---
    luogo_id: str = ""  # id del luogo corrente nella lore (luogo_corrente è il nome da mostrare)
    ore_totali: int = 8  # ore trascorse dall'inizio del giorno 1; si parte alle 08:00 del giorno 1
    flag: dict[str, bool] = field(default_factory=dict)  # progressi dell'avventura
    eventi_scattati: list[int] = field(default_factory=list)  # giorni degli eventi già accaduti
    finale: str | None = None  # id del finale raggiunto (None = partita in corso)
    # --- Illustrazioni generate ---
    scena: dict | None = None  # {"url", "didascalia", "luogo_id"} dell'ultima illustrazione di scena
    ultimo_turno_scena: int = -99  # per limitare la frequenza delle illustrazioni

    @property
    def giorno(self) -> int:
        return self.ore_totali // 24 + 1

    @property
    def ora(self) -> int:
        return self.ore_totali % 24

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, dati: dict[str, Any]) -> "StatoPartita":
        dati = dict(dati)
        dati["personaggio"] = Personaggio(**dati["personaggio"])
        return cls(**dati)
