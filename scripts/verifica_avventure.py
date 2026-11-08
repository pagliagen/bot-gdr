"""Controlla la coerenza dei dati di tutte le avventure (o di una sola).

Uso:  python scripts/verifica_avventure.py [avventura]
Segnala: riferimenti a luoghi/zone/flag che non esistono, PNG in zone chiuse alle loro ore,
collegamenti non reciproci, finali irraggiungibili, immagini mancanti.
Esce con codice 1 se trova errori (le immagini mancanti sono solo un avviso).
"""

from __future__ import annotations

import sys
from pathlib import Path

RADICE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RADICE))

from gdr.avventure import Catalogo  # noqa: E402
from gdr.config import carica_config  # noqa: E402
from gdr.models import Personaggio, StatoPartita  # noqa: E402


def verifica(m) -> tuple[list[str], list[str]]:
    err: list[str] = []
    avv: list[str] = []
    flag = set(m.flag_iniziali)
    luoghi = set(m.luoghi)

    # luoghi, collegamenti, zone
    if m.iniziale not in luoghi:
        err.append(f"luogo iniziale '{m.iniziale}' inesistente")
    for l in m.luoghi.values():
        if not all(0 <= c <= 1 for c in l["pos"]):
            err.append(f"{l['id']}: pos fuori da 0-1")
        for k, ore in l["collegamenti"].items():
            if k not in luoghi:
                err.append(f"{l['id']}: collegamento a '{k}' inesistente")
            elif l["id"] not in m.luoghi[k]["collegamenti"]:
                err.append(f"{l['id']} -> {k}: collegamento non reciproco")
        zs = m.zone(l["id"])
        if not zs:
            err.append(f"{l['id']}: nessuna zona")
            continue
        if sum(1 for z in zs if z.get("ingresso")) != 1:
            err.append(f"{l['id']}: serve esattamente una zona d'ingresso")
        ids = [z["id"] for z in zs]
        if len(set(ids)) != len(ids):
            err.append(f"{l['id']}: id di zona duplicati")
        for z in zs:
            if z.get("ingresso") and (z.get("orari") or z.get("richiede_flag")):
                err.append(f"{l['id']}.{z['id']}: l'ingresso deve essere sempre aperto")
            for f in z.get("richiede_flag", []):
                if f not in flag:
                    err.append(f"{l['id']}.{z['id']}: flag '{f}' inesistente")
            if not z.get("prompt_immagine"):
                err.append(f"{l['id']}.{z['id']}: manca prompt_immagine")
    # PNG
    aperto = StatoPartita(Personaggio("x", "G", {}, 1, 1), "")
    aperto.flag = {f: True for f in flag}
    for p in m.png.values():
        if p["luogo"] not in luoghi:
            err.append(f"PNG {p['id']}: luogo '{p['luogo']}' inesistente")
            continue
        if not p.get("aspetto_en"):
            err.append(f"PNG {p['id']}: manca aspetto_en")
        zone_ids = {z["id"] for z in m.zone(p["luogo"])}
        for h in range(24):
            z = m.zona_png(p, h)
            if z is None:
                continue
            if z not in zone_ids:
                err.append(f"PNG {p['id']}: zona '{z}' inesistente in {p['luogo']}")
                break
            aperto.ore_totali = h
            if not m.apertura(m.zona(p["luogo"], z), aperto)[0]:
                err.append(f"PNG {p['id']}: alle {h:02d}:00 sta in '{z}', che è chiusa")
        if all(m.zona_png(p, h) is None for h in range(24)):
            err.append(f"PNG {p['id']}: non è mai reperibile")

    # trama
    for e in m.eventi:
        if e["luogo"] not in luoghi and not e["luogo"].startswith("tutta"):
            err.append(f"evento giorno {e['giorno']}: luogo '{e['luogo']}' inesistente")
        if not 1 <= e["giorno"] <= m.giorni:
            err.append(f"evento '{e['titolo']}': giorno fuori durata")
        for v in e.get("varianti", []):
            if v["se_flag"] not in flag:
                err.append(f"evento '{e['titolo']}': flag '{v['se_flag']}' inesistente")
    for f in m.finali:
        for k in f["richiede"] + f["esclude"]:
            if k not in flag:
                err.append(f"finale {f['id']}: flag '{k}' inesistente")
    if m.finali[-1]["richiede"]:
        err.append("l'ultimo finale deve avere richiede: [] (è quello di ripiego)")
    usati = {k for f in m.finali for k in f["richiede"] + f["esclude"]}
    for fl, r in m.prove_flag.items():
        if fl not in flag:
            err.append(f"prova: flag '{fl}' non in flag_iniziali")
        if r.get("luogo") not in luoghi:
            err.append(f"prova {fl}: luogo '{r.get('luogo')}' inesistente")
        elif r.get("zona") and not m.zona(r["luogo"], r["zona"]):
            err.append(f"prova {fl}: zona '{r['zona']}' inesistente")
        for k in r.get("richiede_flag", []):
            if k not in flag:
                err.append(f"prova {fl}: richiede_flag '{k}' inesistente")
        if r["statistica"] not in ("forza", "agilita", "intelletto"):
            err.append(f"prova {fl}: statistica '{r['statistica']}' non valida")
        if not 1 <= r["cd"] <= 30:
            err.append(f"prova {fl}: cd fuori da 1-30")
    for fl in flag:
        if fl not in m.prove_flag:
            err.append(f"flag '{fl}': nessuna prova_suggerita lo imposta (irraggiungibile)")
    # ogni finale (tranne il ripiego) deve poter essere ottenuto: tutti i suoi flag sono impostabili
    for f in m.finali[:-1]:
        if any(k not in m.prove_flag for k in f["richiede"]):
            err.append(f"finale {f['id']}: richiede flag senza prova")
    # tempo
    if not 0 <= m.ora_inizio < 24 or not 0 <= m.ora_finale < 24:
        err.append("ora_inizio/ora_finale fuori da 0-23")

    # immagini mancanti (avviso)
    for l in m.luoghi.values():
        if not m.url_asset(l.get("immagine")):
            avv.append(f"immagine mancante: {l.get('immagine')}")
    for p in m.png.values():
        if not m.url_asset(p.get("immagine")):
            avv.append(f"immagine mancante: {p.get('immagine')}")
    for lid in m.luoghi:
        for z in m.zone(lid):
            if not (m.cartella / "assets" / "zone" / f"{lid}_{z['id']}.webp").exists():
                avv.append(f"immagine mancante: assets/zone/{lid}_{z['id']}.webp")
    if not m.url_asset("assets/mappa.webp"):
        avv.append("immagine mancante: assets/mappa.webp")
    return err, avv


def main() -> None:
    cfg = carica_config()
    cat = Catalogo(cfg.percorso_avventure)
    ids = sys.argv[1:] or cat.ids()
    errori_tot = 0
    for i in ids:
        m = cat.ottieni(i)
        if m is None:
            sys.exit(f"Avventura '{i}' inesistente. Disponibili: {', '.join(cat.ids())}")
        err, avv = verifica(m)
        print(f"== {m.id} ({m.titolo}): {len(m.luoghi)} luoghi, {sum(len(m.zone(l)) for l in m.luoghi)} zone, {len(m.png)} PNG, {len(m.prove_flag)} flag, {len(m.finali)} finali")
        for e in err:
            print("  ERRORE:", e)
        for a in avv[:6]:
            print("  avviso:", a)
        if len(avv) > 6:
            print(f"  avviso: ... e altre {len(avv) - 6} immagini mancanti")
        errori_tot += len(err)
        if not err:
            print("  dati coerenti")
    sys.exit(1 if errori_tot else 0)


if __name__ == "__main__":
    main()
