# -*- coding: utf-8 -*-
"""Per-character glyph extraction for shape-based face matching.

Tesseract gives a box + identity for every character on the page. We keep the
lower-case letters of each remedy token (the shape-discriminative part), crop
and size-normalise each to a fixed binary bitmap, and hand them to the shape
model. Capitals and punctuation are skipped — capitals share the same form in
Roman and Antique and only add noise, and we already read CAPS from the text.
"""
import re
import numpy as np
import cv2
import pytesseract
from tpbocr import features as _feat

GLYPH = 40          # normalised glyph canvas (GLYPH x GLYPH)


def page_chars(gray, tess_cmd=None, psm=6, lang="eng"):
    """-> list of dict(ch, x0, y0, x1, y1) in top-left pixel coords."""
    if tess_cmd:
        pytesseract.pytesseract.tesseract_cmd = tess_cmd
    H = gray.shape[0]
    raw = pytesseract.image_to_boxes(gray, lang=lang, config="--psm %d" % psm)
    out = []
    for line in raw.splitlines():
        p = line.split()
        if len(p) < 5:
            continue
        ch = p[0]
        x0, ybl, x1, ytl = int(p[1]), int(p[2]), int(p[3]), int(p[4])
        y0 = H - ytl          # tesseract box origin is bottom-left; flip y
        y1 = H - ybl
        out.append(dict(ch=ch, x0=x0, y0=y0, x1=x1, y1=y1))
    return out


def _ink_glyph(gray, box, scale, pad=2):
    """Grey ink crop scaled by `scale` (a per-token x-height factor) and placed,
    un-stretched, centred in a GLYPH canvas. Keeping grey + a common x-height
    scale PRESERVES stroke thickness, so the prototype carries the weight signal
    (Antique vs Roman) as well as the shape (Italic vs upright)."""
    x0, y0, x1, y1 = box
    crop = gray[max(0, y0 - pad):y1 + pad, max(0, x0 - pad):x1 + pad]
    if crop.size == 0:
        return None
    _, th = cv2.threshold(crop.astype(np.uint8), 0, 255,
                          cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    ink = (th > 0).astype(np.float32)       # 1 = ink
    ys, xs = np.nonzero(ink)
    if len(ys) < 4:
        return None
    g = ink[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    if abs(scale - 1.0) > 0.02:
        g = cv2.resize(g, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    h, w = g.shape
    if h > GLYPH or w > GLYPH:              # too big: fit inside canvas
        f = min(GLYPH / h, GLYPH / w)
        g = cv2.resize(g, None, fx=f, fy=f, interpolation=cv2.INTER_AREA)
        h, w = g.shape
    canvas = np.zeros((GLYPH, GLYPH), np.float32)
    oy, ox = (GLYPH - h) // 2, (GLYPH - w) // 2
    canvas[oy:oy + h, ox:ox + w] = g
    return canvas


def token_glyphs(gray, token_box, chars):
    """Lower-case glyph bitmaps (weight-preserving) for one token."""
    x0, y0, x1, y1 = token_box
    # estimate this token's x-height from its full-line ink, for a common scale
    pad = 3
    tc = gray[max(0, y0 - pad):y1 + pad, max(0, x0 - pad):x1 + pad]
    ink = _feat.binarize(tc); tr = _feat._trim(ink)
    xh = _feat.estimate_xheight(tr) if tr is not None else 0
    scale = (_feat.NORM_XH / xh) if xh > 0 else 1.0
    out = []
    for c in chars:
        cx = (c["x0"] + c["x1"]) / 2
        cy = (c["y0"] + c["y1"]) / 2
        if x0 <= cx <= x1 and y0 <= cy <= y1 and re.match(r"^[a-z]$", c["ch"]):
            g = _ink_glyph(gray, (c["x0"], c["y0"], c["x1"], c["y1"]), scale)
            if g is not None:
                out.append((c["ch"], g))
    return out
