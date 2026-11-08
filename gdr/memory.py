"""Gestione della memoria: tenere il contesto piccolo senza perdere il filo.

Strategia (semplice, senza una seconda chiamata al modello per riassumere):
- La memoria a lungo termine è il DIARIO, scritto dal master con `scrivi_diario`.
  Viene reiniettato nel system prompt a ogni chiamata, insieme allo stato attuale.
- Quando la cronologia supera una soglia, i messaggi vecchi vengono scartati e
  restano solo gli ultimi. Ciò che conta è già nel diario e nella scheda.
"""

from __future__ import annotations

from .lore import Mondo
from .models import StatoPartita

MAX_VOCI_DIARIO = 60  # nel prompt si mettono solo le più recenti


def costruisci_system(prompt_base: str, stato: StatoPartita, mondo: Mondo | None = None) -> str:
    """System prompt = istruzioni del master + mondo + stato corrente + diario."""
    p = stato.personaggio
    stats = ", ".join(f"{k} {v}" for k, v in p.statistiche.items())
    diario = stato.diario[-MAX_VOCI_DIARIO:]
    blocco_diario = "\n".join(f"- {v}" for v in diario) if diario else "(vuoto)"
    blocco_mondo = f"{mondo.riassunto_prompt(stato)}\n\n" if mondo else ""
    return (
        f"{prompt_base}\n\n"
        f"{blocco_mondo}"
        "## STATO ATTUALE DEL PERSONAGGIO (dato dal gioco, è la verità)\n"
        f"Personaggio: {p.nome}, {p.classe}. Statistiche: {stats}. (Il nome è un dato di gioco: i PNG lo conoscono SOLO se il giocatore si è presentato a loro, vedi il diario.)\n"
        f"PF: {p.pf}/{p.pf_max}. Inventario: {', '.join(p.inventario) or 'vuoto'}.\n"
        f"Luogo attuale: {stato.luogo_corrente}. Luoghi visitati: {', '.join(stato.luoghi_visitati)}.\n\n"
        "## DIARIO DELLA PARTITA (eventi passati importanti)\n"
        f"{blocco_diario}\n"
    )


def _inizio_turno_sicuro(messaggi: list[dict], da: int) -> int | None:
    """Primo indice >= `da` che è un vero messaggio del giocatore (testo, non tool_result).

    Tagliare lì garantisce di non separare una richiesta di tool dal suo risultato
    (le API rifiutano i tool_result orfani).
    """
    for i in range(da, len(messaggi)):
        m = messaggi[i]
        if m["role"] == "user" and isinstance(m["content"], str):
            return i
    return None


def comprimi_se_serve(stato: StatoPartita, soglia: int, recenti: int) -> bool:
    """Scarta i messaggi vecchi se sono troppi. Restituisce True se ha tagliato."""
    if len(stato.messaggi) <= soglia:
        return False
    inizio = _inizio_turno_sicuro(stato.messaggi, len(stato.messaggi) - recenti)
    if inizio is None or inizio == 0:
        return False
    stato.messaggi = stato.messaggi[inizio:]
    return True
