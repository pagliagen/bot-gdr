"""Utenti, password e login (per la versione online).

Solo libreria standard:
- le password si salvano con scrypt + un sale casuale (mai in chiaro);
- il login è un cookie firmato con HMAC-SHA256 (non falsificabile senza il segreto) con scadenza;
- i tentativi sbagliati rallentano chi prova a indovinare una password.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import threading
import time
from pathlib import Path

NOME_VALIDO = re.compile(r"^[a-z0-9_]{3,20}$")  # niente '/', '.', spazi: il nome diventa una cartella
DURATA_LOGIN = 30 * 24 * 3600  # secondi
TENTATIVI_MAX = 5
BLOCCO_SECONDI = 60


class ErroreUtente(ValueError):
    """Errore da mostrare all'utente (nome non valido, password errata...)."""


def _hash(password: str, sale: bytes) -> bytes:
    return hashlib.scrypt(password.encode(), salt=sale, n=2**14, r=8, p=1, dklen=32)


class Utenti:
    def __init__(self, cartella: Path):
        self.cartella = Path(cartella)
        self.cartella.mkdir(parents=True, exist_ok=True)
        self._file = self.cartella / "utenti.json"
        self._lock = threading.Lock()
        self._segreto = self._carica_segreto()
        self._falliti: dict[str, list[float]] = {}  # chiave (nome) -> istanti dei tentativi sbagliati

    # --- Segreto per firmare i cookie (generato una volta, poi riusato) ----------------
    def _carica_segreto(self) -> bytes:
        f = self.cartella / ".segreto"
        if f.exists():
            return bytes.fromhex(f.read_text().strip())
        s = secrets.token_bytes(32)
        f.write_text(s.hex())
        os.chmod(f, 0o600)
        return s

    def _leggi(self) -> dict:
        return json.loads(self._file.read_text(encoding="utf-8")) if self._file.exists() else {}

    def _scrivi(self, dati: dict) -> None:
        tmp = self._file.with_suffix(".tmp")
        tmp.write_text(json.dumps(dati, indent=2), encoding="utf-8")
        os.chmod(tmp, 0o600)
        os.replace(tmp, self._file)

    # --- Registrazione e accesso -------------------------------------------------------
    @staticmethod
    def normalizza(nome: str) -> str:
        n = (nome or "").strip().lower()
        if not NOME_VALIDO.match(n):
            raise ErroreUtente("Il nome utente deve avere da 3 a 20 caratteri: lettere, numeri o _ (niente spazi).")
        return n

    def registra(self, nome: str, password: str) -> str:
        n = self.normalizza(nome)
        if len(password or "") < 8:
            raise ErroreUtente("La password deve avere almeno 8 caratteri.")
        with self._lock:
            dati = self._leggi()
            if n in dati:
                raise ErroreUtente("Questo nome utente è già preso.")
            sale = secrets.token_bytes(16)
            dati[n] = {"sale": sale.hex(), "hash": _hash(password, sale).hex(), "creato": int(time.time())}
            self._scrivi(dati)
        return n

    def verifica(self, nome: str, password: str) -> str:
        """Restituisce il nome normalizzato se le credenziali sono giuste; altrimenti ErroreUtente (messaggio generico)."""
        n = (nome or "").strip().lower()
        ora = time.time()
        with self._lock:
            tent = [t for t in self._falliti.get(n, []) if ora - t < BLOCCO_SECONDI]
            if len(tent) >= TENTATIVI_MAX:
                raise ErroreUtente(f"Troppi tentativi: riprova tra {int(BLOCCO_SECONDI - (ora - tent[0])) + 1} secondi.")
            u = self._leggi().get(n)
        # Si calcola sempre l'hash (anche per utenti inesistenti): i tempi non rivelano chi esiste.
        sale = bytes.fromhex(u["sale"]) if u else b"\0" * 16
        calcolato = _hash(password or "", sale)
        ok = bool(u) and hmac.compare_digest(calcolato, bytes.fromhex(u["hash"]))
        with self._lock:
            if not ok:
                tent.append(ora)
                self._falliti[n] = tent
            else:
                self._falliti.pop(n, None)
        if not ok:
            raise ErroreUtente("Nome utente o password errati.")
        return n

    # --- Cookie di sessione ------------------------------------------------------------
    def _firma(self, corpo: bytes) -> str:
        return hmac.new(self._segreto, corpo, hashlib.sha256).hexdigest()

    def crea_token(self, nome: str) -> str:
        corpo = base64.urlsafe_b64encode(json.dumps({"u": nome, "e": int(time.time()) + DURATA_LOGIN}).encode())
        return f"{corpo.decode()}.{self._firma(corpo)}"

    def utente_da_token(self, token: str | None) -> str | None:
        """Il nome utente se il token è autentico, non scaduto e l'utente esiste ancora; altrimenti None."""
        try:
            corpo, firma = (token or "").rsplit(".", 1)
            if not hmac.compare_digest(self._firma(corpo.encode()), firma):
                return None
            dati = json.loads(base64.urlsafe_b64decode(corpo))
            if dati["e"] < time.time() or dati["u"] not in self._leggi():
                return None
            return dati["u"]
        except Exception:
            return None
