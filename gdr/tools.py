"""Gli strumenti (tool) che il Game Master può chiamare.

Due parti:
1. TOOL_SCHEMAS: la descrizione dei tool che mandiamo al modello (nome, a cosa
   serve, quali argomenti). È l'unica cosa che il modello "vede".
2. La classe Strumenti: il codice che li esegue davvero sullo stato di gioco.

Regola d'oro: un tool NON solleva mai eccezioni verso l'agente. Se qualcosa va
storto restituisce {"ok": False, "errore": "..."}: il modello legge l'errore e
può correggersi (es. riprovare con un argomento valido).
"""

from __future__ import annotations

import random
from typing import Any, Callable

from . import rules
from .lore import Mondo
from .models import StatoPartita

MAX_OGGETTI = 30

# --- Schemi dei tool (formato JSON Schema, lo stesso usato da Anthropic) ---------
TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "name": "tira_dadi",
        "description": "Tira dadi con una formula (es. '1d20+3', '2d6'). Usalo per qualsiasi tiro casuale che non sia una prova di abilità (es. danni, tabelle casuali).",
        "input_schema": {
            "type": "object",
            "properties": {
                "formula": {"type": "string", "description": "Formula NdF+M, es. '1d20+3'."},
                "motivo": {"type": "string", "description": "Perché si tira (per il diario/debug)."},
            },
            "required": ["formula", "motivo"],
        },
    },
    {
        "name": "prova_abilita",
        "description": "Prova di abilità del giocatore: d20 + modificatore della statistica contro una difficoltà (CD). CD standard 5e: 5 molto facile, 10 facile, 15 media, 20 difficile, 25 molto difficile, 30 quasi impossibile. Restituisce successo o fallimento: devi rispettare l'esito.",
        "input_schema": {
            "type": "object",
            "properties": {
                "statistica": {"type": "string", "enum": ["forza", "agilita", "intelletto"]},
                "difficolta": {"type": "integer", "description": "La CD da battere, tra 1 e 30."},
                "motivo": {"type": "string", "description": "Cosa sta tentando il giocatore."},
            },
            "required": ["statistica", "difficolta"],
        },
    },
    {
        "name": "leggi_scheda",
        "description": "Restituisce la scheda del personaggio: nome, classe, statistiche, punti vita, inventario.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "modifica_punti_vita",
        "description": "Cambia i punti vita del personaggio. delta negativo = danno, positivo = cura. Usalo SEMPRE per ferite e guarigioni.",
        "input_schema": {
            "type": "object",
            "properties": {
                "delta": {"type": "integer", "description": "Variazione dei PF (es. -4 o +2). Non può essere 0."},
                "motivo": {"type": "string", "description": "Causa della variazione."},
            },
            "required": ["delta", "motivo"],
        },
    },
    {
        "name": "inventario",
        "description": "Gestisce l'inventario. azione: 'aggiungi', 'rimuovi' o 'elenca'. Per aggiungere/rimuovere serve il nome dell'oggetto. Rimuovere un oggetto non posseduto fallisce.",
        "input_schema": {
            "type": "object",
            "properties": {
                "azione": {"type": "string", "enum": ["aggiungi", "rimuovi", "elenca"]},
                "oggetto": {"type": "string", "description": "Nome dell'oggetto (non serve per 'elenca')."},
            },
            "required": ["azione"],
        },
    },
    {
        "name": "sposta_in",
        "description": "Sposta il personaggio: in una ZONA del luogo in cui si trova (la locanda, l'emporio, la piazza... nessun tempo perso) oppure in un altro LUOGO collegato (viaggio, fa passare ore). Il gioco rifiuta le zone chiuse e dice quando aprono.",
        "input_schema": {
            "type": "object",
            "properties": {"luogo": {"type": "string", "description": "Nome della zona o del luogo, es. 'Emporio', 'Locanda del Pesce Pigro', 'Mulino Alto'."}},
            "required": ["luogo"],
        },
    },
    {
        "name": "descrivi_mappa",
        "description": "Restituisce la posizione attuale e tutti i luoghi già visitati.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "scrivi_diario",
        "description": "Annota nel diario un evento importante (incontri, promesse, scoperte, decisioni). Il diario è la tua memoria a lungo termine: i messaggi vecchi vengono dimenticati, il diario no.",
        "input_schema": {
            "type": "object",
            "properties": {"evento": {"type": "string", "description": "Frase breve che riassume l'evento."}},
            "required": ["evento"],
        },
    },
    {
        "name": "avanza_tempo",
        "description": "Fa passare il tempo di gioco (riposo, attesa, ricerche lunghe, lavori). Il mondo va avanti da solo: allo scoccare dei giorni scattano eventi, che questo strumento ti restituisce. Gli spostamenti tra luoghi fanno già passare il tempo da soli (sposta_in).",
        "input_schema": {
            "type": "object",
            "properties": {
                "ore": {"type": "integer", "description": "Ore che passano, da 1 a 24."},
                "motivo": {"type": "string", "description": "Cosa fa il giocatore nel frattempo."},
            },
            "required": ["ore"],
        },
    },
    {
        "name": "consulta_lore",
        "description": "Cerca nella bibbia del mondo: un luogo, un PNG, una fazione, una religione, oppure 'storia', 'religioni', 'fazioni', 'luoghi', 'png'. Restituisce i fatti da rispettare. I campi 'segreto_riservato_al_master' sono solo per te: non rivelarli finché il giocatore non li scopre.",
        "input_schema": {
            "type": "object",
            "properties": {"argomento": {"type": "string", "description": "Es. 'Sorella Brina', 'Mulino Alto', 'religioni'."}},
            "required": ["argomento"],
        },
    },
    {
        "name": "imposta_flag",
        "description": "Registra un progresso importante dell'avventura (es. 'contratto_trovato', 'borgo_evacuato'). Funziona solo se il giocatore è nel luogo giusto, ha i requisiti e l'ULTIMA prova_abilita è riuscita con la statistica e la CD giuste. Se ti viene rifiutato, leggi l'errore: dice cosa manca.",
        "input_schema": {
            "type": "object",
            "properties": {
                "flag": {"type": "string", "description": "Nome del flag."},
                "motivo": {"type": "string", "description": "Cosa ha fatto il giocatore."},
            },
            "required": ["flag"],
        },
    },
    {
        "name": "valuta_finale",
        "description": "Chiude l'avventura. Chiamalo SOLO quando il tempo ha raggiunto il momento finale (te lo segnalano avanza_tempo e sposta_in con momento_finale_raggiunto). Il codice decide il finale in base ai progressi del giocatore: tu lo racconti.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "illustra_scena",
        "description": "Genera un'illustrazione per un momento visivo importante (entrare in un luogo interno come una locanda, incontrare un PNG chiave, una scena drammatica). Usalo con parsimonia: massimo una volta ogni pochi turni. L'immagine arriva dopo circa 30 secondi: non aspettarla, continua a narrare.",
        "input_schema": {
            "type": "object",
            "properties": {
                "descrizione": {"type": "string", "description": "Descrizione VISIVA in INGLESE, concreta, 1-2 frasi: luogo, luce, azione, e i PNG per nome (il loro aspetto lo aggiunge il gioco). Non descrivere l'aspetto del giocatore. Es. 'inside a cozy medieval tavern, a round innkeeper with a huge mustache behind the bar, warm candlelight'."},
                "didascalia": {"type": "string", "description": "Breve didascalia in italiano (max 80 caratteri)."},
            },
            "required": ["descrizione"],
        },
    },
]


