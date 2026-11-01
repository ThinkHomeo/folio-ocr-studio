# -*- coding: utf-8 -*-
"""Dump per-token features for a page, for threshold calibration."""
import sys, io, os
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import numpy as np, cv2
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tpbocr import segment, features

TESS = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

def load_gray(path, scale=2):
    im = cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_GRAYSCALE)
    if scale != 1:
        im = cv2.resize(im, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    return im

def run(path):
    g = load_gray(path)
    toks = segment.tokens(g, tess_cmd=TESS)
    print("rubric\tis_head\ttext\tcaps\tparen\tweight\tslant\tdensity\tstroke\txh\tconf")
    for t in toks:
        if t["is_heading"]:
            print("== %s ==" % t["rubric"])
            continue
        mp = segment.main_part(t["parts"])
        x0,y0,x1,y1 = mp["x"], mp["y"], mp["x"]+mp["w"], mp["y"]+mp["h"]
        pad=2
        crop = g[max(0,y0-pad):y1+pad, max(0,x0-pad):x1+pad]
        f = features.measure(crop)
        if not f: continue
        txt = t["text"]
        letters=[c for c in txt if c.isalpha()]
        caps = bool(letters) and all(c.isupper() for c in letters)
        paren = txt.strip().startswith("(")
        conf = min(p["conf"] for p in t["parts"])
        print("%s\t%d\t%s\t%d\t%d\t%.3f\t%.1f\t%.3f\t%.2f\t%.1f\t%d" % (
            t["rubric"], 0, txt[:22], caps, paren, f["weight"], f["slant"],
            f["density"], f["stroke"], f["xheight"], conf))

if __name__ == "__main__":
    run(sys.argv[1])
