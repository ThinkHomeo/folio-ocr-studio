# Historical OCR prototype notes

These notes describe earlier TPB research and its historical measurements.
They are not a benchmark of the current Folio application. Refer to the
[current README](../README.md) and [application guide](../APPLICATION.md)
for installation and the supported workflow. Referenced scans, training
datasets and generated outputs are not included in the repository.

**Local application:** Folio turns general scans into editable page text with
**Text OCR** (default), and supports printed-entry review with **Format-aware OCR**
(current template: TPB 1891). Page numbers support **0 से … तक**; Chapter is not
required. See [APPLICATION.md](../APPLICATION.md)
for the persistent upload, review and export interface. Start it with
`.\.venv\Scripts\python.exe -m formatocr` and open `http://127.0.0.1:8788`.
The [architecture review](../ARCHITECTURE_REVIEW.md) records historical gaps and saved
evaluation evidence. The research notes below describe the earlier prototype.

A self-contained system that OCRs pages of Boenninghausen / Allen's
**Therapeutic Pocket Book** (1891 New American Edition) **and recovers the
five-level remedy rank that the book encodes in the typeface** of each remedy
abbreviation.

```
CAPITALS                  -> rank 5   SUL., NUX V., CALC. C.
Antique (heavy / bold)    -> rank 4   Sep., Bell., Nux v.
Italic                    -> rank 3   Spig., Stram.
Roman (ordinary thin)     -> rank 2   Spo., Squ., Acon.
Roman in parentheses      -> rank 1   (Abrot.)
```

The point is **not** to transcribe the words only — any OCR does that — but to
read the *grade* off the printing, so the rubric→remedy→grade fact can be
rebuilt directly from the page instead of trusting a third-party dataset.

## How it works

A page is processed in four stages (`tpbocr/`):

1. **segment.py** — Tesseract (`image_to_data`) gives word boxes + text.
   Words are reassembled into *remedy tokens* (comma-separated), the bold
   rubric heading glued to the first remedy by an em-dash is split off, and
   running heads are dropped.
2. **features.py** — for each token crop, scale-normalised to a fixed
   x-height, we measure the three signals that separate the faces:
   - **slant** — gradient orientation of the near-vertical stems (italic leans
     ~+10°..+15°, roman/antique ~0°);
   - **weight** — mean horizontal black-run length in the x-height body band,
     divided by x-height (antique is heavier than roman); a distance-transform
     stroke width is kept as a secondary cue;
   - **caps / parentheses** — read from the token text.
3. **classify.py** — decision order: parentheses→1, all-caps→5, slant→3,
   weight→4, else roman→2. The antique/roman split threshold is **re-fitted per
   page** (1-D Otsu on that page's upright-token weights) so it tracks scan
   exposure. Every token gets a **confidence**; near-boundary tokens are
   flagged.
4. **pipeline.py** — orchestrates and writes the three outputs below.

Everything geometric is expressed scale-free, so the same thresholds work on a
96-dpi preview and a 600-dpi scan — but see *Accuracy* on why resolution still
matters.

## Usage

Requires Python 3, `opencv-python`, `numpy`, `pytesseract`, and a Tesseract
binary (eng). Install dependencies using the current README; this historical
prototype assumed an environment where the dependencies were already present.

```bash
python -m tpbocr.pipeline PAGE.(jpg|png|webp|tif) [--scale N] [--tag NAME] \
       [--out DIR] [--tess PATH-to-tesseract.exe]
```

`--scale 2` upsamples a low-resolution preview before OCR (recommended for the
webp previews). Outputs land in `out/`:

| file | contents |
|---|---|
| `<tag>.json` | structured `{page, weight_threshold, rubrics:[{rubric, remedies:[{text, rank, rank_name, confidence, bbox, features}]}]}` |
| `<tag>_proof.txt` | human-readable, remedies grouped by rank per rubric (`?` = low confidence) |
| `<tag>_overlay.png` | the page with every token boxed in its rank colour (thick box = confident) — the fastest way to eyeball correctness |

Run on a whole book by looping the command over every page image.

## Accuracy (measured on pp. 17–18, "Mind")

- **Rank 1 (parens), 3 (italic), 5 (CAPITALS): ~98%+** — these signals are
  unambiguous. The hand-verified `Mind/Avarice` line
  (`ARS.`₅ `Calc. c.`₂ `Lyc.`₄ `Nat. c.`₃ `PULS.`₅ `Sep.`₃) comes out **6/6**.
- **Rank 2 (roman) vs 4 (antique): ~85–90%** — this is the hard pair: both are
  upright and the antique face is only slightly heavier, so short abbreviations
  near the weight boundary (e.g. *Dros.*, *Agn.*) are sometimes confused. These
  are exactly the tokens the pipeline marks low-confidence.

**Resolution matters.** Grading is reliable on the full-resolution scan
(~3000 px tall, `input/p018_hires.jpg`). On the downsized webp previews the
weight signal is weaker — italic/caps still work, antique/roman degrades.
For production, feed ≥300-dpi page images.

## Limitations & how to push further

- The OCR *text* of the abbreviations is raw Tesseract and still has errors
  (`Mere.`→Merc., `¢`→c.); the system's job here is the **rank**, not perfect
  spelling. Pair with the remedy-abbreviation authority to normalise names.
- Antique/roman is the ceiling of hand-crafted features. The clean next step is
  a small **trained classifier** (HOG descriptor + linear SVM) over the token
  crops: the segmenter already yields labelled crops, caps/parens are free
  labels, and a few fully hand-labelled pages would lift rank-2/4 accuracy.
  `calibrate.py` / `septest.py` are the dev tools used to tune the thresholds.

## Files

```
tpbocr/
  segment.py    page -> ordered remedy tokens (Tesseract word boxes)
  features.py   per-token slant / weight / caps measurement
  classify.py   features -> rank 1..5 + confidence (per-page adaptive)
  pipeline.py   CLI: image -> json + proof + overlay
  calibrate.py  dump per-token features for a page (dev)
  septest.py    feature-separability check vs hand labels (dev)
input/          the two sample pages (webp preview + hi-res scan)
out/            generated json / proof / overlay
```
