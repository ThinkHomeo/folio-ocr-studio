# -*- coding: utf-8 -*-
"""Retrain the PRIMARY MLP face classifier on ALL vision-gold pages (the big
lever — the shipped model was trained on only 8 pages).

For every book page that has vision gold (ocr_out/..._bp0NN.md): render the jp2
leaf exactly as the inference path does (1300-wide WEBP-equivalent, then x2
CUBIC), segment it, and for each remedy token that matches a gold token whose
face is Roman(2)/Italic(3)/Antique(4), extract its lower-case glyph bitmaps and
build the SAME feature rows the pipeline uses at inference (model_mlp.token_vecs:
glyph bitmap + per-page-normalised weight & slant). Train an MLPFace on the lot
and save out/mlp_model.pkl.

Usage: python -m tpbocr.train_full [START] [END] [--out PATH] [--cache]
       defaults 17..495 ; book page NN = jp2 leaf NN+6.
"""
import sys, os, io, re, json, zipfile, time, pickle, argparse
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import numpy as np, cv2
from PIL import Image
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tpbocr import segment, features, classify, glyphs, model_mlp as MLP

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BK = os.path.join(ROOT, "..", "tpb-data", "public-domain", "books",
                  "07_Allen_1891_New_American_Edition_Boston")
ZIP = os.path.join(BK, "therapeuticpocke0000timo_jp2.zip")
OCR_OUT = os.path.join(BK, "ocr_out")
TESS = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
OUTDIR = os.path.join(ROOT, "out")
LOG = os.path.join(OUTDIR, "train_full.log")


def log(msg):
    os.makedirs(OUTDIR, exist_ok=True)
    line = "%s  %s" % (time.strftime("%H:%M:%S"), msg)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")
    print(line, flush=True)


def nkey(s):
    return re.sub(r"[^a-z0-9]", "", s.lower())


def tok_rank(t):
    t = t.strip()
    if t.startswith("(") and t.endswith(")"):
        return 1
    if t.startswith("**") and t.endswith("**"):
        return 4
    if t.startswith("*") and t.endswith("*"):
        return 3
    core = re.sub(r"[*()]", "", t); L = [c for c in core if c.isalpha()]
    return 5 if (L and all(c.isupper() for c in L)) else 2


def parse_ref(path):
    rub = []
    for line in open(path, encoding="utf-8"):
        m = re.match(r"\*\*(.+?)\.\*\*\s*[—-]+\s*(.*)", line.strip())
        if not m:
            continue
        items = [(re.sub(r"[*()]|\*\*", "", t).strip(), tok_rank(t))
                 for t in m.group(2).split(",") if t.strip()]
        rub.append((m.group(1).strip(), items))
    return rub


def match_rubric(rn, keys):
    rk = nkey(rn)
    for mk in keys:
        if nkey(mk)[:6] == rk[:6] or nkey(mk).startswith(rk[:5]) or rk.startswith(nkey(mk)[:5]):
            return mk
    return None


