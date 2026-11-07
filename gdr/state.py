"""Salvataggio e caricamento della partita su file JSON."""

from __future__ import annotations

import json
import os
from pathlib import Path

from .models import StatoPartita


def salva(stato: StatoPartita, percorso: Path) -> None:
    """Scrittura atomica: scrive su un file temporaneo e poi lo rinomina.

    Se il programma si interrompe a metà scrittura, il vecchio salvataggio
    resta intatto (os.replace è atomico).
    """
    percorso = Path(percorso)
    percorso.parent.mkdir(parents=True, exist_ok=True)
    tmp = percorso.with_suffix(percorso.suffix + ".tmp")
    tmp.write_text(json.dumps(stato.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, percorso)


def carica(percorso: Path) -> StatoPartita | None:
    """Restituisce lo stato salvato, oppure None se il file non esiste."""
    percorso = Path(percorso)
    if not percorso.exists():
        return None
    return StatoPartita.from_dict(json.loads(percorso.read_text(encoding="utf-8")))
