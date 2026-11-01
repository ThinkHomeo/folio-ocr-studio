# -*- coding: utf-8 -*-
"""Set-B re-vision montage: crop every DOUBTFUL token (out/verify/setB_doubtful.csv)
for a page into ONE numbered grid image so an INDEPENDENT vision pass can re-read
its typeface rank — BLIND (the first-vision grade is NOT shown, only the remedy
text + crop), so the second opinion doesn't just parrot the first.

Pairs with revision_merge.py: a vision agent writes {id: rank} to
out/verify/revis_p<NN>.json, then merge promotes agreements to Set A and sends
disagreements to Set C (user certifies).

Usage: python -m tpbocr.montage_setb 17 30     # build montages for a page range
       python -m tpbocr.montage_setb 25         # single page
Outputs per page with >0 doubtful tokens: out/verify/montage_setb_p<NN>[_k].png + .json
"""
import sys, os, io, csv, json, zipfile, argparse, collections
import numpy as np, cv2
from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BK = os.path.join(ROOT, "..", "tpb-data", "public-domain", "books",
                  "07_Allen_1891_New_American_Edition_Boston")
ZIP = os.path.join(BK, "therapeuticpocke0000timo_jp2.zip")
VERIFY = os.path.join(ROOT, "out", "verify")
SETB = os.path.join(VERIFY, "setB_doubtful.csv")
PER_MONTAGE = 80                        # context strips are wider -> fewer per sheet
CTX = 230                               # px of horizontal neighbour context each side


def render_leaf(z, leaf, width=1300, scale=2):
    """leaf -> grayscale array in the SAME space the pNNN.json bboxes live in
    (batch_book renders width=1300 then pipeline upsamples x2)."""
    name = "therapeuticpocke0000timo_jp2/therapeuticpocke0000timo_%04d.jp2" % leaf
    im = Image.open(io.BytesIO(z.read(name))).convert("L")
    h = int(im.height * width / im.width)
    im = im.resize((width, h), Image.LANCZOS)
    g = np.asarray(im)
    return cv2.resize(g, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)


def load_setb_by_page():
    pages = collections.defaultdict(list)
    with open(SETB, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            try:
                bbox = json.loads(r["bbox"]) if r.get("bbox") else None
            except Exception:
                bbox = None
            if not bbox:
                continue                 # no-machine-match tokens have no crop
            pages[int(r["page"])].append(r | {"bbox": bbox})
    return pages


def build_page(bp, rows, gray, cols=5):
    """Lay rows into numbered grid PNGs. Each cell is a horizontal LINE STRIP:
    the target token (red box) flanked by its neighbours, so the second vision
    can judge Antique-vs-Roman WEIGHT by comparison (isolated crops can't).
    Returns list of (png, count)."""
    cellw, cellh, pad, lab = 470, 104, 6, 20
    gh, gw = gray.shape
    out = []
    for part, s in enumerate(range(0, len(rows), PER_MONTAGE)):
        chunk = rows[s:s + PER_MONTAGE]
        nrows = (len(chunk) + cols - 1) // cols
        W, H = cols * cellw, nrows * cellh + 42
        canvas = Image.new("RGB", (W, H), (250, 250, 248))
        d = ImageDraw.Draw(canvas)
        d.text((8, 10), "SET-B RE-VISION  book p.%d  (%d)  — judge the RED-BOXED token's TYPEFACE "
               "vs its neighbours: C/c=CAPS(5) A=Antique-heavier(4) I=italic-slanted(3) "
               "R=roman-normal(2) P=(parens)(1). Reply id->letter." % (bp, len(chunk)), fill=(0, 0, 0))
        index = []
        for i, r in enumerate(chunk):
            gid = s + i
            x0, y0, x1, y1 = [int(v) for v in r["bbox"]]
            cx0, cx1 = max(0, x0 - CTX), min(gw, x1 + CTX)
            cy0, cy1 = max(0, y0 - 5), min(gh, y1 + 5)
            crop = gray[cy0:cy1, cx0:cx1]
            if crop.size == 0:
                crop = np.full((20, 60), 255, np.uint8)
            rim = Image.fromarray(crop).convert("RGB")
            ch, cw = crop.shape
            sc = min((cellw - 2 * pad) / max(1, cw), (cellh - lab - 2 * pad) / max(1, ch), 2.4)
            rim = rim.resize((max(1, int(cw * sc)), max(1, int(ch * sc))), Image.LANCZOS)
            dd = ImageDraw.Draw(rim)                       # outline target within the strip
            dd.rectangle([int((x0 - cx0) * sc), int((y0 - cy0) * sc),
                          int((x1 - cx0) * sc), int((y1 - cy0) * sc)], outline=(220, 30, 30), width=2)
            cxp = (i % cols) * cellw; cyp = (i // cols) * cellh + 36
            canvas.paste(rim, (cxp + pad, cyp + lab + pad))
            d.text((cxp + 4, cyp + 4), "#%d %s" % (gid, r["remedy"][:20]), fill=(60, 60, 60))
            index.append(dict(id=gid, page=bp, rubric=r["rubric"], remedy=r["remedy"],
                              first_grade=int(r["grade"]), bbox=r["bbox"]))
        os.makedirs(VERIFY, exist_ok=True)
        suf = "" if len(rows) <= PER_MONTAGE else "_%d" % part
        png = os.path.join(VERIFY, "montage_setb_p%03d%s.png" % (bp, suf))
        canvas.save(png)
        json.dump({"page": bp, "part": part, "count": len(chunk), "items": index},
                  open(os.path.join(VERIFY, "montage_setb_p%03d%s.json" % (bp, suf)),
                       "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        out.append((png, len(chunk)))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("start", type=int)
    ap.add_argument("end", nargs="?", type=int)
    a = ap.parse_args()
    end = a.end or a.start
    by_page = load_setb_by_page()
    z = zipfile.ZipFile(ZIP)
    total = 0
    for bp in range(a.start, end + 1):
        rows = by_page.get(bp)
        if not rows:
            continue
        gray = render_leaf(z, bp + 6)
        for png, n in build_page(bp, rows, gray):
            total += n
            print("wrote %s  (%d tokens)" % (os.path.basename(png), n))
    print("DONE  %d doubtful tokens montaged across pages %d..%d" % (total, a.start, end))


if __name__ == "__main__":
    main()