def render_gray(z, leaf, width=1300):
    """Render a jp2 leaf to the SAME grey array the inference path sees:
    PIL->L, 1300-wide LANCZOS (what batch_book writes as WEBP), then x2 CUBIC
    (what pipeline.load_gray does with --scale 2)."""
    name = "therapeuticpocke0000timo_jp2/therapeuticpocke0000timo_%04d.jp2" % leaf
    im = Image.open(io.BytesIO(z.read(name))).convert("L")
    h = int(im.height * width / im.width)
    im = im.resize((width, h), Image.LANCZOS)
    g = np.asarray(im)
    return cv2.resize(g, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("start", nargs="?", type=int, default=17)
    ap.add_argument("end", nargs="?", type=int, default=495)
    ap.add_argument("--out", default=os.path.join(OUTDIR, "mlp_model.pkl"))
    ap.add_argument("--cache", default=None,
                    help="pickle of per-page rows to reuse (skips re-OCR)")
    a = ap.parse_args()

    samples = []            # (feature_row, face)
    pages_used = glyph_n = tok_n = 0
    face_count = {2: 0, 3: 0, 4: 0}
    t0 = time.time()

    cache = None
    if a.cache and os.path.exists(a.cache):
        log("loading cache %s" % a.cache)
        cache = pickle.load(open(a.cache, "rb"))

    percol = {}             # page -> rows, for optional caching
    z = None if cache else zipfile.ZipFile(ZIP)
    leaves = set()
    if z is not None:
        leaves = {int(re.search(r"_(\d+)\.jp2$", n).group(1))
                  for n in z.namelist() if n.endswith(".jp2")}

    log("START retrain pages %d..%d" % (a.start, a.end))
    for bp in range(a.start, a.end + 1):
        vg = os.path.join(OCR_OUT, "therapeuticpocke0000timo_bp0%d.md" % bp)
        if not os.path.exists(vg):
            continue
        try:
            if cache is not None:
                rows = cache.get(bp, [])
            else:
                leaf = bp + 6
                if leaf not in leaves:
                    continue
                gray = render_gray(z, leaf)
                toks = segment.tokens(gray, tess_cmd=TESS)
                chars = glyphs.page_chars(gray, tess_cmd=TESS)
                myrub = {}; cur = None
                for t in toks:
                    if t["is_heading"]:
                        cur = t["rubric"]; myrub[cur] = []
                    elif cur is not None:
                        myrub[cur].append(t)
                ref = parse_ref(vg)
                rows = []
                for rn, ritems in ref:
                    mk = match_rubric(rn, list(myrub.keys()))
                    if not mk:
                        continue
                    gmap = {}
                    for txt, rk in ritems:
                        gmap.setdefault(nkey(txt), rk)
                    for t in myrub[mk]:
                        k = nkey(t["text"])
                        if k not in gmap:
                            continue
                        gold = gmap[k]
                        if gold not in (2, 3, 4):
                            continue
                        box = segment.first_line_box(t["parts"])
                        gl = glyphs.token_glyphs(gray, box, chars)
                        pad = 3
                        crop = gray[max(0, box[1] - pad):box[3] + pad,
                                    max(0, box[0] - pad):box[2] + pad]
                        feat = features.measure(crop)
                        rows.append(dict(gold=gold, glyphs=gl, feat=feat))
                if a.cache is not None:
                    percol[bp] = rows
            # build samples with per-page norm
            up = [r["feat"]["weight"] for r in rows
                  if r["feat"] and r["feat"]["slant"] < classify.SLANT_T]
            norm = MLP.page_norm(up)
            for r in rows:
                vecs = MLP.token_vecs(r["glyphs"], r["feat"], norm)
                for v in vecs:
                    samples.append((v, r["gold"]))
                    glyph_n += 1
                if vecs:
                    tok_n += 1; face_count[r["gold"]] = face_count.get(r["gold"], 0) + 1
            if rows:
                pages_used += 1
            if pages_used % 25 == 0 and rows:
                log("..bp%d  pages=%d toks=%d glyphs=%d  (%.0fs)"
                    % (bp, pages_used, tok_n, glyph_n, time.time() - t0))
        except Exception as e:
            log("bp%d FAIL %r" % (bp, e))

    log("built samples: pages=%d tokens=%d glyphs=%d faces=%s  (%.0fs)"
        % (pages_used, tok_n, glyph_n, face_count, time.time() - t0))
    if a.cache is not None and percol:
        pickle.dump(percol, open(a.cache, "wb"))
        log("cached rows -> %s" % a.cache)
    if not samples:
        log("NO SAMPLES — aborting"); return
    log("training MLP on %d glyph samples ..." % len(samples))
    model = MLP.train(samples)
    model.save(a.out)
    log("DONE saved %s  (total %.0fs)" % (a.out, time.time() - t0))
    print("SAVED %s" % a.out)


if __name__ == "__main__":
    main()
