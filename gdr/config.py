"""Configurazione: legge le variabili d'ambiente (e il file .env)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

RADICE = Path(__file__).resolve().parent.parent  # cartella del progetto


@dataclass(frozen=True)
class Config:
    provider: str  # "anthropic" oppure "ollama"
    anthropic_api_key: str | None
    anthropic_model: str
    ollama_model: str
    ollama_host: str
    ollama_num_ctx: int  # finestra di contesto da chiedere a Ollama (il default è troppo piccolo)
    max_iterazioni: int  # tetto ai giri del ciclo dell'agente per ogni turno
    soglia_messaggi: int  # oltre questo numero di messaggi si comprime la cronologia
    messaggi_recenti: int  # quanti messaggi recenti tenere quando si comprime
    percorso_prompt: Path
    percorso_avventure: Path  # una cartella per avventura (lore + immagini)
    cartella_salvataggi: Path  # saves/<utente>/<avventura>.json
    # --- Web (accesso con utente e password) ---
    codice_invito: str | None  # senza codice la registrazione è chiusa
    admin: tuple[str, ...]  # utenti che vedono la modalità debug (contiene spoiler)
    cookie_sicuro: bool  # True dietro HTTPS: il cookie di login viaggia solo su connessioni cifrate
    max_turni_contemporanei: int  # turni del narratore eseguiti insieme (la GPU è una sola)
    immagini_attive: bool
    immagini_model: str
    immagini_larghezza: int
    immagini_altezza: int
    immagini_steps: int


def carica_config() -> Config:
    load_dotenv(RADICE / ".env")
    return Config(
        provider=os.getenv("LLM_PROVIDER", "ollama").lower(),
        anthropic_api_key=os.getenv("ANTHROPIC_API_KEY") or None,
        anthropic_model=os.getenv("ANTHROPIC_MODEL", "claude-opus-5-5"),
        ollama_model=os.getenv("OLLAMA_MODEL", "qwen3.5:9b"),
        ollama_host=os.getenv("OLLAMA_HOST", "http://localhost:11434"),
        ollama_num_ctx=int(os.getenv("OLLAMA_NUM_CTX", "16384")),
        max_iterazioni=int(os.getenv("MAX_ITERAZIONI", "8")),
        soglia_messaggi=int(os.getenv("SOGLIA_MESSAGGI", "40")),
        messaggi_recenti=int(os.getenv("MESSAGGI_RECENTI", "12")),
        percorso_prompt=RADICE / "prompts" / "master.md",
        percorso_avventure=RADICE / "avventure",
        cartella_salvataggi=RADICE / "saves",
        codice_invito=os.getenv("CODICE_INVITO") or None,
        admin=tuple(n.strip().lower() for n in os.getenv("ADMIN", "").split(",") if n.strip()),
        cookie_sicuro=os.getenv("COOKIE_SICURO", "off").lower() in ("on", "1", "si", "true"),
        max_turni_contemporanei=max(1, int(os.getenv("MAX_TURNI_CONTEMPORANEI", "1"))),
        immagini_attive=os.getenv("IMMAGINI", "on").lower() not in ("off", "0", "no", "false"),
        immagini_model=os.getenv("IMMAGINI_MODEL", "x/z-image-turbo"),
        immagini_larghezza=int(os.getenv("IMMAGINI_LARGHEZZA", "1024")),
        immagini_altezza=int(os.getenv("IMMAGINI_ALTEZZA", "576")),
        immagini_steps=int(os.getenv("IMMAGINI_STEPS", "9")),
    )
