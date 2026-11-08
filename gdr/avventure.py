"""Il catalogo delle avventure: una cartella in avventure/ per ognuna.

Ogni avventura è autonoma (mondo, luoghi, zone, PNG, trama, immagini). Aggiungerne una
nuova significa creare una cartella con gli stessi file di `acquaverde`: il catalogo
la trova da solo.
"""

from __future__ import annotations

import re
from pathlib import Path

from .lore import Mondo

ID_VALIDO = re.compile(r"^[a-z0-9_]{1,40}$")


class Catalogo:
    def __init__(self, cartella: Path):
        self._mondi: dict[str, Mondo] = {}
        for d in sorted(Path(cartella).iterdir()):
            if d.is_dir() and ID_VALIDO.match(d.name) and (d / "avventura.yaml").exists():
                self._mondi[d.name] = Mondo(d)
        if not self._mondi:
            raise RuntimeError(f"Nessuna avventura trovata in {cartella}.")

    def ids(self) -> list[str]:
        return list(self._mondi)

    def ottieni(self, avventura_id: str) -> Mondo | None:
        """Il mondo di un'avventura, o None se l'id non esiste (nessun accesso al disco con l'id dell'utente)."""
        return self._mondi.get(avventura_id)

    def elenco(self) -> list[dict]:
        return [
            {"id": m.id, "titolo": m.titolo, "presentazione": m.presentazione, "giorni": m.giorni, "mondo": m.mondo["nome"]}
            for m in self._mondi.values()
        ]
