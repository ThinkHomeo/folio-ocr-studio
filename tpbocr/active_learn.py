# -*- coding: utf-8 -*-
"""Active learning: fold vision-adjudicated tokens back into MLP training so the
model learns THIS book's fonts and flags fewer tokens on later pages.

Training labels = (a) gold pages (bp*.md) + (b) any page JSON tokens marked
`adjudicated` (vision verdict). Retrains out/mlp_model.pkl.

Usage: python -m tpbocr.active_learn p025 p026 ...   (extra adjudicated pages)
"""
import sys, os, re, json, glob
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import numpy as np, cv2
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tpbocr import segment, features, classify, glyphs, model_mlp as M
from tpbocr import train_shape as TS

TESS = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

def gold_samples():
    s = []
    for pg, rows in TS.DATA.items():
        norm = M.page_norm([r["feat"]["weight"] for r in rows
                            if r["feat"] and r["feat"]["slant"] < classify.SLANT_T])
        for r in rows:
            for v in M.token_vecs(r["glyphs"], r["feat"], norm):
                s.append((v, r["gold"]))
    return s

def adjudicated_samples(tags):
    """extract (vec, vision_rank) for tokens marked adjudicated in page JSONs."""
    out = []
    for tag in tags:
        jp = os.path.join("out", tag + "_webp.json")
        if not os.path.exists(jp):
            continue
        doc = json.load(open(jp, encoding="utf-8"))
        adj = [(ru["rubric"], rem) for ru in doc["rubrics"] for rem in ru["remedies"]
               if rem.get("adjudicated") and rem["rank"] in (2, 3, 4)]
        if not adj:
            continue
        gray = cv2.resize(cv2.imdecode(np.fromfile("input/%s.webp" % tag, np.uint8),
                          cv2.IMREAD_GRAYSCALE), None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
        toks = segment.tokens(gray, tess_cmd=TESS)
        chars = glyphs.page_chars(gray, tess_cmd=TESS)
        up = [features.measure(gray[max(0,segment.first_line_box(t['parts'])[1]-3):
              segment.first_line_box(t['parts'])[3]+3,
              max(0,segment.first_line_box(t['parts'])[0]-3):
              segment.first_line_box(t['parts'])[2]+3]) for t in toks if not t["is_heading"]]
        norm = M.page_norm([f["weight"] for f in up if f and f["slant"] < classify.SLANT_T])
        # map adjudicated bbox -> glyphs
        for t in toks:
            if t["is_heading"]:
                continue
            box = segment.first_line_box(t["parts"])
            bb = list(segment.union_box(t["parts"]))
            for rub, rem in adj:
                if rem["bbox"] == [int(b) for b in bb]:
                    pad=3; crop=gray[max(0,box[1]-pad):box[3]+pad, max(0,box[0]-pad):box[2]+pad]
                    f=features.measure(crop); gl=glyphs.token_glyphs(gray, box, chars)
                    for v in M.token_vecs(gl, f, norm):
                        out.append((v, rem["rank"]))
                    break
    return out

if __name__ == "__main__":
    extra = sys.argv[1:]
    samples = gold_samples()
    adj = adjudicated_samples(extra) if extra else []
    print("gold glyph-samples: %d   adjudicated glyph-samples: %d" % (len(samples), len(adj)))
    M.train(samples + adj).save("out/mlp_model.pkl")
    print("retrained out/mlp_model.pkl on %d samples" % (len(samples) + len(adj)))
