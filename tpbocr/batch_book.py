# -*- coding: utf-8 -*-
"""Whole-book MACHINE-ONLY OCR pass (no vision, no agents) for vision-vs-machine
comparison. For each jp2 leaf in the range: render -> pipeline (MLP+shape+scalar
rank) -> dictionary-correct remedy text -> write a rank-marked .md (gold format)
and the raw .json. Robust per-page; logs progress to out/book/_progress.log.

Usage: python -m tpbocr.batch_book [START_BOOKPAGE] [END_BOOKPAGE]
       (defaults 17..495; book page NN = jp2 leaf NN+6)
"""
import sys, os, io, re, json, zipfile, time, traceback
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import numpy as np, cv2
from PIL import Image
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tpbocr import pipeline, classify, dict_correct as DC

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BK = os.path.join(ROOT, "..", "tpb-data", "public-domain", "books",
                  "07_Allen_1891_New_American_Edition_Boston")
ZIP = os.path.join(BK, "therapeuticpocke0000timo_jp2.zip")
OCR_OUT = os.path.join(BK, "ocr_out")
OUTDIR = os.path.join(ROOT, "out", "book")
TESS = pipeline.DEFAULT_TESS
MLP = os.path.join(ROOT, "out", "mlp_model.pkl")
SHAPE = os.path.join(ROOT, "out", "shape_model.pkl")

MARK = {5: lambda s: s, 4: lambda s: "**%s**" % s, 3: lambda s: "*%s*" % s,
        2: lambda s: s, 1: lambda s: "(%s)" % s}

def log(msg):
    os.makedirs(OUTDIR, exist_ok=True)
    with open(os.path.join(OUTDIR, "_progress.log"), "a", encoding="utf-8") as f:
        f.write("%s  %s\n" % (time.strftime("%H:%M:%S"), msg))

def render_leaf(z, leaf, dst, width=1300):
    name = "therapeuticpocke0000timo_jp2/therapeuticpocke0000timo_%04d.jp2" % leaf
    im = Image.open(io.BytesIO(z.read(name))).convert("L")
    g = np.asarray(im)
    ink = float((g < 128).mean())
    h = int(im.height * width / im.width)
    im.resize((width, h), Image.LANCZOS).save(dst, "WEBP", quality=90)
    return ink

def to_md(doc, bookpage, vocab, vkeys):
    lines = ["<!-- RANK: CAPS=5 | **bold**=Antique4 | *italic*=Italic3 | plain=Roman2 | (parens)=1 -->",
             "<!-- MACHINE-ONLY OCR (TPB 1891 book p.%d) — tpbocr pipeline, no vision -->" % bookpage, ""]
    for ru in doc["rubrics"]:
        if not ru["rubric"]:
            continue
        toks = []
        for rem in ru["remedies"]:
            txt = rem["text"]
            cor, k, dist, unc = DC.correct(txt, vocab, vkeys)
            use = cor if not unc else txt
            mark = MARK.get(rem["rank"], lambda s: s)(use)
            if rem.get("flag") or unc:
                mark += "?"               # machine low-confidence marker
            toks.append(mark)
        lines.append("**%s.**—%s" % (ru["rubric"], ", ".join(toks)))
        lines.append("")
    return "\n".join(lines)

def main():
    start = int(sys.argv[1]) if len(sys.argv) > 1 else 17
    end = int(sys.argv[2]) if len(sys.argv) > 2 else 495
    os.makedirs(OUTDIR, exist_ok=True)
    vocab = DC.default_vocab(OCR_OUT); vkeys = list(vocab.keys())
    z = zipfile.ZipFile(ZIP)
    leaves = {int(re.search(r"_(\d+)\.jp2$", n).group(1)) for n in z.namelist() if n.endswith(".jp2")}
    log("START book pages %d..%d  (vocab=%d)" % (start, end, len(vocab)))
    done = skipped = failed = 0
    for bp in range(start, end + 1):
        leaf = bp + 6
        if leaf not in leaves:
            continue
        if os.path.exists(os.path.join(OUTDIR, "machine_p%03d.md" % bp)):
            done += 1; continue            # resume: already processed
        try:
            tmp = os.path.join(OUTDIR, "_p%03d.webp" % bp)
            ink = render_leaf(z, leaf, tmp)
            if ink < 0.012:                 # near-blank leaf
                skipped += 1; log("p%d skip (blank ink=%.3f)" % (bp, ink));
                os.remove(tmp); continue
            doc, _ = pipeline.process(tmp, scale=2, tess=TESS,
                                      shape_model_path=SHAPE, mlp_model_path=MLP)
            n = sum(len(r["remedies"]) for r in doc["rubrics"])
            with open(os.path.join(OUTDIR, "p%03d.json" % bp), "w", encoding="utf-8") as f:
                json.dump(doc, f, ensure_ascii=False)
            with open(os.path.join(OUTDIR, "machine_p%03d.md" % bp), "w", encoding="utf-8") as f:
                f.write(to_md(doc, bp, vocab, vkeys))
            os.remove(tmp)
            done += 1
            if n:
                log("p%d OK  rubrics=%d tokens=%d" % (bp, len(doc["rubrics"]), n))
        except Exception as e:
            failed += 1
            log("p%d FAIL %s" % (bp, repr(e)))
    log("DONE  done=%d skipped=%d failed=%d" % (done, skipped, failed))
    print("DONE done=%d skipped=%d failed=%d -> %s" % (done, skipped, failed, OUTDIR))

if __name__ == "__main__":
    main()
