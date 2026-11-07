"""Il ciclo dell'agente, scritto a mano.

    giocatore scrive  ->  [ modello  ->  tool richiesti?  ->  esegui  ->  risultati al modello ]  ->  narrazione
                              ^________________ si ripete finché non chiede più tool ____________|

Questo file non sa nulla di terminale, Telegram o grafica: riceve testo e restituisce testo.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from .llm.base import LLMProvider
from .lore import Mondo
from .memory import comprimi_se_serve, costruisci_system
from .models import StatoPartita
from .tools import Strumenti

# Callback per il debug: riceve (tipo_evento, dati). La CLI decide come mostrarli.
SuEvento = Callable[[str, dict[str, Any]], None]


class Agente:
    def __init__(
        self,
        provider: LLMProvider,
        stato: StatoPartita,
        percorso_prompt: Path,
        max_iterazioni: int = 8,
        soglia_messaggi: int = 40,
        messaggi_recenti: int = 12,
        su_evento: SuEvento | None = None,
        strumenti: Strumenti | None = None,
        mondo: Mondo | None = None,
    ):
        self.provider = provider
        self.stato = stato
        self.percorso_prompt = percorso_prompt
        self.max_iterazioni = max_iterazioni
        self.soglia_messaggi = soglia_messaggi
        self.messaggi_recenti = messaggi_recenti
        self.su_evento = su_evento or (lambda tipo, dati: None)
        self.mondo = mondo
        self.strumenti = strumenti or Strumenti(stato, mondo=mondo)

    def turno(self, testo_giocatore: str) -> str:
        """Gestisce un turno completo e restituisce il testo narrativo da mostrare."""
        s = self.stato
        s.turno += 1
        self.strumenti.nuovo_turno()
        s.messaggi.append({"role": "user", "content": testo_giocatore})
        comprimi_se_serve(s, self.soglia_messaggi, self.messaggi_recenti)

        try:
            return self._ciclo()
        except Exception:
            # Errore (rete, API...): annulla il turno così la cronologia resta coerente.
            s.turno -= 1
            self._annulla_turno(testo_giocatore)
            raise

    def _annulla_turno(self, testo_giocatore: str) -> None:
        """Rimuove i messaggi di questo turno (dall'ultimo messaggio utente col testo del giocatore)."""
        m = self.stato.messaggi
        for i in range(len(m) - 1, -1, -1):
            if m[i]["role"] == "user" and m[i]["content"] == testo_giocatore:
                del m[i:]
                return

    def _ciclo(self) -> str:
        s = self.stato
        for _ in range(self.max_iterazioni):
            # Il prompt si rilegge da file a ogni giro: lo puoi modificare a partita in corso.
            prompt = self.percorso_prompt.read_text(encoding="utf-8")
            system = costruisci_system(prompt, s, self.mondo)

            # 1) chiama il modello
            risposta = self.provider.chiama(system, s.messaggi, self.strumenti.schemi())

            # 2) registra la risposta del modello nella cronologia
            blocchi: list[dict] = []
            if risposta.testo:
                blocchi.append({"type": "text", "text": risposta.testo})
            for c in risposta.chiamate_tool:
                blocchi.append({"type": "tool_use", "id": c.id, "name": c.nome, "input": c.argomenti})

            # 3) nessun tool richiesto = risposta narrativa finale: fine del ciclo
            if not risposta.chiamate_tool:
                testo = risposta.testo or "(Il narratore resta in silenzio... riprova a descrivere la tua azione.)"
                s.messaggi.append({"role": "assistant", "content": testo})
                return testo

            s.messaggi.append({"role": "assistant", "content": blocchi})

            # 4) esegui i tool e restituisci TUTTI i risultati in un unico messaggio
            risultati = []
            for c in risposta.chiamate_tool:
                self.su_evento("tool_call", {"nome": c.nome, "argomenti": c.argomenti})
                esito = self.strumenti.esegui(c.nome, c.argomenti)
                self.su_evento("tool_result", {"nome": c.nome, "risultato": esito})
                risultati.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": c.id,
                        "content": json.dumps(esito, ensure_ascii=False),
                        "is_error": not esito.get("ok", False),
                    }
                )
            s.messaggi.append({"role": "user", "content": risultati})
            # ...e si torna al punto 1: il modello legge i risultati e decide cosa fare.

        # Limite raggiunto: chiudiamo in modo pulito per non lasciare la cronologia a metà.
        testo = "(Il narratore si perde nei suoi pensieri e perde il filo. Riprova con un'azione più semplice.)"
        s.messaggi.append({"role": "assistant", "content": testo})
        return testo
