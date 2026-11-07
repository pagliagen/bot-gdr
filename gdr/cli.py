"""Interfaccia da terminale. È l'UNICO file che usa input() e print().

Per aggiungere Telegram o una GUI basta scrivere un file gemello di questo che
crei un `Agente` e chiami `agente.turno(testo)`.
"""

from __future__ import annotations

import json

from . import state as salvataggi
from .agent import Agente
from .character_creation import ARRAY_STANDARD, CLASSI, crea_personaggio
from .config import Config
from .llm import crea_provider
from .lore import GIORNI_AVVENTURA, Mondo, carica_mondo
from .models import STATISTICHE, StatoPartita

GRIGIO, RESET = "\033[90m", "\033[0m"

AIUTO = """Comandi: /scheda  /mappa  /diario  /debug (attiva/disattiva)  /salva  /aiuto  /esci
Qualsiasi altro testo è l'azione del tuo personaggio."""


def _chiedi(prompt: str) -> str:
    return input(prompt).strip()


def creazione_guidata(mondo: Mondo) -> StatoPartita:
    print("\n=== Creazione del personaggio ===")
    while True:
        nome = _chiedi("Come si chiama il tuo eroe? ")
        if 1 <= len(nome) <= 30:
            break
        print("  Il nome deve avere tra 1 e 30 caratteri.")

    print("\nClassi disponibili:")
    for nome_classe, info in CLASSI.items():
        print(f"  - {nome_classe}: {info['descrizione']}")
    while True:
        classe = _chiedi("Scegli la classe: ").capitalize()
        if classe in CLASSI:
            break
        print(f"  Classe non valida. Scegli tra: {', '.join(CLASSI)}.")

    print(f"\nAssegna i valori {ARRAY_STANDARD} a Forza, Agilità e Intelletto (ognuno una volta).")
    print("Esempio: '15 13 10' = Forza 15, Agilità 13, Intelletto 10.")
    while True:
        try:
            valori = [int(x) for x in _chiedi("Forza Agilità Intelletto: ").split()]
            if len(valori) != len(STATISTICHE):
                raise ValueError("Servono esattamente tre numeri.")
            return _stato_iniziale(crea_personaggio(nome, classe, dict(zip(STATISTICHE, valori))), mondo)
        except ValueError as e:
            print(f"  Non va bene: {e}")


def _stato_iniziale(personaggio, mondo: Mondo) -> StatoPartita:
    stato = StatoPartita(personaggio=personaggio, luogo_corrente="", luoghi_visitati=[])
    mondo.stato_iniziale(stato)  # luogo di partenza, flag e orologio vengono dalla lore
    return stato


def orologio(stato: StatoPartita) -> str:
    return f"Giorno {stato.giorno}/{GIORNI_AVVENTURA}, {stato.ora:02d}:00"


def mostra_scheda(stato: StatoPartita) -> None:
    p = stato.personaggio
    print(f"\n{p.nome} — {p.classe} — PF {p.pf}/{p.pf_max}")
    for k, v in p.statistiche.items():
        mod = (v - 10) // 2
        print(f"  {k.capitalize():<11}{v:>3} ({mod:+d})")
    print(f"  Inventario: {', '.join(p.inventario) or 'vuoto'}")
    print(f"  Luogo: {stato.luogo_corrente} — {orologio(stato)}\n")


def avvia(cfg: Config, nuova: bool, debug: bool) -> None:
    mondo = carica_mondo(cfg.percorso_lore)
    stato = None if nuova else salvataggi.carica(cfg.percorso_salvataggio)
    if stato and stato.personaggio.pf <= 0:
        print("Il tuo eroe del salvataggio è caduto. Si ricomincia da capo!")
        stato = None
    if stato and stato.finale:
        print("L'avventura salvata è già conclusa. Si ricomincia da capo!")
        stato = None
    if stato:
        print(f"Bentornato, {stato.personaggio.nome}! (partita ripresa, turno {stato.turno})")
    else:
        stato = creazione_guidata(mondo)
        mostra_scheda(stato)

    modo_debug = {"attivo": debug}

    def su_evento(tipo: str, dati: dict) -> None:
        if not modo_debug["attivo"]:
            return
        if tipo == "tool_call":
            args = json.dumps(dati["argomenti"], ensure_ascii=False)
            print(f"{GRIGIO}  [tool] {dati['nome']}({args}){RESET}")
        else:
            print(f"{GRIGIO}  [esito] {json.dumps(dati['risultato'], ensure_ascii=False)}{RESET}")

    agente = Agente(
        provider=crea_provider(cfg),
        stato=stato,
        percorso_prompt=cfg.percorso_prompt,
        max_iterazioni=cfg.max_iterazioni,
        soglia_messaggi=cfg.soglia_messaggi,
        messaggi_recenti=cfg.messaggi_recenti,
        su_evento=su_evento,
        mondo=mondo,
    )

    def gioca(testo: str) -> bool:
        """Esegue un turno; restituisce False se la partita è finita."""
        try:
            print("\n" + agente.turno(testo) + "\n")
        except Exception as e:
            print(f"\n[Errore nella chiamata al modello: {e}]\nIl turno è stato annullato, riprova.\n")
            return True
        salvataggi.salva(stato, cfg.percorso_salvataggio)
        if stato.finale:
            print(f"*** FINE DELL'AVVENTURA: {mondo.valuta_finale(stato.flag)['nome']} ***")
            return False
        if stato.personaggio.pf <= 0:
            print("*** Il tuo eroe è caduto. Fine della partita. ***")
            return False
        return True

    if not stato.messaggi:
        print("\n(Il narratore prepara la scena...)")
        if not gioca("Inizia l'avventura: è la mattina del primo giorno. Presenta la scena iniziale (tieni conto degli eventi già in corso nel diario) e il personaggio, e lascia a me la prima mossa."):
            return
    print(AIUTO + "\n")

    while True:
        try:
            comando = _chiedi(f"[{orologio(stato)} · {stato.luogo_corrente}] > ")
        except (EOFError, KeyboardInterrupt):
            comando = "/esci"
        if not comando:
            continue
        if comando == "/esci":
            salvataggi.salva(stato, cfg.percorso_salvataggio)
            print("Partita salvata. A presto!")
            return
        if comando == "/scheda":
            mostra_scheda(stato)
        elif comando == "/mappa":
            print(f"Sei in: {stato.luogo_corrente} ({orologio(stato)}). Visitati: {', '.join(stato.luoghi_visitati)}")
        elif comando == "/diario":
            print("\n".join(stato.diario) or "(diario vuoto)")
        elif comando == "/debug":
            modo_debug["attivo"] = not modo_debug["attivo"]
            print(f"Debug {'attivo' if modo_debug['attivo'] else 'disattivato'}.")
        elif comando == "/salva":
            salvataggi.salva(stato, cfg.percorso_salvataggio)
            print("Salvato.")
        elif comando == "/aiuto":
            print(AIUTO)
        elif not gioca(comando):
            return
