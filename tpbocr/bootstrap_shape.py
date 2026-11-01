# -*- coding: utf-8 -*-
"""Strengthen the shape model with MORE pages, semi-supervised.

Full vision transcription per page is costly, but the shape prototypes only
need many clean glyph exemplars per (letter, face). So we mine EXTRA pages
(no gold needed) for HIGH-CONFIDENCE tokens — strong-slant italics and tokens
far from the per-page weight valley where the scalar + shape engines agree —
and add their glyphs as pseudo-labels. We then re-evaluate the shape model on
the 4 gold pages (leave-one-out) to show whether the extra data helps.
"""
import sys, os, re
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import numpy as np, cv2
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tpbocr import segment, features, classify, glyphs, shape_model
from tpbocr import train_shape as TS   # gold-page token cache (DATA)

TESS = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
BOOT_PAGES = ["p022","p023","p024","p025","p026","p027","p028","p029","p030"]

def load_gray(name, scale=2):
    im = cv2.imdecode(np.fromfile("input/%s.webp" % name, np.uint8), cv2.IMREAD_GRAYSCALE)
    return cv2.resize(im, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)

def mine_page(name, smodel):
    """-> list of (letter, pseudo_face, glyph) from confident tokens only."""
    gray = load_gray(name)
    toks = segment.tokens(gray, tess_cmd=TESS)
    chars = glyphs.page_chars(gray, tess_cmd=TESS)
    feats = []
    for t in toks:
        if t["is_heading"]: continue
        box = segment.first_line_box(t["parts"]); pad = 3
        crop = gray[max(0,box[1]-pad):box[3]+pad, max(0,box[0]-pad):box[2]+pad]
        feats.append((t, box, features.measure(crop)))
    up = [f["weight"] for _,_,f in feats if f and f["slant"] < classify.SLANT_T
          and not classify.is_caps(_[0] if False else "")]
    up = [f["weight"] for t,_,f in feats if f and f["slant"] < classify.SLANT_T
          and not classify.is_caps(t["text"]) and not classify.is_paren(t["text"])]
    wt = classify.otsu_split(up) or classify.WEIGHT_T
    out = []
    for t, box, f in feats:
        if not f or classify.is_caps(t["text"]) or classify.is_paren(t["text"]):
            continue
        if f["slant"] >= classify.SLANT_T:
            face, conf = 3, (f["slant"] - classify.SLANT_T) >= 4.0
        else:
            margin = abs(f["weight"] - wt) / wt
            face = 4 if f["weight"] >= wt else 2
            conf = margin >= 0.25
        if not conf:
            continue
        # require shape engine to agree (independent check), if it has an opinion
        gl = glyphs.token_glyphs(gray, box, chars)
        res = smodel.classify(gl) if smodel else None
        if res and res["face"] != face:
            continue
        for ch, g in gl:
            out.append((ch, face, g))
    return out

def gold_samples(exclude=None):
    return [(ch, r["gold"], g) for pg, rows in TS.DATA.items() if pg != exclude
            for r in rows for ch, g in r["glyphs"]]

print("Mining bootstrap pages for high-confidence glyphs...")
base = shape_model.ShapeModel().fit(gold_samples())
boot = []
for name in BOOT_PAGES:
    s = mine_page(name, base)
    boot += s
    print("  %s: +%d confident glyphs" % (name, len(s)))
print("TOTAL bootstrap glyphs:", len(boot))

print("\nLeave-one-gold-page-out shape accuracy  (gold-only  vs  gold+bootstrap):")
tot=okA=okB=0
for test in TS.DATA:
    trainA = gold_samples(exclude=test)
    mA = shape_model.ShapeModel().fit(trainA)
    mB = shape_model.ShapeModel().fit(trainA + boot)
    n=a=b=0
    for r in TS.DATA[test]:
        rA = mA.classify(r["glyphs"]); rB = mB.classify(r["glyphs"])
        n+=1
        a += 1 if (rA and rA["face"]==r["gold"]) else 0
        b += 1 if (rB and rB["face"]==r["gold"]) else 0
    print("  %s n=%3d  gold-only=%.1f%%  +bootstrap=%.1f%%" % (test,n,100*a/n,100*b/n))
    tot+=n; okA+=a; okB+=b
print("  OVERALL  gold-only=%.1f%%  +bootstrap=%.1f%%" % (100*okA/tot,100*okB/tot))

# save the strengthened model (all gold + bootstrap)
final = shape_model.ShapeModel().fit(gold_samples() + boot)
final.save("out/shape_model.pkl")
print("\nsaved strengthened out/shape_model.pkl  (%d prototypes)" % len(final.proto))
