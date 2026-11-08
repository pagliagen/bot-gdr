"""Una partita in corso: stato + agente + salvataggio, senza alcuna interfaccia.

È il livello comune che useranno le interfacce (web adesso, Telegram in futuro):
loro si occupano solo di mostrare e di raccogliere input.
"""

from __future__ import annotations

import hashlib
import threading
from pathlib import Path
from typing import Any

from . import state as salvataggi
from .agent import Agente
from .character_creation import ARRAY_STANDARD, CLASSI, crea_personaggio
from .config import RADICE, Config
from .immagini import CodaImmagini, GeneratoreImmagini, crea_generatore
from .llm import crea_provider
from .llm.base import LLMProvider
from .lore import GIORNI_AVVENTURA, Mondo, carica_mondo
from .models import StatoPartita

PROMPT_INIZIO = (
    "Inizia l'avventura: è la mattina del primo giorno. Presenta la scena iniziale "
    "(tieni conto degli eventi già in corso nel diario) e il personaggio, e lascia a me la prima mossa."
)


class SessioneOccupata(RuntimeError):
    """Un altro turno è ancora in corso."""


class Sessione:
    def __init__(
        self,
        cfg: Config,
        mondo: Mondo | None = None,
        provider: LLMProvider | None = None,
        generatore: GeneratoreImmagini | None = None,
    ):
        self.cfg = cfg
        self.mondo = mondo or carica_mondo(cfg.percorso_lore)
        self.provider = provider or crea_provider(cfg)
        self.stato: StatoPartita | None = None
        self.agente: Agente | None = None
        self._eventi: list[dict[str, Any]] = []
        self._lock = threading.Lock()
        self._lock_salva = threading.Lock()
        # Immagini generate a runtime: coda in background (None se disattivate)
        generatore = generatore or crea_generatore(cfg)
        self.coda: CodaImmagini | None = CodaImmagini(generatore) if generatore else None
        self._posto_visto: tuple[str, str] = ("", "")  # (luogo, zona) dell'ultimo turno: per accorgersi che il giocatore si è mosso

    # --- Ciclo di vita ----------------------------------------------------------
    def carica(self) -> bool:
        """Riprende il salvataggio, se esiste ed è ancora in corso."""
        stato = salvataggi.carica(self.cfg.percorso_salvataggio)
        if stato is None or stato.finale or stato.personaggio.pf <= 0:
            return False
        self._usa(stato)
        return True

    def nuova(self, nome: str, classe: str, valori: dict[str, int]) -> None:
        """Crea una partita nuova. Solleva ValueError se le scelte non sono valide."""
        stato = StatoPartita(personaggio=crea_personaggio(nome, classe, valori), luogo_corrente="")
        self.mondo.stato_iniziale(stato)
        self._usa(stato)
        salvataggi.salva(stato, self.cfg.percorso_salvataggio)

    def _usa(self, stato: StatoPartita) -> None:
        self.mondo.assicura_zona(stato)  # salvataggi vecchi senza zona
        self.stato = stato
        self.agente = Agente(
            provider=self.provider,
            stato=stato,
            percorso_prompt=self.cfg.percorso_prompt,
            max_iterazioni=self.cfg.max_iterazioni,
            soglia_messaggi=self.cfg.soglia_messaggi,
            messaggi_recenti=self.cfg.messaggi_recenti,
            su_evento=lambda tipo, dati: self._eventi.append({"tipo": tipo, **dati}),
            mondo=self.mondo,
        )
        # Il tool illustra_scena esiste solo se le immagini sono attive
        self.agente.strumenti.su_scena = self._richiedi_scena if self.coda else None
        self._posto_visto = (stato.luogo_id, stato.zona_id)
        self._richiedi_luogo()

    def _salva(self) -> None:
        with self._lock_salva:  # può essere chiamato anche dal thread delle immagini
            salvataggi.salva(self.stato, self.cfg.percorso_salvataggio)  # type: ignore[arg-type]

    # --- Immagini generate -------------------------------------------------------
    def _stile(self) -> str:
        return self.mondo.mondo["stile_immagini"].strip()

    def _percorso_zona(self, luogo_id: str, zona_id: str) -> Path:
        """Immagine statica della zona (assets/zone/), se esiste; altrimenti il percorso della copia generata."""
        statica = RADICE / "assets" / "zone" / f"{luogo_id}_{zona_id}.webp"
        return statica if statica.exists() else self.cfg.percorso_generate / "zone" / f"{luogo_id}_{zona_id}.webp"

    def _richiedi_luogo(self) -> None:
        """Se la zona corrente non ha un'immagine (né statica né già generata), la genera: una volta sola, poi è in cache."""
        if not self.coda or not self.stato:
            return
        z = self.mondo.zona(self.stato.luogo_id, self.stato.zona_id)
        if not z or not z.get("prompt_immagine"):
            return
        percorso = self._percorso_zona(self.stato.luogo_id, z["id"])
        self.coda.accoda(f"{z['prompt_immagine'].strip()}, {self._stile()}", percorso)  # False (nulla da fare) se esiste già

    def _richiedi_scena(self, descrizione: str, didascalia: str) -> None:
        """Chiamata dal tool illustra_scena: mette in coda l'illustrazione e la mostrerà quando è pronta."""
        s, luogo = self.stato, self.stato.luogo_id  # type: ignore[union-attr]
        nome = f"{s.turno:04d}_{hashlib.sha1(descrizione.encode()).hexdigest()[:8]}.webp"
        percorso = self.cfg.percorso_generate / "scene" / nome

        def pronta(ok: bool) -> None:
            if ok and self.stato is s:
                s.scena = {"url": "/" + percorso.relative_to(RADICE).as_posix(), "didascalia": didascalia, "luogo_id": luogo}
                self._salva()

        # I PNG nominati nella descrizione vengono resi con il loro aspetto vero (come nei ritratti)
        aspetti = ". ".join(self.mondo.aspetti_in_scena(descrizione))
        prompt = f"{descrizione}. {aspetti}. {self._stile()}" if aspetti else f"{descrizione}, {self._stile()}"
        self.coda.accoda(prompt, percorso, pronta)  # type: ignore[union-attr]

    @staticmethod
    def _url_file(percorso: Path) -> str | None:
        """URL di un file generato, con la data di modifica per evitare la cache del browser."""
        if percorso.exists():
            return f"/{percorso.relative_to(RADICE).as_posix()}?v={int(percorso.stat().st_mtime)}"
        return None

    # --- Turni -------------------------------------------------------------------
    def inizia(self) -> dict[str, Any]:
        return self.turno(PROMPT_INIZIO)

    def turno(self, testo: str) -> dict[str, Any]:
        """Esegue un turno. Restituisce narrazione, tool chiamati ed eventi del mondo (solo i titoli)."""
        if self.agente is None or self.stato is None:
            raise RuntimeError("Nessuna partita in corso.")
        if not self._lock.acquire(blocking=False):
            raise SessioneOccupata("Il narratore sta ancora scrivendo.")
        try:
            self._eventi = []
            narrazione = self.agente.turno(testo)  # in caso di errore annulla il turno e rilancia
            if (self.stato.luogo_id, self.stato.zona_id) != self._posto_visto:  # il giocatore si è spostato
                self._posto_visto = (self.stato.luogo_id, self.stato.zona_id)
                self.stato.scena = None  # l'illustrazione di scena valeva per il posto di prima
                self._richiedi_luogo()
            self._salva()
            eventi, self._eventi = self._eventi, []
        finally:
            self._lock.release()
        titoli = [
            e["titolo"]
            for ev in eventi
            if ev["tipo"] == "tool_result"
            for e in ev["risultato"].get("eventi_mondo", [])
        ]
        return {"narrazione": narrazione, "tool": eventi, "eventi_mondo": titoli}

    # --- Vista per l'interfaccia -------------------------------------------------
    @staticmethod
    def _url(percorso: str | None) -> str | None:
        """URL di un'immagine statica, solo se il file esiste davvero."""
        if percorso and (RADICE / percorso).exists():
            return "/" + percorso
        return None

    def vista(self) -> dict[str, Any]:
        s, m = self.stato, self.mondo
        assert s is not None
        p = s.personaggio
        luogo = m.luoghi.get(s.luogo_id, {})
        zona = m.zona(s.luogo_id, s.zona_id) or {}
        visitati = {l["id"] for l in m.luoghi.values() if l["nome"] in s.luoghi_visitati}
        vicini = m.raggiungibili(s.luogo_id)

        pins = []
        for l in m.luoghi.values():
            if l["id"] == s.luogo_id:
                stato_pin = "corrente"
            elif l["id"] in visitati:
                stato_pin = "visitato"
            elif l["id"] in vicini:
                stato_pin = "vicino"
            else:
                continue  # luoghi ancora ignoti: non compaiono (nebbia)
            pins.append({"id": l["id"], "nome": l["nome"] if stato_pin != "vicino" else "?", "x": l["pos"][0], "y": l["pos"][1], "stato": stato_pin})

        fine = None
        if s.finale:
            f = next(f for f in m.finali if f["id"] == s.finale)
            fine = {"tipo": "finale", "titolo": f["nome"], "esito": f["esito"].strip()}
        elif p.pf <= 0:
            fine = {"tipo": "caduto", "titolo": "Il tuo eroe è caduto", "esito": ""}

        return {
            "personaggio": {
                "nome": p.nome,
                "classe": p.classe,
                "pf": p.pf,
                "pf_max": p.pf_max,
                "statistiche": {k: {"valore": v, "mod": (v - 10) // 2} for k, v in p.statistiche.items()},
                "inventario": list(p.inventario),
            },
            "tempo": {"giorno": s.giorno, "ora": s.ora, "giorni_totali": GIORNI_AVVENTURA},
            "luogo": {
                "id": s.luogo_id,
                "nome": s.luogo_corrente,
                "luogo_nome": luogo.get("nome", s.luogo_corrente),
                "zona": zona.get("nome", ""),
                # l'immagine della zona, altrimenti quella del luogo finché la zona non è pronta
                "immagine": self._url_file(self._percorso_zona(s.luogo_id, s.zona_id)) or self._url(luogo.get("immagine")),
                "zone": self._zone_vista(),
                "png": [
                    {"id": n["id"], "nome": n["nome"], "ruolo": n["ruolo"], "immagine": self._url(n.get("immagine"))}
                    for n in m.png_presenti(s.luogo_id, s.zona_id, s.ora)
                ],
                "collegamenti": [
                    {"nome": m.nome_luogo(k) if k in visitati else "?", "ore": v} for k, v in vicini.items()
                ],
            },
            "scena": self._scena_valida(),
            "immagini": {
                "attive": self.coda is not None,
                "in_corso": self.coda.n_in_corso if self.coda else 0,
                "errore": self.coda.ultimo_errore if self.coda else None,
            },
            "mappa": {"immagine": self._url("assets/mappa.webp"), "pins": pins},
            "diario": list(s.diario),
            "cronologia": self._cronologia(),
            "fine": fine,
        }

    def _zone_vista(self) -> list[dict[str, Any]]:
        """Le zone del luogo con lo stato (corrente / aperta / chiusa) e l'orario."""
        s, m = self.stato, self.mondo
        out = []
        for z in m.zone(s.luogo_id):  # type: ignore[union-attr]
            aperta, motivo = m.apertura(z, s)  # type: ignore[arg-type]
            stato_z = "corrente" if z["id"] == s.zona_id else ("aperta" if aperta else "chiusa")  # type: ignore[union-attr]
            orari = m.orari_testo(z)
            out.append({"id": z["id"], "nome": z["nome"], "stato": stato_z, "orari": orari if z.get("orari") else "", "motivo": motivo})
        return out

    def _scena_valida(self) -> dict[str, str] | None:
        """L'ultima illustrazione di scena, solo se riguarda il luogo attuale e il file esiste."""
        sc = self.stato.scena  # type: ignore[union-attr]
        if sc and sc["luogo_id"] == self.stato.luogo_id and (RADICE / sc["url"].lstrip("/")).exists():  # type: ignore[union-attr]
            return {"url": sc["url"], "didascalia": sc["didascalia"]}
        return None

    def _cronologia(self) -> list[dict[str, str]]:
        """I messaggi 'veri' della chat (niente tool, niente messaggio di avvio)."""
        out = []
        for msg in self.stato.messaggi:  # type: ignore[union-attr]
            if isinstance(msg["content"], str) and msg["content"] != PROMPT_INIZIO:
                out.append({"ruolo": "giocatore" if msg["role"] == "user" else "narratore", "testo": msg["content"]})
        return out


def opzioni_creazione() -> dict[str, Any]:
    """Dati per il modulo di creazione del personaggio."""
    return {
        "classi": [{"nome": n, "descrizione": c["descrizione"]} for n, c in CLASSI.items()],
        "valori": list(ARRAY_STANDARD),
    }
