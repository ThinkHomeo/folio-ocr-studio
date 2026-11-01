# -*- coding: utf-8 -*-
"""Separability test: pull features for hand-labelled anchor tokens and show
whether weight/slant separate roman(2) / italic(3) / antique(4)."""
import sys, os
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import numpy as np, cv2
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tpbocr import segment, features
TESS = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

# hand-read ground truth (page 18), keyed by normalised leading text.
# 2=roman 3=italic 4=antique/bold  (caps=5 & parens=1 handled by text, skip)
GOLD = {
 # Avarice line (crystal clear)
 "calc. c.":2, "lyc.":4, "nat. c.":3, "sep.":3,
 # Anxiety tail lines
 "dros.":4,"fer.":4,"graph.":4,"hell.":4,"hep.":2,"hyos.":3,"ign.":4,
 "k. carb.":2,"k. iod.":3,"lach.":2,"meny.":2,"merc.":4,"merc. c.":4,
 "mur. ac.":2,"nux v.":2,"op.":3,"ox. ac.":3,"petrol.":3,"pho. ac.":2,
 "plat.":3,"pso.":4,"ruta":2,"saba.":2,"sabi.":4,"samb.":2,
 "spig.":3,"stan.":4,"stram.":4,"stro.":2,"sul.":4,"thea.":3,
 "thuj.":2,"valer.":2,
 # Despair tail
 "pb.":2,"puls.":4,"rhus":2,"sil.":3,"sul. ac.":3,"verb.":2,"verat. a.":4,
}

def norm(t):
    t = t.lower().strip()
    import re
    letters = re.sub(r"[^a-z. ]", "", t)
    return letters.strip(" .")

def key3(t):
    """first word's first 3 alpha chars — survives most OCR noise"""
    import re
    w = norm(t).split()
    if not w: return ""
    return re.sub(r"[^a-z]", "", w[0])[:3]

# build fuzzy gold by first-3 of first word
GOLD3 = {}
for k, v in GOLD.items():
    import re
    kk = re.sub(r"[^a-z]", "", k.split()[0])[:3]
    GOLD3.setdefault(kk, v)

def load_gray(path, scale=2):
    im=cv2.imdecode(np.fromfile(path,np.uint8),cv2.IMREAD_GRAYSCALE)
    if scale!=1: im=cv2.resize(im,None,fx=scale,fy=scale,interpolation=cv2.INTER_CUBIC)
    return im

g=load_gray(sys.argv[1], scale=int(sys.argv[2]) if len(sys.argv)>2 else 2)
toks=segment.tokens(g,tess_cmd=TESS)
groups={2:[],3:[],4:[]}
seen=set()
for t in toks:
    if t["is_heading"]:continue
    k3=key3(t["text"])
    r=GOLD3.get(k3)
    if r is None or k3 in seen: continue
    seen.add(k3)
    mp=segment.main_part(t["parts"])
    pad=3
    crop=g[max(0,mp["y"]-pad):mp["y"]+mp["h"]+pad, max(0,mp["x"]-pad):mp["x"]+mp["w"]+pad]
    f=features.measure(crop)
    if not f:continue
    groups[r].append((k3,f["weight"],f["slant"],f["density"],f["stroke"]))

names={2:"ROMAN",3:"ITALIC",4:"ANTIQUE"}
for r in (2,3,4):
    print("\n=== rank %d %s (n=%d) ==="%(r,names[r],len(groups[r])))
    print("  %-10s %6s %6s %6s %6s"%("tok","weight","slant","dens","stroke"))
    for k,w,s,d,st in groups[r]:
        print("  %-10s %6.3f %6.1f %6.3f %6.2f"%(k,w,s,d,st))
    if groups[r]:
        W=[x[1] for x in groups[r]];S=[x[2] for x in groups[r]]
        print("  -- weight mean %.3f med %.3f | slant mean %.1f med %.1f"%(
            np.mean(W),np.median(W),np.mean(S),np.median(S)))
