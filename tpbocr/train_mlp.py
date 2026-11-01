# -*- coding: utf-8 -*-
"""Trained glyph classifier (scikit-learn MLP) — the real model upgrade.

Uses the vision-gold pages as labels: every lower-case glyph bitmap (+ its
token's per-page-normalised weight and slant) is a training example for the
token's face (2 Roman / 3 Italic / 4 Antique). We classify each glyph and
average the class-probabilities over a token's letters. This learns the actual
Roman vs Antique letterforms instead of thresholding one scalar.
Evaluated leave-one-gold-page-out against the hand scalar baseline.
"""
import sys, os
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import numpy as np, cv2
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tpbocr import train_shape as TS, classify
from sklearn.neural_network import MLPClassifier

G = 20   # glyph downsample

def page_norm(rows):
    w = [r["feat"]["weight"] for r in rows if r["feat"] and r["feat"]["slant"] < classify.SLANT_T]
    m = np.median(w); mad = np.median(np.abs(np.array(w) - m)) * 1.4826 + 1e-6
    return m, mad

def glyph_vec(g):
    gg = cv2.resize(g.astype(np.float32), (G, G), interpolation=cv2.INTER_AREA)
    return gg.flatten()

def build(rows, norm):
    """-> per-glyph X, y(face), and token index for aggregation."""
    X, y, tok = [], [], []
    m, mad = norm
    for ti, r in enumerate(rows):
        f = r["feat"]
        if not f: continue
        zw = (f["weight"] - m) / mad
        extra = [zw, f["slant"] / 20.0, abs(f["slant"]) / 20.0]
        for ch, g in r["glyphs"]:
            X.append(np.concatenate([glyph_vec(g), extra]))
            y.append(r["gold"]); tok.append((ti, r["gold"]))
    return np.array(X), np.array(y), tok

pages = list(TS.DATA.keys())
norms = {pg: page_norm(TS.DATA[pg]) for pg in pages}

print("Leave-one-gold-page-out: trained MLP vs hand scalar\n")
tot = okM = okS = 0
for test in pages:
    Xtr, ytr = [], []
    for pg in pages:
        if pg == test: continue
        X, y, _ = build(TS.DATA[pg], norms[pg])
        if len(X): Xtr.append(X); ytr.append(y)
    Xtr = np.vstack(Xtr); ytr = np.concatenate(ytr)
    clf = MLPClassifier(hidden_layer_sizes=(120,), max_iter=400,
                        alpha=1e-3, random_state=0).fit(Xtr, ytr)
    # scalar per-page threshold for baseline
    up = [r["feat"]["weight"] for r in TS.DATA[test] if r["feat"] and r["feat"]["slant"] < classify.SLANT_T]
    wt = classify.otsu_split(up) or classify.WEIGHT_T
    Xte, yte, tok = build(TS.DATA[test], norms[test])
    proba = clf.predict_proba(Xte); cls = clf.classes_
    # aggregate per token
    nM = nS = n = 0
    agg = {}
    for i, (ti, gold) in enumerate(tok):
        agg.setdefault(ti, [np.zeros(len(cls)), gold])
        agg[ti][0] += proba[i]
    for ti, (p, gold) in agg.items():
        pred = cls[int(np.argmax(p))]
        n += 1; nM += (pred == gold)
    # scalar on same tokens (those with glyphs)
    for ti in agg:
        r = TS.DATA[test][ti]; f = r["feat"]
        sc = 3 if f["slant"] >= classify.SLANT_T else (4 if f["weight"] >= wt else 2)
        nS += (sc == agg[ti][1])
    print("  %s  n=%3d  MLP=%.1f%%  scalar=%.1f%%" % (test, n, 100*nM/n, 100*nS/n))
    tot += n; okM += nM; okS += nS
print("\n  OVERALL  MLP=%.1f%%  scalar=%.1f%%" % (100*okM/tot, 100*okS/tot))
