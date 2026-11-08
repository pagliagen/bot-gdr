"""Confronta modelli Ollama sullo stesso scenario: usano i tool giusti? Come scrivono?

Uso:  python scripts/prova_modelli.py qwen3.5:9b gemma4:12b qwen3:14b
Non tocca i salvataggi: lavora su una partita temporanea in memoria.
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from gdr.agent import Agente  # noqa: E402
from gdr.character_creation import crea_personaggio  # noqa: E402
from gdr.config import carica_config  # noqa: E402
from gdr.llm.ollama_provider import OllamaProvider  # noqa: E402
from gdr.lore import carica_mondo  # noqa: E402
from gdr.models import StatoPartita  # noqa: E402

# (azione del giocatore, tool che ci aspettiamo vengano chiamati)
SCENARIO = [
    ("Provo a scassinare la serratura della porta sul retro.", "prova_abilita"),
    ("Prendo la lanterna appesa al muro.", "inventario"),
    ("Vado al Mulino Alto.", "sposta_in"),
    ("Chi è Sorella Brina?", "consulta_lore"),
    ("Mi riposo in un fienile per 8 ore.", "avanza_tempo"),
    ("Un ladro mi colpisce con il pugnale!", "modifica_punti_vita"),
]


def prova(modello: str, cfg) -> None:
    print(f"\n{'=' * 60}\nMODELLO: {modello}\n{'=' * 60}")
    pg = crea_personaggio("Prova", "Ladro", {"forza": 10, "agilita": 15, "intelletto": 13})
    mondo = carica_mondo(cfg.percorso_avventure / "acquaverde")  # lo scenario è scritto per questa avventura
    stato = StatoPartita(personaggio=pg, luogo_corrente="", luoghi_visitati=[])
    mondo.stato_iniziale(stato)
    chiamati: list[str] = []
    errori: list[str] = []

    def su_evento(tipo, dati):
        if tipo == "tool_call":
            chiamati.append(dati["nome"])
        elif not dati["risultato"].get("ok"):
            errori.append(f"{dati['nome']}: {dati['risultato'].get('errore')}")

    agente = Agente(OllamaProvider(modello, cfg.ollama_host, cfg.ollama_num_ctx), stato, cfg.percorso_prompt, su_evento=su_evento, mondo=mondo)
    for azione, atteso in SCENARIO:
        chiamati.clear()
        t0 = time.time()
        try:
            testo = agente.turno(azione)
        except Exception as e:
            print(f"\n> {azione}\n  ERRORE: {e}")
            continue
        esito = "OK " if atteso in chiamati else "MANCA"
        print(f"\n> {azione}\n  [{esito}] atteso={atteso} chiamati={chiamati} ({time.time() - t0:.0f}s)\n  {testo}")
    if errori:
        print("\nErrori dei tool (argomenti sbagliati dal modello):", *errori, sep="\n  - ")


if __name__ == "__main__":
    configurazione = carica_config()
    for nome_modello in sys.argv[1:] or [configurazione.ollama_model]:
        prova(nome_modello, configurazione)
