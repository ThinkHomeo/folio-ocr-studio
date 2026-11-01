# -*- coding: utf-8 -*-
"""Rank classifier: feature dict (+ token text) -> rank 1..5 with confidence.

Decision order (each rank has a distinct, independent typographic signature):

  1. text wrapped in ( )          -> rank 1  Roman in parentheses
  2. all alphabetic chars UPPER   -> rank 5  CAPITALS
  3. forward slant > SLANT_T      -> rank 3  Italic
  4. stroke weight  > WEIGHT_T    -> rank 4  Antique (bold)
  5. otherwise                    -> rank 2  Roman

Thresholds are calibrated on the 1891 Boston edition at full scan resolution
(see calibrate/septest). They are expressed scale-free (weight = stroke / x-
height, slant in degrees) so they travel across resolutions, but grading is
only reliable at >= ~300 dpi; below that `confidence` drops and tokens near a
boundary are flagged for review.
"""
import re

SLANT_T = 6.5      # deg; italic lean clearly exceeds roman jitter (~0 +/-3)
WEIGHT_T = 0.290   # body run length / x-height; antique above, roman below
# soft margins used only to compute a confidence score
SLANT_M = 3.0
WEIGHT_M = 0.025

RANK_NAME = {5: "CAPITALS", 4: "Antique", 3: "Italic", 2: "Roman",
             1: "Roman-paren"}


def is_caps(text):
    letters = [c for c in text if c.isalpha()]
    return bool(letters) and all(c.isupper() for c in letters)


def is_paren(text):
    return text.strip().lstrip(":;.").startswith("(")


def classify(text, feat, weight_t=WEIGHT_T):
    """Return dict(rank, name, confidence 0..1, why)."""
    t = text.strip()
    if is_paren(t):
        return _mk(1, 1.0, "parentheses")
    if is_caps(t):
        return _mk(5, 1.0, "all-caps")
    if feat is None:
        return _mk(2, 0.0, "no-features")

    sl = feat["slant"]
    wt = feat["weight"]

    # italic first: slant is the most reliable high-res signal
    if sl >= SLANT_T:
        conf = _sigmoid((sl - SLANT_T) / SLANT_M)
        return _mk(3, conf, "slant=%.1f" % sl)

    # among upright faces, weight splits antique from roman
    if wt >= weight_t:
        conf = _sigmoid((wt - weight_t) / WEIGHT_M)
        return _mk(4, conf, "weight=%.3f slant=%.1f" % (wt, sl))

    conf = _sigmoid((weight_t - wt) / WEIGHT_M)
    # near-boundary slant also lowers roman confidence
    if sl > SLANT_T - SLANT_M:
        conf = min(conf, _sigmoid((SLANT_T - sl) / SLANT_M))
    return _mk(2, conf, "weight=%.3f slant=%.1f" % (wt, sl))


def kmeans2(values, iters=50):
    """1-D 2-means on the Roman/Antique weight populations. Returns
    (lo_center, hi_center, threshold, separation).

    Self-calibrating against per-page ink/exposure drift: the two faces are
    two clusters whatever the exposure. Input is trimmed to [p5,p90] first so
    a few mis-segmented tokens (merged words -> huge run-length) cannot drag a
    centre to an absurd value and push the valley out of range."""
    import numpy as np
    a = np.sort(np.asarray([x for x in values if x is not None], float))
    if len(a) < 10:
        return None
    lo_c, hi_c = np.percentile(a, 5), np.percentile(a, 90)
    v = a[(a >= lo_c) & (a <= hi_c)]
    if len(v) < 8:
        v = a
    c0, c1 = np.percentile(v, 25), np.percentile(v, 75)
    if c1 - c0 < 1e-6:
        return None
    for _ in range(iters):
        mid = (c0 + c1) / 2
        lo, hi = v[v <= mid], v[v > mid]
        if len(lo) == 0 or len(hi) == 0:
            break
        n0, n1 = lo.mean(), hi.mean()
        if abs(n0 - c0) < 1e-6 and abs(n1 - c1) < 1e-6:
            c0, c1 = n0, n1
            break
        c0, c1 = n0, n1
    thr = (c0 + c1) / 2
    sep = (c1 - c0) / (v.std() + 1e-9)
    return float(c0), float(c1), float(thr), float(sep)


def otsu_split(values):
    """Back-compat wrapper: per-page Antique/Roman threshold via 2-means."""
    r = kmeans2(values)
    if r is None:
        return None
    c0, c1, thr, sep = r
    # only trust a genuinely bimodal split in a sane range
    if sep < 0.45 or not (0.20 <= thr <= 0.42):
        return None
    return thr


def _sigmoid(x):
    import math
    return round(1.0 / (1.0 + math.exp(-2.0 * x)), 3)


def _mk(rank, conf, why):
    return dict(rank=rank, name=RANK_NAME[rank], confidence=conf, why=why)
