"""Genera con Ollama le immagini statiche che mancano: le zone dei luoghi e i ritratti dei PNG.

Salta i file già presenti, quindi si può rilanciare dopo uno stop. Per rifarne una,
cancella il file e rilancia. Uso:  python scripts/genera_immagini.py [zone|png]
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

RADICE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RADICE))

from gdr.config import carica_config  # noqa: E402
from gdr.immagini import OllamaImmagini, salva_webp  # noqa: E402
from gdr.lore import carica_mondo  # noqa: E402


def main() -> None:
    cfg = carica_config()
    mondo = carica_mondo(cfg.percorso_lore)
    stile = mondo.mondo["stile_immagini"].strip()
    cosa = sys.argv[1] if len(sys.argv) > 1 else "tutto"
    zone_gen = OllamaImmagini(cfg.immagini_model, cfg.ollama_host, 1024, 576, cfg.immagini_steps)
    ritratti_gen = OllamaImmagini(cfg.immagini_model, cfg.ollama_host, 768, 1024, cfg.immagini_steps)

    lavori: list[tuple[Path, str, OllamaImmagini]] = []
    if cosa in ("tutto", "png"):
        for p in mondo.png.values():
            lavori.append((RADICE / p["immagine"], f"half-length portrait of {p['aspetto_en']}, neutral parchment-colored background, {stile}", ritratti_gen))
    if cosa in ("tutto", "zone"):
        for lid in mondo.luoghi:
            for z in mondo.zone(lid):
                lavori.append((RADICE / "assets" / "zone" / f"{lid}_{z['id']}.webp", f"{z['prompt_immagine'].strip()}, {stile}", zone_gen))

    da_fare = [l for l in lavori if not l[0].exists()]
    print(f"{len(da_fare)} immagini da generare ({len(lavori) - len(da_fare)} già presenti).")
    for i, (percorso, prompt, gen) in enumerate(da_fare, 1):
        t0 = time.time()
        try:
            salva_webp(gen.genera(prompt), percorso)
            print(f"[{i}/{len(da_fare)}] {percorso.relative_to(RADICE)} ({time.time() - t0:.0f}s)", flush=True)
        except RuntimeError as e:
            print(f"[{i}/{len(da_fare)}] ERRORE {percorso.name}: {e}", flush=True)


if __name__ == "__main__":
    main()
