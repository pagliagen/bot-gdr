"""Interfaccia web (FastAPI): pagina in web/ e API JSON, con login e più avventure.

Come la CLI, questo file non contiene logica di gioco: traduce richieste HTTP in
chiamate al `GestoreSessioni` / alla `Sessione`. Si occupa però di sicurezza:
- ogni richiesta di gioco richiede il cookie di login (firmato) e usa SOLO l'utente del cookie;
- id di avventura e nomi utente sono validati prima di diventare un percorso;
- i tool chiamati (debug, pieni di spoiler) li vedono solo gli utenti in ADMIN;
- le immagini si servono solo da avventure/<id>/assets: i file YAML con i segreti non sono raggiungibili.
"""

from __future__ import annotations

import hmac
import json
import queue
import threading
import time

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .config import RADICE, Config
from .gestore import GestoreSessioni
from .sessione import Sessione, SessioneOccupata, opzioni_creazione
from .utenti import ErroreUtente, Utenti

COOKIE = "gdr_sessione"
MAX_TESTO = 1000


class Credenziali(BaseModel):
    nome: str = Field(max_length=40)
    password: str = Field(max_length=200)


class Registrazione(Credenziali):
    codice: str = Field(default="", max_length=100)


class NuovaPartita(BaseModel):
    nome: str = Field(max_length=60)
    classe: str = Field(max_length=30)
    valori: dict[str, int]  # {"forza": 15, "agilita": 13, "intelletto": 10}


class Azione(BaseModel):
    testo: str = Field(max_length=MAX_TESTO)


class _Limite:
    """Max `n` eventi ogni `secondi` per chiave (es. tentativi di indovinare il codice d'invito per IP)."""

    def __init__(self, n: int, secondi: int):
        self.n, self.secondi = n, secondi
        self._eventi: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def consenti(self, chiave: str) -> bool:
        ora = time.time()
        with self._lock:
            recenti = [t for t in self._eventi.get(chiave, []) if ora - t < self.secondi]
            if len(recenti) >= self.n:
                self._eventi[chiave] = recenti
                return False
            recenti.append(ora)
            self._eventi[chiave] = recenti
            return True


