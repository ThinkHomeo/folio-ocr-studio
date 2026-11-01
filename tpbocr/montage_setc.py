# -*- coding: utf-8 -*-
"""Set-C certification montage generator.
Renders context-strip montage grids for the remaining Set-C genuine ties (1,133 tokens)
and the auto-resolved audit sample (150 tokens), annotating each cell with the three
independent signals (v1 = first vision, v2 = second revision vision, eng = engine majority)
so the user or reviewer can verify or certify instantly.

Usage: python -m tpbocr.montage_setc [ties|audit|both]
Outputs under out/verify/: montage_setc_ties_pNNN.png + .json, montage_setc_audit.png + .json
"""
import sys, os, io, csv, json, zipfile, argparse, collections
import numpy as np, cv2
from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BK = os.path.join(ROOT, "..", "tpb-data", "public-domain", "books",
                  "07_Allen_1891_New_American_Edition_Boston")
ZIP = os.path.join(BK, "therapeuticpocke0000timo_jp2.zip")
VERIFY = os.path.join(ROOT, "out", "verify")
GNAME = {5: "C", 4: "A", 3: "I", 2: "R", 1: "P"}


def render_leaf(z, leaf, width=1300, scale=2):
    name = "therapeuticpocke0000timo_jp2/therapeuticpocke0000timo_%04d.jp2" % leaf
    im = Image.open(io.BytesIO(z.read(name))).convert("L")
    h = int(im.height * width / im.width)
    im = im.resize((width, h), Image.LANCZOS)
    g = np.asarray(im)
    return cv2.resize(g, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)


def emaj_str(r):
    v = [int(x) for x in (r.get("scalar"), r.get("mlp"), r.get("shape"))
         if x not in ("", "None", None)]
    if not v:
        return "?"
    top = collections.Counter(v).most_common(1)[0][0]
    return GNAME.get(top, str(top))


def build_montages_for_rows(rows, tag_prefix, cols=5):
    """Group rows by page and build montage grids."""
    if not rows:
        print("No rows for", tag_prefix)
        return
    by_page = collections.defaultdict(list)
    for r in rows:
        try:
            bbox = json.loads(r["bbox"]) if r.get("bbox") else None
        except Exception:
            bbox = None
        if bbox:
            by_page[int(r["page"])].append(r | {"bbox": bbox})

    z = zipfile.ZipFile(ZIP)
    cellw, cellh, pad, lab = 480, 116, 6, 24
    CTX = 230

    for bp, page_rows in sorted(by_page.items()):
        gray = render_leaf(z, bp + 6)
        gh, gw = gray.shape
        nrows = (len(page_rows) + cols - 1) // cols
        W, H = cols * cellw, nrows * cellh + 46
        canvas = Image.new("RGB", (W, H), (250, 250, 248))
        d = ImageDraw.Draw(canvas)
        d.text((8, 10), "SET-C CERTIFICATION (%s) — book p.%d (%d tokens)  |  Format per cell: #id Remedy  |  Hints: v1=1st-vision v2=2nd-vision eng=engine  |  Reply id->letter (C/A/I/R/P)"
               % (tag_prefix, bp, len(page_rows)), fill=(0, 0, 0))
        index = []
        for i, r in enumerate(page_rows):
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
            dd = ImageDraw.Draw(rim)
            dd.rectangle([int((x0 - cx0) * sc), int((y0 - cy0) * sc),
                          int((x1 - cx0) * sc), int((y1 - cy0) * sc)], outline=(220, 30, 30), width=2)
            cxp = (i % cols) * cellw; cyp = (i // cols) * cellh + 38
            canvas.paste(rim, (cxp + pad, cyp + lab + pad))

            v1_g = GNAME.get(int(r["grade"]), str(r["grade"]))
            import re
            m = re.search(r"v1=(\d),v2=(\d)", r.get("reasons", ""))
            v2_g = GNAME.get(int(m.group(2)), m.group(2)) if m else "?"
            eng_g = emaj_str(r)
            hint = "v1=%s v2=%s eng=%s" % (v1_g, v2_g, eng_g)

            d.text((cxp + 4, cyp + 4), "#%d  %s" % (i, r["remedy"][:16]), fill=(20, 20, 20))
            d.text((cxp + 4, cyp + 22), "hint: [%s]" % hint, fill=(160, 40, 40))

            index.append(dict(id=i, page=bp, rubric=r["rubric"], remedy=r["remedy"],
                              v1=v1_g, v2=v2_g, eng=eng_g, bbox=r["bbox"]))

        png = os.path.join(VERIFY, "montage_setc_%s_p%03d.png" % (tag_prefix, bp))
        canvas.save(png)
        json.dump({"tag": tag_prefix, "page": bp, "count": len(page_rows), "items": index},
                  open(os.path.join(VERIFY, "montage_setc_%s_p%03d.json" % (tag_prefix, bp)),
                       "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print("Wrote %s (%d tokens)" % (os.path.basename(png), len(page_rows)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", nargs="?", default="ties", choices=["ties", "audit", "both"])
    a = ap.parse_args()

    if a.mode in ("ties", "both"):
        ties = []
        p = os.path.join(VERIFY, "setC_residual.csv")
        if os.path.exists(p):
            with open(p, encoding="utf-8-sig") as f:
                ties = list(csv.DictReader(f))
        print("Building montages for Set C ties (%d tokens)..." % len(ties))
        build_montages_for_rows(ties, "ties")

    if a.mode in ("audit", "both"):
        audit = []
        p = os.path.join(VERIFY, "setC_audit_sample.csv")
        if os.path.exists(p):
            with open(p, encoding="utf-8-sig") as f:
                audit = list(csv.DictReader(f))
        print("Building montages for auto-resolved audit sample (%d tokens)..." % len(audit))
        build_montages_for_rows(audit, "audit")


if __name__ == "__main__":
    main()
