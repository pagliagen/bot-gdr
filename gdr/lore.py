"""La lore (mondo, luoghi, PNG, avventura) caricata dai file YAML in lore/.

Qui non c'è nessuna chiamata al modello: solo dati e regole di consultazione.
Il codice usa questi dati per:
- dare al master un riassunto breve nel system prompt (non può contenere tutta la lore);
- rispondere al tool consulta_lore;
- far scattare gli eventi della cronologia al giorno giusto;
- stabilire il finale in base ai flag.
"""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from typing import Any

import yaml

from .models import StatoPartita

GIORNI_AVVENTURA = 7
ORA_FESTA = 20  # la Festa dell'Apertura comincia alle 20 del giorno 7
FESTA_ORE = (GIORNI_AVVENTURA - 1) * 24 + ORA_FESTA  # ore totali a cui scatta la Festa

_PAROLE_VUOTE = {"di", "del", "dei", "della", "delle", "il", "lo", "la", "le", "i", "gli", "al", "alla", "a", "da", "in", "e"}


def _parole(testo: str) -> set[str]:
    """'Il Mulino Alto!' -> {'mulino', 'alto'}: minuscole, senza accenti né punteggiatura."""
    t = unicodedata.normalize("NFD", str(testo).lower())
    t = "".join(c if c.isalnum() else " " for c in t if unicodedata.category(c) != "Mn")
    return {p for p in t.split() if p not in _PAROLE_VUOTE}


def _leggi(percorso: Path) -> Any:
    return yaml.safe_load(percorso.read_text(encoding="utf-8"))


