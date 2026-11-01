# -*- coding: utf-8 -*-
"""Per-token typographic feature extraction (scale-normalised).

A "token" is one remedy entry (e.g. "Nux v.," / "CANNAB. I.," / "(Abrot.)").
We measure the signals that separate the five printed ranks of the TPB:

  rank 5  CAPITALS           -> all letters upper-case      (text)
  rank 4  Antique (bold)     -> heavy stroke, upright       (weight)
  rank 3  Italic             -> slanted                     (slant)
  rank 2  Roman              -> thin, upright               (weight+slant)
  rank 1  (Roman in parens)  -> wrapped in ( )              (text)

Everything geometric is normalised to a fixed x-height so a 96-dpi webp and a
600-dpi scan yield the same numbers.
"""
import numpy as np
import cv2

NORM_XH = 40.0          # all glyphs rescaled so x-height == 40 px


def binarize(gray):
    g = gray.astype(np.uint8)
    _, th = cv2.threshold(g, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    return (th > 0).astype(np.uint8)


def _trim(ink):
    ys, xs = np.nonzero(ink)
    if len(ys) == 0:
        return None
    return ink[ys.min():ys.max() + 1, xs.min():xs.max() + 1]


def estimate_xheight(ink):
    """x-height from connected components: drop punctuation (tiny) and
    ascenders/caps (tall); the median height of the remaining body glyphs is
    the x-height. Robust fallback to the dense-row band."""
    n, _, stats, _ = cv2.connectedComponentsWithStats(ink, connectivity=8)
    hs = [stats[i, cv2.CC_STAT_HEIGHT] for i in range(1, n)
          if stats[i, cv2.CC_STAT_AREA] >= 4]
    H = ink.shape[0]
    if hs:
        hs = sorted(hs)
        # keep the central cluster: ignore dots (<30% max) and tall caps
        big = max(hs)
        body = [h for h in hs if 0.30 * big <= h <= 0.82 * big]
        if body:
            return float(np.median(body))
        return float(np.median(hs))
    # fallback: dense horizontal band
    rowsum = ink.sum(axis=1).astype(np.float32)
    if rowsum.max() == 0:
        return float(H)
    dense = rowsum >= 0.4 * rowsum.max()
    best = cur = 0
    for d in dense:
        cur = cur + 1 if d else 0
        best = max(best, cur)
    return float(best or H)


def _normalize(ink):
    xh = estimate_xheight(ink)
    if xh <= 0:
        return ink, 1.0
    scale = NORM_XH / xh
    if abs(scale - 1.0) > 0.02:
        ink = cv2.resize(ink, None, fx=scale, fy=scale,
                         interpolation=cv2.INTER_NEAREST)
    return ink, xh


def stroke_width(ink):
    """Mean stroke full-width (px) via distance transform (continuous)."""
    dt = cv2.distanceTransform(ink, cv2.DIST_L2, 5)
    vals = dt[ink > 0]
    if len(vals) == 0:
        return 0.0
    core = vals[vals > 0.75]
    if len(core) < 0.2 * len(vals):
        core = vals
    return float(np.mean(core) * 2.0)


def body_runlen(ink):
    """Mean horizontal black-run length within the x-height body band.

    Each row of the body band crosses the glyph's vertical stems and bowls;
    the mean run length scales with stroke thickness, so it is a sturdier
    weight proxy than the distance transform for short abbreviations. Returned
    in px at the normalised x-height."""
    h, w = ink.shape
    rs = ink.sum(axis=1).astype(np.float32)
    tot = rs.sum()
    if tot == 0:
        return 0.0
    cum = np.cumsum(rs)
    lo = np.searchsorted(cum, 0.20 * tot)
    hi = np.searchsorted(cum, 0.80 * tot)
    band = ink[lo:hi + 1] if hi > lo else ink
    runs = []
    for row in band:
        idx = np.nonzero(row)[0]
        if len(idx) == 0:
            continue
        for seg in np.split(idx, np.nonzero(np.diff(idx) != 1)[0] + 1):
            runs.append(len(seg))
    if not runs:
        return 0.0
    return float(np.mean(runs))


def slant_angle(gray_crop, ink):
    """Forward lean in degrees from the gradient orientation of vertical stems.

    For a vertical stem the intensity gradient is horizontal; a stem leaning
    forward by theta rotates its edges — and the gradient — by theta. We take
    the magnitude-weighted median tilt over strong, near-vertical edges.
    Positive = italic forward lean."""
    g = gray_crop.astype(np.float32)
    gx = cv2.Sobel(g, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(g, cv2.CV_32F, 0, 1, ksize=3)
    mag = np.hypot(gx, gy)
    if mag.max() <= 0:
        return 0.0
    ang = np.degrees(np.arctan2(gy, gx))
    # fold gradient direction to (-90, 90]; 0 == horizontal gradient == vertical edge
    a = ((ang + 90.0) % 180.0) - 90.0
    strong = mag > max(0.25 * mag.max(), np.percentile(mag[mag > 0], 60))
    stem = strong & (np.abs(a) < 32.0)        # near-vertical edges only
    if ink.shape == a.shape:
        stem &= cv2.dilate(ink, np.ones((3, 3), np.uint8)) > 0
    vals = a[stem]
    wts = mag[stem]
    if len(vals) < 20:
        return 0.0
    order = np.argsort(vals)
    vals, wts = vals[order], wts[order]
    cw = np.cumsum(wts)
    med = vals[np.searchsorted(cw, cw[-1] / 2.0)]
    return float(round(med, 2))


def _strip_leading_cap(icrop, gcrop):
    """Every remedy token starts with a capital; on short abbreviations that
    capital dominates the crop and corrupts the lowercase-face signals — wide
    caps (A, M, N) inflate run-length -> false Antique, curved caps (C, G, O)
    fake a slant -> false Italic. Drop the leftmost glyph (the capital) and
    measure weight/slant on the lower-case body only."""
    n, lab, stats, _ = cv2.connectedComponentsWithStats(icrop, connectivity=8)
    if n <= 2:
        return icrop, gcrop
    comps = [(stats[i, cv2.CC_STAT_LEFT],
              stats[i, cv2.CC_STAT_LEFT] + stats[i, cv2.CC_STAT_WIDTH],
              stats[i, cv2.CC_STAT_HEIGHT], stats[i, cv2.CC_STAT_AREA])
             for i in range(1, n)]
    comps.sort(key=lambda c: c[0])
    maxh = max(c[2] for c in comps)
    left, right, hh, area = comps[0]
    # leading glyph must be tall (cap/ascender) and small enough to be one letter
    if hh < 0.72 * maxh or right > 0.6 * icrop.shape[1]:
        return icrop, gcrop
    body_i = icrop[:, right:]
    body_g = gcrop[:, right:]
    if body_i.sum() < 0.3 * icrop.sum() or body_i.shape[1] < 6:
        return icrop, gcrop
    return body_i, body_g


def measure(gray_crop):
    ink0 = binarize(gray_crop)
    t = _trim(ink0)
    if t is None or t.sum() < 10:
        return None
    # normalise scale by x-height, applying the SAME transform to grey + ink
    xh = estimate_xheight(t)
    scale = NORM_XH / xh if xh > 0 else 1.0
    ink = binarize(gray_crop)
    ys, xs = np.nonzero(ink)
    y0, y1, x0, x1 = ys.min(), ys.max(), xs.min(), xs.max()
    gcrop = gray_crop[y0:y1 + 1, x0:x1 + 1]
    icrop = ink[y0:y1 + 1, x0:x1 + 1]
    if abs(scale - 1.0) > 0.02:
        gcrop = cv2.resize(gcrop, None, fx=scale, fy=scale,
                           interpolation=cv2.INTER_CUBIC)
        icrop = cv2.resize(icrop, None, fx=scale, fy=scale,
                           interpolation=cv2.INTER_NEAREST)
    h, w = icrop.shape
    # NOTE: tested stripping the leading capital here (hypothesis: wide caps
    # inflate weight) — it REGRESSED accuracy, so we measure on the full token.
    sw = stroke_width(icrop)
    rl = body_runlen(icrop)
    density = float(icrop.sum()) / float(h * w)
    return dict(
        xheight=round(xh, 2),
        stroke=round(sw, 2),               # dt stroke width, px at NORM_XH
        runlen=round(rl, 2),               # body-band mean run length, px
        weight=round(rl / NORM_XH, 4),     # primary weight (scale-free)
        stroke_w=round(sw / NORM_XH, 4),   # secondary weight
        density=round(density, 4),
        slant=slant_angle(gcrop, icrop),
        h=int(h), w=int(w),
    )
