# Prompt per le immagini statiche

Sono in inglese perché i generatori di immagini lo capiscono meglio. Ogni prompt
va completato con lo **stile fisso** qui sotto (incollalo in coda a ognuno).
Salva i file con i nomi indicati (formato **webp**) nella cartella `assets/` del progetto: la mappa in `assets/mappa.webp`, i ritratti in `assets/png/`, i luoghi in `assets/luoghi/`.

Già fatte: la mappa e i ritratti di Madre Corrente, Ormando, Odilia, Sorella Brina e Tobia.

## Stile fisso (da aggiungere in fondo a tutti i prompt)

```
hand-painted storybook fantasy illustration, warm watercolor and ink, soft natural light, gentle humor, muted palette of river green, ochre and slate blue, detailed but not photorealistic, no text, no watermark, no modern objects
```

Suggerimento: usa lo stesso modello e lo stesso stile per tutte, e rigenera finché
i volti dei PNG ti piacciono. Non servono tutte subito: parti dalle priorità.

---

## PRIORITÀ 1: la mappa

**File:** `assets/mappa.webp` — formato 16:9 (fatta: 1024×559)

Importante: chiedi **senza scritte**. I generatori sbagliano le parole. I nomi e i
segnalini li disegna il programma sopra la mappa, usando le coordinate in
`luoghi.yaml`.

```
fantasy map of a small river valley seen from above, aged parchment style with hand-drawn ink and watercolor. A green river flows from the top-left mountains, passes a large calm lake near the top-left (a dam in a narrow gorge), then winds down through the center of the valley under a stone bridge at a small village in the middle, and continues to the bottom-right where it widens into marshy flats with a fishing village on stilts. A small castle on a crescent-shaped hill in the right side. A dark mossy willow forest in the bottom-left. A tiny cave shrine at the far left near the source. A watermill complex between the lake and the central village. Roads connect the places. Mountains along the top and left edges, rolling hills elsewhere. Empty parchment margins. No text, no labels, no compass, no legend, no scale bar, no watermark
```

Quando l'hai generata, dammela: guardo dove sono i luoghi e correggo le coordinate.

---

## PRIORITÀ 2: ritratti dei PNG principali

**Formato:** 3:4 verticale (es. 768×1024), mezzo busto, sfondo neutro color pergamena.
Cartella: `assets/png/`.

| File | Prompt (poi aggiungi lo stile fisso) |
|---|---|
| `madre_corrente.webp` | `portrait of a river spirit, a stern matronly figure made of translucent flowing water, hair of swirling currents, eyes like river pebbles, faint stamp-shaped seal glowing on her chest, dignified and slightly annoyed expression, neutral parchment background` |
| `ormando_ruotanera.webp` | `portrait of a tall thin charismatic engineer in his fifties, round spectacles, ink-stained fingers, leather apron over a fine waistcoat, optimistic confident smile, holding a rolled blueprint, neutral parchment background` |
| `odilia_mezzaluna.webp` | `portrait of a stern fifty-year-old baroness, straight posture, green velvet dress, tired sarcastic eyes, a small teacup in her hand, neutral parchment background` |
| `sorella_brina.webp` | `portrait of a tiny elderly nun-like priestess, blue shawl, very thick glasses, holding a stack of stamped forms, stubborn kind face, neutral parchment background` |
| `tobia_bonvino.webp` | `portrait of a round sixty-year-old innkeeper with a huge mustache, stained apron, big warm grin, holding a wooden tankard, neutral parchment background` |

## PRIORITÀ 3: altri PNG

| File | Prompt (poi aggiungi lo stile fisso) |
|---|---|
| `fiammetta.webp` | `portrait of a young female apprentice engineer, around twenty, messy braid, oil-stained hands, worried clever eyes, leather goggles on her forehead, neutral parchment background` |
| `ruggero_duro.webp` | `portrait of a sturdy forty-year-old guard captain, dented armor, tired kind face, droopy moustache, helmet under his arm, neutral parchment background` |
| `gedeone_anguilla.webp` | `portrait of a lean fervent preacher wearing a tunic woven from fishing nets, wet beard, wild feverish eyes, holding a small silver eel, neutral parchment background` |
| `nonna_zelinda.webp` | `portrait of an old witch-like hermit woman, wide straw hat, knotty walking stick, patched skirt with a thousand patches, sly smile, giant pumpkin beside her, neutral parchment background` |
| `pina_la_rana.webp` | `portrait of a stocky thirty-year-old female river smuggler, wide-brimmed hat, roguish grin, rope over her shoulder, neutral parchment background` |

---

## PRIORITÀ 4: illustrazioni dei luoghi

**Formato:** 16:9 (es. 1344×768). Cartella: `assets/luoghi/`.
Sono le immagini che il programma mostra quando il giocatore arriva in un luogo.
Se mancano, la versione dinamica con l'AI le genera a runtime.

| File | Prompt (poi aggiungi lo stile fisso) |
|---|---|
| `pontevecchio.webp` | `wide scene of a small stone village around a mossy arched bridge, a crooked toll booth, a fountain with a one-armed statue of a woman, a warm tavern with a fish-shaped sign, a shallow low river beneath the bridge, morning light` |
| `mulino_alto.webp` | `a large watermill complex with a big slowly turning wooden wheel, brass and wood gears everywhere, tidy offices, guards in leather aprons, slightly eerie order, golden afternoon light` |
| `la_diga.webp` | `a massive stone and timber dam wedged in a narrow rocky gorge, a calm too-still lake behind it, a keystone glowing faint green, narrow walkways, tense atmosphere, twilight` |
| `santuario_sorgente.webp` | `a small cave shrine among ferns and wet rocks where a spring flows from a crack, a simple altar with an empty pedestal, candles, shelves of stamped parchments, soft green light` |
| `rocca_mezzaluna.webp` | `a small castle on a crescent-shaped hill, small towers with oversized banners, sleepy soldiers in a courtyard, a view over a quiet valley, late afternoon` |
| `borgo_basso.webp` | `a fishing village on stilts along a dried-up river bend, boats stranded on mud, nets hanging everywhere, a pier ending on dry land, a small shrine with an eel sign, stunned fish in puddles, grey morning` |
| `bosco_salici.webp` | `a damp ancient willow forest, whispering trees with faces in the bark, daytime fireflies, huge mushrooms like stools, a crooked hut with a garden of giant pumpkins, misty` |