def _errore(msg: str) -> dict:
    return {"ok": False, "errore": msg}


def _intero(valore: Any, nome: str) -> int:
    """Converte in int accettando anche "5" (i modelli piccoli sbagliano spesso il tipo)."""
    if isinstance(valore, bool):
        raise rules.ErroreRegole(f"'{nome}' deve essere un numero intero.")
    if isinstance(valore, int):
        return valore
    if isinstance(valore, str) and valore.strip().lstrip("+-").isdigit():
        return int(valore)
    raise rules.ErroreRegole(f"'{nome}' deve essere un numero intero.")


def _testo(valore: Any, nome: str, max_len: int) -> str:
    if not isinstance(valore, str) or not valore.strip():
        raise rules.ErroreRegole(f"'{nome}' deve essere un testo non vuoto.")
    valore = valore.strip()
    if len(valore) > max_len:
        raise rules.ErroreRegole(f"'{nome}' è troppo lungo (massimo {max_len} caratteri).")
    return valore


class Strumenti:
    """Esegue i tool sullo stato della partita."""

    def __init__(self, stato: StatoPartita, rng: random.Random | None = None, mondo: Mondo | None = None):
        self.stato = stato
        self.rng = rng or random.Random()
        self.mondo = mondo  # senza lore gli strumenti del mondo restano disattivati
        # Funzione (descrizione_inglese, didascalia) -> None che mette in coda l'illustrazione.
        # La imposta chi gestisce le immagini; se è None il tool illustra_scena non viene offerto.
        self.su_scena: Callable[[str, str], None] | None = None
        self.ultima_prova: dict | None = None  # serve a imposta_flag: serve una prova riuscita
        self._funzioni: dict[str, Callable[..., dict]] = {
            "tira_dadi": self.tira_dadi,
            "prova_abilita": self.prova_abilita,
            "leggi_scheda": self.leggi_scheda,
            "modifica_punti_vita": self.modifica_punti_vita,
            "inventario": self.inventario,
            "sposta_in": self.sposta_in,
            "descrivi_mappa": self.descrivi_mappa,
            "scrivi_diario": self.scrivi_diario,
            "avanza_tempo": self.avanza_tempo,
            "consulta_lore": self.consulta_lore,
            "imposta_flag": self.imposta_flag,
            "valuta_finale": self.valuta_finale,
            "illustra_scena": self.illustra_scena,
        }

    def nuovo_turno(self) -> None:
        """Chiamato all'inizio di ogni turno del giocatore: una prova riuscita vale per un solo turno."""
        self.ultima_prova = None

    def esegui(self, nome: str, argomenti: Any) -> dict:
        """Punto d'ingresso unico: qualunque cosa succeda, restituisce un dizionario."""
        funzione = self._funzioni.get(nome)
        if funzione is None:
            return _errore(f"Tool '{nome}' inesistente. Disponibili: {', '.join(self._funzioni)}.")
        if not isinstance(argomenti, dict):
            return _errore("Gli argomenti devono essere un oggetto JSON.")
        try:
            return funzione(**argomenti)
        except rules.ErroreRegole as e:
            return _errore(str(e))
        except TypeError as e:  # argomenti mancanti o in più
            return _errore(f"Argomenti non validi per '{nome}': {e}")
        except Exception as e:  # rete di sicurezza: un bug non deve far crollare la partita
            return _errore(f"Errore interno nel tool '{nome}': {e}")

    # --- Dadi e prove -----------------------------------------------------------
    def tira_dadi(self, formula: str, motivo: str = "") -> dict:
        return {"ok": True, "motivo": motivo, **rules.tira_formula(formula, self.rng)}

    def prova_abilita(self, statistica: str, difficolta: Any, motivo: str = "") -> dict:
        stat = rules.normalizza_statistica(statistica)
        cd = _intero(difficolta, "difficolta")
        if not 1 <= cd <= 30:
            raise rules.ErroreRegole("La difficoltà deve essere tra 1 e 30.")
        valore = self.stato.personaggio.statistiche[stat]
        esito = rules.prova(valore, cd, self.rng)
        self.ultima_prova = {"statistica": stat, "cd": cd, "successo": esito["successo"]}
        return {"ok": True, "statistica": stat, "motivo": motivo, **esito}

    # --- Scheda e punti vita ------------------------------------------------------
    def leggi_scheda(self) -> dict:
        p = self.stato.personaggio
        return {
            "ok": True,
            "nome": p.nome,
            "classe": p.classe,
            "statistiche": {k: {"valore": v, "modificatore": rules.modificatore(v)} for k, v in p.statistiche.items()},
            "pf": p.pf,
            "pf_max": p.pf_max,
            "inventario": list(p.inventario),
        }

    def modifica_punti_vita(self, delta: Any, motivo: str = "") -> dict:
        d = _intero(delta, "delta")
        if d == 0:
            raise rules.ErroreRegole("delta non può essere 0.")
        p = self.stato.personaggio
        prima = p.pf
        p.pf = max(0, min(p.pf_max, p.pf + d))  # mai sotto 0 né sopra il massimo
        return {
            "ok": True,
            "motivo": motivo,
            "pf_prima": prima,
            "pf_dopo": p.pf,
            "pf_max": p.pf_max,
            "personaggio_caduto": p.pf == 0,
        }

    # --- Inventario -------------------------------------------------------------
    def inventario(self, azione: str, oggetto: str | None = None) -> dict:
        inv = self.stato.personaggio.inventario
        if azione == "elenca":
            return {"ok": True, "inventario": list(inv)}
        if azione not in ("aggiungi", "rimuovi"):
            raise rules.ErroreRegole("azione deve essere 'aggiungi', 'rimuovi' o 'elenca'.")
        nome = _testo(oggetto, "oggetto", 60)
        if azione == "aggiungi":
            if len(inv) >= MAX_OGGETTI:
                raise rules.ErroreRegole(f"Inventario pieno (massimo {MAX_OGGETTI} oggetti).")
            inv.append(nome)
            return {"ok": True, "aggiunto": nome, "inventario": list(inv)}
        # rimuovi: confronto senza distinzione tra maiuscole e minuscole
        for i, o in enumerate(inv):
            if o.lower() == nome.lower():
                inv.pop(i)
                return {"ok": True, "rimosso": o, "inventario": list(inv)}
        raise rules.ErroreRegole(f"Il personaggio non possiede '{nome}'. Inventario attuale: {inv}.")

    # --- Mappa e tempo ---------------------------------------------------------
    def sposta_in(self, luogo: str) -> dict:
        nome = _testo(luogo, "luogo", 60)
        s = self.stato
        if self.mondo is None:  # modalità libera, senza lore
            gia_noto = next((l for l in s.luoghi_visitati if l.lower() == nome.lower()), None)
            if gia_noto:
                nome = gia_noto
            else:
                s.luoghi_visitati.append(nome)
            s.luogo_corrente = nome
            return {"ok": True, "luogo_corrente": nome, "luogo_nuovo": gia_noto is None}

        m = self.mondo
        # 1) una zona del luogo in cui si trova? (nessun tempo perso)
        zone = m.cerca_zone(s.luogo_id, nome)
        if len(zone) == 1:
            return self._entra_in_zona(zone[0])
        trovati = m.cerca_luoghi(nome)
        if len(trovati) != 1:
            altrove = m.zona_altrove(s.luogo_id, nome)
            if altrove:
                l, z = altrove
                raise rules.ErroreRegole(f"{z['nome']} si trova a {l['nome']}, non qui. Prima serve arrivare a {l['nome']}.")
            qui = ", ".join(z["nome"] for z in m.zone(s.luogo_id))
            elenco = ", ".join(l["nome"] for l in m.luoghi.values())
            raise rules.ErroreRegole(f"'{nome}' non è valido (o è ambiguo). Zone di {s.luogo_corrente}: {qui}. Luoghi della valle: {elenco}.")
        dest = trovati[0]
        if dest["id"] == s.luogo_id:
            return {"ok": True, "luogo_corrente": dest["nome"], "nota": "Il personaggio è già in questo luogo: per muoversi dentro, indica una zona.", "ore_viaggio": 0}
        ore = m.raggiungibili(s.luogo_id).get(dest["id"])
        if ore is None:
            vicini = ", ".join(f"{m.nome_luogo(k)} ({v} ore)" for k, v in m.raggiungibili(s.luogo_id).items())
            raise rules.ErroreRegole(f"Da {s.luogo_corrente} non si arriva direttamente a {dest['nome']}. Da qui si raggiunge: {vicini}.")
        nuovo = dest["nome"] not in s.luoghi_visitati
        if nuovo:
            s.luoghi_visitati.append(dest["nome"])
        s.luogo_id, s.luogo_corrente = dest["id"], dest["nome"]
        s.zona_id = m.ingresso(dest["id"])["id"]  # si arriva sempre nella zona d'ingresso (sempre aperta)
        esito = {"ok": True, "luogo_corrente": dest["nome"], "luogo_nuovo": nuovo, "ore_viaggio": ore}
        esito.update(self._fai_passare_ore(ore))
        esito.update(self._situazione_zona())
        return esito

    def _entra_in_zona(self, zona: dict) -> dict:
        s = self.stato
        if zona["id"] == s.zona_id:
            return {"ok": True, "luogo_corrente": s.luogo_corrente, "nota": f"Il personaggio è già in: {zona['nome']}.", **self._situazione_zona()}
        aperta, motivo = self.mondo.apertura(zona, s)
        if not aperta:
            suggerimento = " Il personaggio può aspettare con avanza_tempo." if zona.get("orari") else ""
            raise rules.ErroreRegole(motivo + suggerimento)
        s.zona_id = zona["id"]
        return {"ok": True, "luogo_corrente": s.luogo_corrente, "ore_viaggio": 0, **self._situazione_zona()}

    def _situazione_zona(self) -> dict:
        """Dove si trova il personaggio e chi c'è ora: il master non deve inventare altri presenti."""
        s, m = self.stato, self.mondo
        z = m.zona(s.luogo_id, s.zona_id) or m.ingresso(s.luogo_id)
        return {
            "zona": z["nome"],
            "descrizione_zona": z["descrizione"].strip(),
            "png_presenti_ora": [f"{p['nome']} ({p['ruolo']})" for p in m.png_presenti(s.luogo_id, z["id"], s.ora)],
        }

    def descrivi_mappa(self) -> dict:
        s = self.stato
        out = {"ok": True, "luogo_corrente": s.luogo_corrente, "luoghi_visitati": list(s.luoghi_visitati)}
        if self.mondo:
            out["da_qui_si_raggiunge"] = {self.mondo.nome_luogo(k): f"{v} ore" for k, v in self.mondo.raggiungibili(s.luogo_id).items()}
            out["giorno"], out["ora"] = s.giorno, f"{s.ora:02d}:00"
            out.update(self._situazione_zona())
            out["zone_del_luogo"] = {
                z["nome"]: ("aperta" if self.mondo.apertura(z, s)[0] else "chiusa") + f" ({self.mondo.orari_testo(z)})" for z in self.mondo.zone(s.luogo_id)
            }
        return out

    def avanza_tempo(self, ore: Any, motivo: str = "") -> dict:
        n = _intero(ore, "ore")
        if not 1 <= n <= 24:
            raise rules.ErroreRegole("ore deve essere tra 1 e 24.")
        return {"ok": True, "motivo": motivo, **self._fai_passare_ore(n)}

    def _fai_passare_ore(self, ore: int) -> dict:
        """Avanza l'orologio e fa scattare gli eventi del mondo. È il cuore del 'mondo che vive da solo'."""
        s = self.stato
        prima = s.ore_totali
        s.ore_totali = prima + ore
        info: dict[str, Any] = {}
        if self.mondo:
            if s.ore_totali >= self.mondo.ore_finali:  # il tempo non va oltre il momento finale: è ora del finale
                s.ore_totali = max(prima, self.mondo.ore_finali)
                info["momento_finale_raggiunto"] = True
                info["nota_per_il_master"] = f"È arrivato il momento finale ({self.mondo.momento_finale}): il tempo si ferma qui. Narra la scena e chiama valuta_finale."
            eventi = self._fai_scattare_eventi()
            if eventi:
                info["eventi_mondo"] = eventi
            z = self.mondo.zona(s.luogo_id, s.zona_id)
            if z and not self.mondo.apertura(z, s)[0]:  # nel frattempo la zona ha chiuso: si esce
                ingresso = self.mondo.ingresso(s.luogo_id)
                s.zona_id = ingresso["id"]
                info["zona_chiusa"] = f"{z['nome']} ha chiuso: il personaggio viene accompagnato fuori, in {ingresso['nome']}."
        info["ore_trascorse"] = s.ore_totali - prima
        info["giorno"], info["ora"] = s.giorno, f"{s.ora:02d}:00"
        return info

    def _fai_scattare_eventi(self) -> list[dict]:
        s = self.stato
        out = []
        for e in self.mondo.eventi_da_scattare(s):
            s.eventi_scattati.append(e["giorno"])
            testo = self.mondo.testo_evento(e, s.flag)
            presente = e["luogo"] in (s.luogo_id, "tutta la valle")
            s.diario.append(f"[giorno {e['giorno']}] EVENTO DEL MONDO - {e['titolo']}: {testo}")
            out.append(
                {
                    "giorno": e["giorno"],
                    "titolo": e["titolo"],
                    "luogo": e["luogo"],
                    "il_giocatore_e_presente": presente,
                    "cosa_accade": testo,
                    "retroscena_riservato_al_master": e["in_segreto"],
                    "nota_per_il_master": (
                        "Raccontalo nella scena."
                        if presente
                        else "Il giocatore è lontano: faglielo sapere solo come voce o notizia che arriva, mai come fatto vissuto."
                    ),
                }
            )
        return out

    # --- Lore, progressi e finale -------------------------------------------------
    def consulta_lore(self, argomento: str) -> dict:
        if self.mondo is None:
            raise rules.ErroreRegole("Nessuna lore caricata.")
        arg = _testo(argomento, "argomento", 80)
        risultati = self.mondo.consulta(arg)
        if not risultati:
            raise rules.ErroreRegole(f"Nessun risultato per '{arg}'. Argomenti disponibili: {', '.join(self.mondo.argomenti())}.")
        return {"ok": True, "risultati": risultati}

    def imposta_flag(self, flag: str, motivo: str = "") -> dict:
        if self.mondo is None:
            raise rules.ErroreRegole("Nessuna avventura caricata.")
        s = self.stato
        regola = self.mondo.prove_flag.get(flag)
        if regola is None:
            raise rules.ErroreRegole(f"Flag '{flag}' sconosciuto. Validi: {', '.join(self.mondo.prove_flag)}.")
        if s.flag.get(flag):
            return {"ok": True, "flag": flag, "nota": "Già attivo."}
        # 1) luogo giusto
        if regola.get("luogo") and s.luogo_id != regola["luogo"]:
            raise rules.ErroreRegole(f"Per '{flag}' il personaggio deve trovarsi a {self.mondo.nome_luogo(regola['luogo'])}, non qui.")
        if regola.get("zona") and s.zona_id != regola["zona"]:
            z = self.mondo.zona(regola["luogo"], regola["zona"]) if regola.get("luogo") else None
            raise rules.ErroreRegole(f"Per '{flag}' il personaggio deve trovarsi in: {z['nome'] if z else regola['zona']}.")
        # 2) requisiti
        for req in regola.get("richiede_flag", []):
            if not s.flag.get(req):
                raise rules.ErroreRegole(f"Per '{flag}' serve prima '{req}'.")
        oggetto = regola.get("richiede_oggetto")
        indice = next((i for i, o in enumerate(s.personaggio.inventario) if oggetto and oggetto.lower() in o.lower()), None)
        if oggetto and indice is None:
            raise rules.ErroreRegole(f"Per '{flag}' il personaggio deve avere nell'inventario: {oggetto}.")
        # 3) prova riuscita con la statistica e la CD giuste
        p = self.ultima_prova
        if not p or not p["successo"]:
            raise rules.ErroreRegole(
                f"Per '{flag}' serve prima una prova_abilita RIUSCITA ({regola['statistica']}, CD {regola['cd']}): {regola['cosa']}."
            )
        if p["statistica"] != regola["statistica"] or p["cd"] < regola["cd"]:
            raise rules.ErroreRegole(
                f"La prova fatta ({p['statistica']}, CD {p['cd']}) non basta: per '{flag}' serve {regola['statistica']} con CD almeno {regola['cd']}."
            )
        # tutto ok
        if regola.get("consuma_oggetto") and indice is not None:
            s.personaggio.inventario.pop(indice)
        s.flag[flag] = True
        self.ultima_prova = None  # una prova riuscita vale per un solo flag
        s.diario.append(f"[giorno {s.giorno}] PROGRESSO: {regola['cosa']} ({motivo or flag})")
        return {"ok": True, "flag": flag, "cosa": regola["cosa"]}

    def valuta_finale(self) -> dict:
        if self.mondo is None:
            raise rules.ErroreRegole("Nessuna avventura caricata.")
        s = self.stato
        if s.ore_totali < self.mondo.ore_finali:
            m = self.mondo
            raise rules.ErroreRegole(f"{m.momento_finale} non è ancora iniziato/a: ora è il giorno {s.giorno} alle {s.ora:02d}:00 (arriva il giorno {m.giorni} alle {m.ora_finale:02d}:00).")
        f = self.mondo.valuta_finale(s.flag)
        s.finale = f["id"]
        s.diario.append(f"[giorno {s.giorno}] FINALE: {f['nome']}")
        return {"ok": True, "finale": f["nome"], "esito": f["esito"].strip(), "nota_per_il_master": "Narra questo finale (puoi arricchirlo ma non cambiarne l'esito) e concludi la storia."}

    # --- Diario -----------------------------------------------------------------
    def scrivi_diario(self, evento: str) -> dict:
        testo = _testo(evento, "evento", 300)
        self.stato.diario.append(f"[giorno {self.stato.giorno}] {testo}")
        return {"ok": True, "voci_nel_diario": len(self.stato.diario)}

    # --- Illustrazioni ----------------------------------------------------------
    def schemi(self) -> list[dict]:
        """I tool da offrire al modello: illustra_scena solo se le immagini sono attive."""
        return [t for t in TOOL_SCHEMAS if t["name"] != "illustra_scena" or self.su_scena is not None]

    def illustra_scena(self, descrizione: str, didascalia: str = "") -> dict:
        if self.su_scena is None:
            raise rules.ErroreRegole("La generazione di immagini è disattivata.")
        desc = _testo(descrizione, "descrizione", 400)
        s = self.stato
        if s.turno - s.ultimo_turno_scena < 3:
            raise rules.ErroreRegole("Hai appena illustrato una scena: aspetta qualche turno prima di illustrarne un'altra.")
        s.ultimo_turno_scena = s.turno
        self.su_scena(desc, (didascalia or "").strip()[:80])
        return {"ok": True, "nota": "Illustrazione in preparazione (circa 30 secondi). Non aspettarla: continua a narrare."}