def crea_app(cfg: Config, gestore: GestoreSessioni | None = None, utenti: Utenti | None = None) -> FastAPI:
    app = FastAPI(title="Master GDR", docs_url=None, redoc_url=None, openapi_url=None)  # niente documentazione API pubblica
    gestore = gestore or GestoreSessioni(cfg)
    utenti = utenti or Utenti(cfg.cartella_salvataggi)
    limite_codice = _Limite(5, 60)

    @app.middleware("http")
    async def intestazioni_sicurezza(request: Request, call_next):
        r = await call_next(request)
        r.headers["X-Content-Type-Options"] = "nosniff"
        r.headers["X-Frame-Options"] = "DENY"
        r.headers["Referrer-Policy"] = "same-origin"
        r.headers["Content-Security-Policy"] = "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; frame-ancestors 'none'"
        if request.url.path.startswith("/api/"):
            r.headers["Cache-Control"] = "no-store"
        return r

    # --- Utente corrente ---------------------------------------------------------------
    def utente_opzionale(request: Request) -> str | None:
        return utenti.utente_da_token(request.cookies.get(COOKIE))

    def utente_corrente(utente: str | None = Depends(utente_opzionale)) -> str:
        if utente is None:
            raise HTTPException(401, "Devi accedere.")
        return utente

    def imposta_cookie(risposta: Response, nome: str) -> None:
        risposta.set_cookie(COOKIE, utenti.crea_token(nome), max_age=30 * 24 * 3600, httponly=True, samesite="lax", secure=cfg.cookie_sicuro, path="/")

    # --- Accesso -----------------------------------------------------------------------
    @app.get("/api/io")
    def io(utente: str | None = Depends(utente_opzionale)) -> dict:
        return {
            "utente": utente,
            "admin": utente in cfg.admin if utente else False,
            "registrazione_aperta": cfg.codice_invito is not None,
            "creazione": opzioni_creazione(),
        }

    @app.post("/api/registrati")
    def registrati(dati: Registrazione, request: Request, risposta: Response) -> dict:
        if cfg.codice_invito is None:
            raise HTTPException(403, "La registrazione è chiusa.")
        if not limite_codice.consenti(request.client.host if request.client else "?"):
            raise HTTPException(429, "Troppi tentativi: riprova tra un minuto.")
        if not hmac.compare_digest(dati.codice.encode(), cfg.codice_invito.encode()):
            raise HTTPException(403, "Codice d'invito errato.")
        try:
            nome = utenti.registra(dati.nome, dati.password)
        except ErroreUtente as e:
            raise HTTPException(400, str(e))
        imposta_cookie(risposta, nome)
        return {"utente": nome}

    @app.post("/api/accedi")
    def accedi(dati: Credenziali, risposta: Response) -> dict:
        try:
            nome = utenti.verifica(dati.nome, dati.password)
        except ErroreUtente as e:
            raise HTTPException(401, str(e))
        imposta_cookie(risposta, nome)
        return {"utente": nome}

    @app.post("/api/esci")
    def esci(risposta: Response) -> dict:
        risposta.delete_cookie(COOKIE, path="/")
        return {"ok": True}

    # --- Avventure e partite -----------------------------------------------------------
    @app.get("/api/avventure")
    def avventure(utente: str = Depends(utente_corrente)) -> dict:
        return {"avventure": gestore.riepilogo(utente)}

    def sessione_di(utente: str, avventura: str) -> Sessione:
        if gestore.catalogo.ottieni(avventura) is None:
            raise HTTPException(404, "Avventura inesistente.")
        return gestore.sessione(utente, avventura)

    def con_partita(utente: str, avventura: str) -> Sessione:
        sess = sessione_di(utente, avventura)
        if sess.stato is None and not sess.carica():
            raise HTTPException(409, "Nessuna partita in corso in questa avventura: creane una.")
        return sess

    @app.post("/api/partite/{avventura}/nuova")
    def nuova(avventura: str, dati: NuovaPartita, utente: str = Depends(utente_corrente)) -> dict:
        sess = sessione_di(utente, avventura)
        try:
            sess.nuova(dati.nome, dati.classe, dati.valori)
        except ValueError as e:
            raise HTTPException(400, str(e))
        return {"vista": sess.vista()}

    @app.post("/api/partite/{avventura}/continua")
    @app.get("/api/partite/{avventura}/stato")
    def stato(avventura: str, utente: str = Depends(utente_corrente)) -> dict:
        sess = con_partita(utente, avventura)
        return {"vista": sess.vista()}

    def _turno(sess: Sessione, utente: str, testo: str, iniziale: bool = False) -> dict:
        try:
            esito = sess.inizia() if iniziale else sess.turno(testo)
        except SessioneOccupata as e:
            raise HTTPException(409, str(e))
        except Exception as e:  # modello spento, rete... il turno è già stato annullato dall'agente
            raise HTTPException(502, f"Errore nella chiamata al modello: {e}")
        if utente not in cfg.admin:
            esito["tool"] = []  # il dettaglio dei tool contiene segreti dei PNG e retroscena
        return {**esito, "vista": sess.vista()}

    def _flusso(sess: Sessione, utente: str, testo: str, iniziale: bool) -> StreamingResponse:
        """Il turno in streaming: righe JSON (una per riga) man mano che il narratore scrive.

            {"tipo": "testo", "t": "..."}      un pezzetto di testo da accodare
            {"tipo": "scarta"}                  il testo mostrato finora non era la narrazione: toglilo
            {"tipo": "fine", "esito": {...}}    turno concluso (stesso contenuto della risposta non in streaming)
            {"tipo": "errore", "stato": 409, "detail": "..."}
        Il turno gira in un thread a parte e passa i pezzetti con una coda: così non si blocca il server.
        """
        coda: queue.Queue = queue.Queue()

        def su_testo(pezzo: str | None) -> None:
            coda.put({"tipo": "scarta"} if pezzo is None else {"tipo": "testo", "t": pezzo})

        def lavora() -> None:
            try:
                esito = sess.inizia(su_testo) if iniziale else sess.turno(testo, su_testo)
                if utente not in cfg.admin:
                    esito["tool"] = []
                coda.put({"tipo": "fine", "esito": {**esito, "vista": sess.vista()}})
            except SessioneOccupata as e:
                coda.put({"tipo": "errore", "stato": 409, "detail": str(e)})
            except Exception as e:  # modello spento, rete...: il turno è già stato annullato dall'agente
                coda.put({"tipo": "errore", "stato": 502, "detail": f"Errore nella chiamata al modello: {e}"})
            coda.put(None)

        threading.Thread(target=lavora, daemon=True, name="turno-stream").start()

        def righe():
            while (voce := coda.get()) is not None:
                yield json.dumps(voce, ensure_ascii=False) + "\n"

        return StreamingResponse(righe(), media_type="application/x-ndjson", headers={"X-Accel-Buffering": "no"})  # niente buffering se dietro nginx

    @app.post("/api/partite/{avventura}/inizia-stream")
    def inizia_stream(avventura: str, utente: str = Depends(utente_corrente)) -> StreamingResponse:
        return _flusso(con_partita(utente, avventura), utente, "", True)

    @app.post("/api/partite/{avventura}/turno-stream")
    def turno_stream(avventura: str, azione: Azione, utente: str = Depends(utente_corrente)) -> StreamingResponse:
        testo = azione.testo.strip()
        if not testo:
            raise HTTPException(400, "Scrivi cosa fa il tuo personaggio.")
        return _flusso(con_partita(utente, avventura), utente, testo, False)

    @app.post("/api/partite/{avventura}/inizia")
    def inizia(avventura: str, utente: str = Depends(utente_corrente)) -> dict:
        return _turno(con_partita(utente, avventura), utente, "", iniziale=True)

    @app.post("/api/partite/{avventura}/turno")
    def turno(avventura: str, azione: Azione, utente: str = Depends(utente_corrente)) -> dict:
        testo = azione.testo.strip()
        if not testo:
            raise HTTPException(400, "Scrivi cosa fa il tuo personaggio.")
        return _turno(con_partita(utente, avventura), utente, testo)

    @app.post("/api/partite/{avventura}/annulla")
    def annulla(avventura: str, utente: str = Depends(utente_corrente)) -> dict:
        """Annulla l'ultimo turno (anche se aveva chiuso la partita: per questo non passa da con_partita)."""
        sess = sessione_di(utente, avventura)
        if sess.stato is None and not sess.carica(anche_conclusa=True):
            raise HTTPException(409, "Nessuna partita in questa avventura.")
        try:
            testo = sess.annulla()
        except (SessioneOccupata, RuntimeError) as e:  # turno in corso, oppure niente da annullare
            raise HTTPException(409, str(e))
        return {"testo": testo, "vista": sess.vista()}

    # --- File statici ------------------------------------------------------------------
    # Solo le immagini di ogni avventura: la sua lore (con i segreti) non viene mai servita.
    for avv_id in gestore.catalogo.ids():
        app.mount(f"/avventure/{avv_id}/assets", StaticFiles(directory=gestore.catalogo.ottieni(avv_id).cartella / "assets"), name=f"assets-{avv_id}")  # type: ignore[union-attr]
    app.mount("/web", StaticFiles(directory=RADICE / "web"), name="web")

    @app.get("/")
    def indice() -> FileResponse:
        return FileResponse(RADICE / "web" / "index.html")

    return app
