# -*- coding: utf-8 -*-
"""Montage micro-adjudication: crop the tokens that need a vision decision
(the Roman/Antique rank-2/4 calls — the only subtle class) into ONE numbered
grid image, so a vision model can judge ~100 of them in a single cheap image
instead of re-reading whole pages. Also emits an index JSON to merge answers.

Usage:  python -m tpbocr.montage p020 [--out out] [--cols 10]
Outputs: out/montage_<tag>.png  +  out/montage_<tag>.json
"""
import sys, os, json, argparse
import numpy as np, cv2
from PIL import Image, ImageDraw, ImageFont

RANK_COLOR = {4: (216,120,0), 2: (30,90,200), 3: (26,122,60), 5:(198,40,40), 1:(120,60,170)}

def load_scaled(tag, scale=2):
    p = os.path.join("input", tag + ".webp")
    im = cv2.imdecode(np.fromfile(p, np.uint8), cv2.IMREAD_GRAYSCALE)
    return cv2.resize(im, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)

def targets(doc, kinds):
    out = []
    for ru in doc["rubrics"]:
        for rem in ru["remedies"]:
            take = (("ra" in kinds and rem["rank"] in (2,4)) or
                    ("flag" in kinds and rem.get("flag")))
            if take:
                out.append((ru["rubric"], rem))
    return out

def build(tag, out="out", cols=10, scale=2, kinds=("ra",)):
    doc = json.load(open(os.path.join(out, tag + "_webp.json"), encoding="utf-8"))
    gray = load_scaled(tag, scale)
    items = targets(doc, kinds)
    cellw, cellh, pad, lab = 230, 92, 6, 20
    rows = (len(items) + cols - 1) // cols
    W, H = cols*cellw, rows*cellh + 36
    canvas = Image.new("RGB", (W, H), (250,250,248))
    d = ImageDraw.Draw(canvas)
    d.text((8, 8), "%s — %d Roman/Antique tokens to adjudicate  (M = machine guess; mark R=Roman(2) / A=Antique(4))"
           % (tag, len(items)), fill=(0,0,0))
    index = []
    for i, (rubric, rem) in enumerate(items):
        x0,y0,x1,y1 = rem["bbox"]
        crop = gray[max(0,y0-3):y1+3, max(0,x0-3):x1+3]
        if crop.size == 0:
            crop = np.full((20,40), 255, np.uint8)
        ch, cw = crop.shape
        sc = min((cellw-2*pad)/max(1,cw), (cellh-lab-2*pad)/max(1,ch), 3.0)
        rim = Image.fromarray(cv2.resize(crop, (max(1,int(cw*sc)), max(1,int(ch*sc))),
                                         interpolation=cv2.INTER_CUBIC)).convert("RGB")
        cx = (i % cols)*cellw; cy = (i//cols)*cellh + 30
        col = RANK_COLOR.get(rem["rank"], (0,0,0))
        d.rectangle([cx+2, cy+lab, cx+cellw-2, cy+cellh-2], outline=col, width=2)
        canvas.paste(rim, (cx+pad, cy+lab+pad))
        gl = "A" if rem["rank"]==4 else "R"
        d.text((cx+4, cy+4), "#%d  M:%s" % (i, gl), fill=col)
        index.append(dict(id=i, page=tag, rubric=rubric, text=rem["text"],
                          bbox=rem["bbox"], machine_rank=rem["rank"],
                          flag=rem.get("flag", False)))
    os.makedirs(out, exist_ok=True)
    png = os.path.join(out, "montage_%s.png" % tag)
    canvas.save(png)
    json.dump({"tag": tag, "count": len(items), "items": index},
              open(os.path.join(out, "montage_%s.json" % tag), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    return png, len(items)

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("tag"); ap.add_argument("--out", default="out")
    ap.add_argument("--cols", type=int, default=10)
    ap.add_argument("--kinds", default="ra")
    a = ap.parse_args()
    png, n = build(a.tag, a.out, a.cols, kinds=tuple(a.kinds.split(",")))
    print("wrote %s  (%d tokens to adjudicate)" % (png, n))
