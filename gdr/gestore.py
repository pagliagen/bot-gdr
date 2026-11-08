"""Il gestore delle sessioni: una partita per ogni coppia (utente, avventura).

Qui vivono le cose condivise (provider del modello, coda delle immagini, semaforo dei turni)
e si decide dove sta il salvataggio di ognuno: saves/<utente>/<avventura>.json.
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

from . import state as salvataggi
from .avventure import Catalogo
from .config import Config
from .immagini import CodaImmagini, crea_generatore
from .llm import crea_provider
from .llm.base import LLMProvider
from .sessione import Sessione
from .utenti import NOME_VALIDO


class GestoreSessioni:
    def __init__(self, cfg: Config, catalogo: Catalogo | None = None, provider: LLMProvider | None = None, coda: CodaImmagini | None = None):
        self.cfg = cfg
        self.catalogo = catalogo or Catalogo(cfg.percorso_avventure)
        self.provider = provider or crea_provider(cfg)
        generatore = crea_generatore(cfg)
        self.coda = coda or (CodaImmagini(generatore) if generatore else None)
        self._semaforo = threading.Semaphore(cfg.max_turni_contemporanei)
        self._sessioni: dict[tuple[str, str], Sessione] = {}
        self._lock = threading.Lock()

    def percorso(self, utente: str, avventura_id: str) -> Path:
        # Solo nomi già validati: l'utente da Utenti.normalizza, l'avventura dal catalogo. Mai input grezzo nel percorso.
        if not NOME_VALIDO.match(utente) or self.catalogo.ottieni(avventura_id) is None:
            raise ValueError("utente o avventura non validi")
        return self.cfg.cartella_salvataggi / utente / f"{avventura_id}.json"

    def sessione(self, utente: str, avventura_id: str) -> Sessione:
        """La sessione (creata al bisogno) di questo utente in questa avventura. Il salvataggio non è ancora caricato."""
        chiave = (utente, avventura_id)
        with self._lock:
            if chiave not in self._sessioni:
                self._sessioni[chiave] = Sessione(
                    self.cfg, self.catalogo.ottieni(avventura_id), self.provider, self.percorso(utente, avventura_id), self.coda, self._semaforo  # type: ignore[arg-type]
                )
            return self._sessioni[chiave]

    def riepilogo(self, utente: str) -> list[dict[str, Any]]:
        """Le avventure con, per ognuna, il salvataggio dell'utente (se c'è): per la schermata 'continua / nuova partita'."""
        out = []
        for a in self.catalogo.elenco():
            mondo = self.catalogo.ottieni(a["id"])
            stato = salvataggi.carica(self.percorso(utente, a["id"]))
            salvato = None
            if stato:
                p = stato.personaggio
                salvato = {
                    "personaggio": p.nome,
                    "classe": p.classe,
                    "giorno": stato.giorno,
                    "ora": stato.ora,
                    "turno": stato.turno,
                    "luogo": stato.luogo_corrente,
                    "conclusa": bool(stato.finale) or p.pf <= 0,
                    "esito": next((f["nome"] for f in mondo.finali if f["id"] == stato.finale), "Il tuo eroe è caduto" if p.pf <= 0 else None),  # type: ignore[union-attr]
                }
            out.append({**a, "salvataggio": salvato})
        return out