class Mondo:
    def __init__(self, cartella: Path):
        cartella = Path(cartella)
        self.mondo = _leggi(cartella / "mondo.yaml")
        luoghi = _leggi(cartella / "luoghi.yaml")
        png = _leggi(cartella / "png.yaml")
        self.avventura = _leggi(cartella / "avventura.yaml")

        self.iniziale: str = luoghi["iniziale"]
        self.luoghi: dict[str, dict] = {l["id"]: l for l in luoghi["luoghi"]}
        self.png: dict[str, dict] = {p["id"]: p for p in png["png"]}
        self.eventi: list[dict] = sorted(self.avventura["cronologia"], key=lambda e: e["giorno"])
        self.finali: list[dict] = self.avventura["finali"]
        self.prove_flag: dict[str, dict] = {p["flag"]: p for p in self.avventura["prove_suggerite"] if "flag" in p}
        self.flag_iniziali: dict[str, bool] = dict(self.avventura["flag_iniziali"])

    # --- Luoghi -------------------------------------------------------------------
    def cerca_luoghi(self, testo: str) -> list[dict]:
        """Luoghi il cui id o nome contiene tutte le parole cercate."""
        q = _parole(testo)
        if not q:
            return []
        return [l for l in self.luoghi.values() if q <= (_parole(l["nome"]) | _parole(l["id"]))]

    def nome_luogo(self, luogo_id: str) -> str:
        return self.luoghi[luogo_id]["nome"] if luogo_id in self.luoghi else luogo_id

    def png_presenti(self, luogo_id: str) -> list[dict]:
        return [p for p in self.png.values() if p["luogo"] == luogo_id]

    def raggiungibili(self, luogo_id: str) -> dict[str, int]:
        return dict(self.luoghi.get(luogo_id, {}).get("collegamenti", {}))

    def stato_iniziale(self, stato: StatoPartita) -> None:
        """Imposta luogo, flag e orologio di una partita nuova."""
        l = self.luoghi[self.iniziale]
        stato.luogo_id, stato.luogo_corrente, stato.luoghi_visitati = l["id"], l["nome"], [l["nome"]]
        stato.flag = dict(self.flag_iniziali)
        stato.ore_totali = 8
        # Gli eventi del giorno 1 sono già in corso quando il giocatore arriva:
        # li registriamo subito nel diario, così il master li conosce dall'inizio.
        for e in self.eventi_da_scattare(stato):
            stato.eventi_scattati.append(e["giorno"])
            stato.diario.append(f"[giorno {e['giorno']}] EVENTO DEL MONDO - {e['titolo']}: {self.testo_evento(e, stato.flag)}")

    def aspetti_in_scena(self, descrizione: str) -> list[str]:
        """Per ogni PNG nominato nella descrizione, il suo aspetto (in inglese) da dare al generatore di immagini.

        Il modello di immagini non conosce i nostri PNG: senza questo disegnerebbe Tobia a caso.
        """
        titoli = {"capitano", "sorella", "fratello", "nonna", "madre", "detto", "detta", "della", "dello"}
        trovati = []
        for p in self.png.values():
            parole = [w for w in re.findall(r"\w+", p["nome"]) if len(w) >= 4 and w.lower() not in titoli]
            if p.get("aspetto_en") and any(re.search(rf"\b{re.escape(w)}\b", descrizione, re.IGNORECASE) for w in parole):
                trovati.append(f"{p['nome']} looks like: {p['aspetto_en']}")
        return trovati

    # --- Eventi e finali ----------------------------------------------------------
    def eventi_da_scattare(self, stato: StatoPartita) -> list[dict]:
        return [e for e in self.eventi if e["giorno"] <= stato.giorno and e["giorno"] not in stato.eventi_scattati]

    @staticmethod
    def testo_evento(evento: dict, flag: dict[str, bool]) -> str:
        """Il testo dell'evento, oppure della prima variante i cui flag sono attivi."""
        for v in evento.get("varianti", []):
            if flag.get(v["se_flag"]):
                return v["cosa_accade"].strip()
        return evento["cosa_accade"].strip()

    def valuta_finale(self, flag: dict[str, bool]) -> dict:
        """Il primo finale (in ordine) le cui condizioni sono soddisfatte."""
        for f in self.finali:
            if all(flag.get(k) for k in f["richiede"]) and not any(flag.get(k) for k in f["esclude"]):
                return f
        return self.finali[-1]

    # --- Consultazione (tool consulta_lore) ----------------------------------------
    def consulta(self, argomento: str) -> list[dict]:
        """Schede della lore che corrispondono all'argomento. I segreti sono marcati come riservati."""
        q = _parole(argomento)
        if not q:
            return []
        m = self.mondo
        # parole chiave generali
        if q & {"storia", "ere", "passato"}:
            return [{"tipo": "storia", "ere": [{"era": e["era"], "quando": e["quando"], "testo": e["testo"].strip()} for e in m["storia"]]}]
        if q & {"religione", "religioni", "culti", "culto", "dei"}:
            return [{"tipo": "religione", **{k: (v.strip() if isinstance(v, str) else v) for k, v in r.items()}} for r in m["religioni"]]
        if q & {"fazioni", "fazione"}:
            return [self._fazione(f) for f in m["fazioni"]]
        if q & {"luoghi", "mappa"}:
            return [{"tipo": "luoghi", "luoghi": [f"{l['nome']} ({l['tipo']})" for l in self.luoghi.values()]}]
        if q & {"png", "personaggi"}:
            return [{"tipo": "png", "png": [f"{p['nome']}, {p['ruolo']}" for p in self.png.values()]}]

        trovati: list[dict] = []
        for l in self.luoghi.values():
            if q <= (_parole(l["nome"]) | _parole(l["id"])):
                trovati.append(self._luogo(l))
        for p in self.png.values():
            if q <= (_parole(p["nome"]) | _parole(p["id"]) | _parole(p["ruolo"])):
                trovati.append(self._png(p))
        for f in m["fazioni"]:
            if q <= (_parole(f["nome"]) | _parole(f["id"])):
                trovati.append(self._fazione(f))
        for r in m["religioni"]:
            if q <= (_parole(r["nome"]) | _parole(r["id"])):
                trovati.append({"tipo": "religione", **r})
        return trovati[:4]

    def argomenti(self) -> list[str]:
        return (
            [l["nome"] for l in self.luoghi.values()]
            + [p["nome"] for p in self.png.values()]
            + [f["nome"] for f in self.mondo["fazioni"]]
            + ["storia", "religioni", "fazioni", "luoghi", "png"]
        )

    def _luogo(self, l: dict) -> dict:
        return {
            "tipo": "luogo",
            "nome": l["nome"],
            "descrizione": l["descrizione"].strip(),
            "dettagli": l["dettagli"].strip(),
            "luoghi_interni": l["luoghi_interni"],
            "collegamenti": {self.nome_luogo(k): f"{v} ore" for k, v in l["collegamenti"].items()},
            "png_presenti": [p["nome"] for p in self.png_presenti(l["id"])],
        }

    def _png(self, p: dict) -> dict:
        return {
            "tipo": "png",
            "nome": p["nome"],
            "ruolo": p["ruolo"],
            "luogo": self.nome_luogo(p["luogo"]),
            "aspetto": p["aspetto"],
            "carattere": p["carattere"],
            "scopo": p["scopo"],
            "frase_tipica": p["voce"],
            "segreto_riservato_al_master": p["segreto"],
        }

    @staticmethod
    def _fazione(f: dict) -> dict:
        return {"tipo": "fazione", "nome": f["nome"], "scopo": f["scopo"], "segreto_riservato_al_master": f["segreto"]}

    # --- Riassunto per il system prompt ---------------------------------------------
    def riassunto_prompt(self, stato: StatoPartita) -> str:
        m, av = self.mondo, self.avventura
        righe = [
            f"## IL MONDO: {m['nome']}",
            m["sintesi"].strip(),
            f"Tono: {m['tono'].strip()}",
            "",
            f"Premessa dell'avventura: {av['premessa'].strip()}",
            f"VERITÀ NASCOSTA (solo per te: non rivelarla finché il giocatore non la scopre con indagini e prove): {av['verita_nascosta'].strip()}",
            "Regole del mondo: " + " ".join(m["regole_mondo"]),
            "",
            "Luoghi: " + "; ".join(f"{l['nome']} ({l['tipo']})" for l in self.luoghi.values()),
            "PNG: " + "; ".join(f"{p['nome']} ({p['ruolo']})" for p in self.png.values()),
            "Per dettagli su un luogo, un PNG o una fazione usa consulta_lore: non inventare.",
            "",
            "## TEMPO",
            f"È il giorno {stato.giorno} di {GIORNI_AVVENTURA}, ore {stato.ora:02d}:00. La Festa dell'Apertura è la sera del giorno {GIORNI_AVVENTURA} (ore {ORA_FESTA}:00).",
        ]
        luogo = self.luoghi.get(stato.luogo_id)
        if luogo:
            righe += [
                "",
                f"## DOVE SI TROVA IL GIOCATORE: {luogo['nome']}",
                luogo["descrizione"].strip(),
                luogo["dettagli"].strip(),
                "Da qui si raggiunge (viaggio a piedi): "
                + ", ".join(f"{self.nome_luogo(k)} ({v} ore)" for k, v in luogo["collegamenti"].items()),
            ]
            qui = self.png_presenti(luogo["id"])
            if qui:
                righe.append("PNG che si trovano qui: " + "; ".join(f"{p['nome']} ({p['ruolo']}; {p['aspetto']}; {p['carattere']})" for p in qui))
        attivi = [k for k, v in stato.flag.items() if v]
        righe += ["", "## PROGRESSI DEL GIOCATORE (flag attivi)", ", ".join(attivi) or "nessuno"]
        return "\n".join(righe)


def carica_mondo(cartella: Path) -> Mondo:
    return Mondo(cartella)
