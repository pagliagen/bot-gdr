"""Logica della creazione del personaggio (nessun input/print: li fa l'interfaccia).

Ispirata al D&D 5e SRD, semplificata a tre statistiche:
- valori dall'"array standard" ridotto: 15, 13, 10, da assegnare come si vuole;
- PF iniziali = dado vita massimo della classe + 2.
"""

from __future__ import annotations

from .models import STATISTICHE, Personaggio

ARRAY_STANDARD = (15, 13, 10)

CLASSI: dict[str, dict] = {
    "Guerriero": {
        "descrizione": "Combattente robusto (dado vita d10). Statistica consigliata: Forza.",
        "dado_vita": 10,
        "equipaggiamento": ["spada lunga", "scudo", "cotta di maglia", "razione di viaggio"],
    },
    "Ladro": {
        "descrizione": "Furtivo e scaltro (dado vita d8). Statistica consigliata: Agilità.",
        "dado_vita": 8,
        "equipaggiamento": ["stocco", "arco corto", "arnesi da scasso", "razione di viaggio"],
    },
    "Mago": {
        "descrizione": "Studioso di arti arcane (dado vita d6). Statistica consigliata: Intelletto.",
        "dado_vita": 6,
        "equipaggiamento": ["bastone", "libro degli incantesimi", "borsa dei componenti", "razione di viaggio"],
    },
}


def crea_personaggio(nome: str, classe: str, assegnazione: dict[str, int]) -> Personaggio:
    """Valida le scelte e costruisce il personaggio. Solleva ValueError con messaggio chiaro."""
    nome = (nome or "").strip()
    if not 1 <= len(nome) <= 30:
        raise ValueError("Il nome deve avere tra 1 e 30 caratteri.")
    if classe not in CLASSI:
        raise ValueError(f"Classe sconosciuta. Scegli tra: {', '.join(CLASSI)}.")
    if set(assegnazione) != set(STATISTICHE) or sorted(assegnazione.values()) != sorted(ARRAY_STANDARD):
        raise ValueError(f"Assegna esattamente i valori {ARRAY_STANDARD}, uno per statistica.")
    pf = CLASSI[classe]["dado_vita"] + 2
    return Personaggio(
        nome=nome,
        classe=classe,
        statistiche=dict(assegnazione),
        pf=pf,
        pf_max=pf,
        inventario=list(CLASSI[classe]["equipaggiamento"]),
    )
