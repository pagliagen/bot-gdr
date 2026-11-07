"""Generazione di immagini con un modello locale (Ollama), in background.

Due pezzi:
- un *generatore* (interfaccia + implementazione Ollama): prompt -> bytes PNG;
- una *coda* con un thread che li esegue uno alla volta, così il turno di gioco
  non resta bloccato (un'immagine richiede circa 30 secondi).

Per usare un altro motore (ComfyUI, Draw Things...) basta scrivere un'altra
classe con il metodo `genera`.
"""

from __future__ import annotations

import base64
import io
import json
import queue
import threading
import time
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Callable

from .config import Config


class GeneratoreImmagini(ABC):
    @abstractmethod
    def genera(self, prompt: str) -> bytes:
        """Restituisce i byte di un'immagine (PNG). Solleva RuntimeError se fallisce."""


class OllamaImmagini(GeneratoreImmagini):
    """Modelli di immagini di Ollama (sperimentale, macOS): POST /api/generate."""

    def __init__(self, modello: str, host: str, larghezza: int, altezza: int, steps: int, timeout: int = 900):
        self.modello, self.host = modello, host.rstrip("/")
        self.larghezza, self.altezza, self.steps, self.timeout = larghezza, altezza, steps, timeout

    def genera(self, prompt: str, tentativi: int = 3) -> bytes:
        """Chiama Ollama; sugli errori del server (5xx) riprova, perché il runner delle immagini ogni tanto cade."""
        ultimo: RuntimeError | None = None
        for n in range(tentativi):
            try:
                return self._una_volta(prompt)
            except _ErroreServer as e:
                ultimo = RuntimeError(str(e))
                time.sleep(3)
        raise ultimo  # type: ignore[misc]

    def _una_volta(self, prompt: str) -> bytes:
        corpo = json.dumps(
            {"model": self.modello, "prompt": prompt, "stream": False, "width": self.larghezza, "height": self.altezza, "steps": self.steps}
        ).encode()
        richiesta = urllib.request.Request(f"{self.host}/api/generate", data=corpo, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(richiesta, timeout=self.timeout) as r:
                dati = json.load(r)
        except urllib.error.HTTPError as e:
            msg = f"Ollama ha risposto {e.code}: {e.read().decode(errors='replace')[:300]}"
            raise (_ErroreServer(msg) if e.code >= 500 else RuntimeError(msg)) from e
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            raise RuntimeError(f"Ollama non raggiungibile: {e}") from e
        immagine = dati.get("image") or (dati.get("images") or [None])[0]
        if not immagine:
            raise RuntimeError(dati.get("error") or f"Il modello '{self.modello}' non ha restituito un'immagine (è un modello di immagini?).")
        return base64.b64decode(immagine)


class _ErroreServer(RuntimeError):
    """Errore 5xx di Ollama: vale la pena riprovare."""


def crea_generatore(cfg: Config) -> GeneratoreImmagini | None:
    """None se le immagini sono disattivate (IMMAGINI=off nel .env)."""
    if not cfg.immagini_attive:
        return None
    return OllamaImmagini(cfg.immagini_model, cfg.ollama_host, cfg.immagini_larghezza, cfg.immagini_altezza, cfg.immagini_steps)


def salva_webp(png: bytes, percorso: Path) -> None:
    """Converte in webp (più leggero) e salva in modo atomico."""
    from PIL import Image

    percorso.parent.mkdir(parents=True, exist_ok=True)
    tmp = percorso.with_suffix(".tmp")
    Image.open(io.BytesIO(png)).convert("RGB").save(tmp, "WEBP", quality=88)
    tmp.replace(percorso)


class CodaImmagini:
    """Esegue le richieste una alla volta in un thread, senza bloccare chi le chiede."""

    def __init__(self, generatore: GeneratoreImmagini):
        self.generatore = generatore
        self._coda: queue.Queue = queue.Queue()
        self._in_corso: set[str] = set()
        self._lock = threading.Lock()
        self.ultimo_errore: str | None = None
        threading.Thread(target=self._lavora, daemon=True, name="coda-immagini").start()

    @property
    def n_in_corso(self) -> int:
        with self._lock:
            return len(self._in_corso)

    def in_corso(self, percorso: Path) -> bool:
        with self._lock:
            return str(percorso) in self._in_corso

    def accoda(self, prompt: str, percorso: Path, al_termine: Callable[[bool], None] | None = None) -> bool:
        """Mette in coda l'immagine. False se esiste già o è già in lavorazione."""
        with self._lock:
            if percorso.exists() or str(percorso) in self._in_corso:
                return False
            self._in_corso.add(str(percorso))
        self._coda.put((prompt, percorso, al_termine))
        return True

    def _lavora(self) -> None:
        while True:
            prompt, percorso, al_termine = self._coda.get()
            ok = False
            try:
                salva_webp(self.generatore.genera(prompt), percorso)
                self.ultimo_errore, ok = None, True
            except Exception as e:  # un errore non deve mai fermare il thread
                self.ultimo_errore = str(e)
            finally:
                with self._lock:
                    self._in_corso.discard(str(percorso))
            if al_termine:
                try:
                    al_termine(ok)
                except Exception:
                    pass
