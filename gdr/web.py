"""Interfaccia web locale (FastAPI). Serve la pagina in web/ e poche API JSON.

Come la CLI, questo file non contiene logica di gioco: traduce richieste HTTP in
chiamate alla `Sessione`. Pensata per un solo giocatore in locale (una sessione
globale), quindi non ha login.
"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .config import RADICE, Config
from .sessione import Sessione, SessioneOccupata, opzioni_creazione


class NuovaPartita(BaseModel):
    nome: str
    classe: str
    valori: dict[str, int]  # {"forza": 15, "agilita": 13, "intelletto": 10}


class Azione(BaseModel):
    testo: str


def crea_app(cfg: Config, sessione: Sessione | None = None) -> FastAPI:
    app = FastAPI(title="Master GDR")
    sess = sessione or Sessione(cfg)
    sess.carica()  # se c'è un salvataggio in corso, lo riprende

    def risposta_turno(esito: dict) -> dict:
        return {**esito, "vista": sess.vista()}

    @app.get("/api/stato")
    def stato() -> dict:
        return {"in_corso": sess.stato is not None, "creazione": opzioni_creazione(), "vista": sess.vista() if sess.stato else None}

    @app.post("/api/nuova")
    def nuova(dati: NuovaPartita) -> dict:
        try:
            sess.nuova(dati.nome, dati.classe, dati.valori)
        except ValueError as e:
            raise HTTPException(400, str(e))
        return {"vista": sess.vista()}

    def _turno(testo: str, iniziale: bool = False) -> dict:
        if sess.stato is None:
            raise HTTPException(409, "Nessuna partita in corso: creane una.")
        try:
            return risposta_turno(sess.inizia() if iniziale else sess.turno(testo))
        except SessioneOccupata as e:
            raise HTTPException(409, str(e))
        except Exception as e:  # modello spento, rete... il turno è già stato annullato dall'agente
            raise HTTPException(502, f"Errore nella chiamata al modello: {e}")

    @app.post("/api/inizia")
    def inizia() -> dict:
        return _turno("", iniziale=True)

    @app.post("/api/turno")
    def turno(azione: Azione) -> dict:
        testo = azione.testo.strip()
        if not testo:
            raise HTTPException(400, "Scrivi cosa fa il tuo personaggio.")
        return _turno(testo)

    # Immagini statiche (mappa, ritratti, luoghi) e pagina
    app.mount("/assets", StaticFiles(directory=RADICE / "assets"), name="assets")
    app.mount("/web", StaticFiles(directory=RADICE / "web"), name="web")

    @app.get("/")
    def indice() -> FileResponse:
        return FileResponse(RADICE / "web" / "index.html")

    return app
