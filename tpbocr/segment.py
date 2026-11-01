# -*- coding: utf-8 -*-
"""Page -> ordered remedy tokens, using Tesseract for text + boxes.

Each TPB rubric reads:  Heading.—Rem1., Rem2., Rem3., ... Remn.
Remedies are comma-separated; a remedy may span several OCR "words"
(e.g. "Nux" "v.," or "Calc." "c.,"). The rubric heading is bold and joined
to the first remedy by an em-dash with no spaces, so Tesseract returns it
glued ("Amativeness.—Acon.,"); we split on the dash.
"""
import re
import numpy as np
import cv2
import pytesseract
from pytesseract import Output

DASH = re.compile(r"[—―‒–]|--")   # em / en / figure dashes


def _words(gray, tess_cmd, psm=6, lang="eng"):
    if tess_cmd:
        pytesseract.pytesseract.tesseract_cmd = tess_cmd
    d = pytesseract.image_to_data(gray, lang=lang, config="--psm %d" % psm,
                                  output_type=Output.DICT)
    out = []
    for i in range(len(d["text"])):
        t = d["text"][i]
        if not t or not t.strip():
            continue
        out.append(dict(
            text=t.strip(),
            conf=int(float(d["conf"][i])),
            x=int(d["left"][i]), y=int(d["top"][i]),
            w=int(d["width"][i]), h=int(d["height"][i]),
            line=(int(d["block_num"][i]), int(d["par_num"][i]), int(d["line_num"][i])),
        ))
    return out


def _split_dash(word):
    """Split a glued 'Heading.—Remedy' word. Returns (head, rest) boxes by
    proportional character position, or (None, word) if no dash."""
    m = DASH.search(word["text"])
    if not m:
        return None, word
    i = m.start()
    full = len(word["text"])
    frac = (i + 1) / full if full else 0.5
    xcut = word["x"] + int(word["w"] * frac)
    head = dict(word, text=word["text"][:i], w=xcut - word["x"])
    rest_text = word["text"][m.end():]
    rest = dict(word, text=rest_text, x=xcut, w=word["x"] + word["w"] - xcut)
    return head, rest


def tokens(gray, tess_cmd=None, psm=6, lang="eng", top_margin=0.055):
    """Return list of token dicts in reading order:
       {text, parts(list of word boxes), is_heading, rubric}
    Running head / page number above `top_margin` are dropped."""
    H = gray.shape[0]
    W = gray.shape[1]
    ws = _words(gray, tess_cmd, psm, lang)
    ws = [w for w in ws if w["y"] + w["h"] > top_margin * H]

    # Filter running heads (page numbers and all-caps chapter titles in top 17% of page)
    # This prevents page numbers (e.g. '19') from merging into the first remedy on continuation pages.
    filtered = []
    for w in ws:
        if w["y"] < 0.17 * H:
            clean = re.sub(r"[^A-Za-z0-9]", "", w["text"])
            if clean.isdigit() or (clean.isupper() and len(clean) >= 3 and not any(c.islower() for c in w["text"])):
                continue
            if not clean:
                continue
        filtered.append(w)
    ws = filtered

    # reading order
    ws.sort(key=lambda w: (w["line"], w["x"]))

    # A centred CHAPTER/SECTION heading ("Intellect.", "Vertigo.") sits alone on
    # its line, carries no comma and no dash, and is horizontally centred. It
    # is NOT a remedy; left in place it gets swallowed into the open remedy token
    # and mis-assigns the whole next rubric. Detect such lines and drop them so a
    # fresh rubric can start cleanly.
    heading_lines = set()
    by_line = {}
    for w in ws:
        by_line.setdefault(w["line"], []).append(w)
    for ln, lw in by_line.items():
        txt = " ".join(x["text"] for x in lw).strip()
        x0 = min(x["x"] for x in lw); x1 = max(x["x"] + x["w"] for x in lw)
        if ("," in txt) or DASH.search(txt) or len(lw) > 4:
            continue
        core = txt.rstrip(".")
        if not core or not re.match(r"^[A-Za-z][A-Za-z .]*$", core):
            continue
        # Insets alone also match a short final remedy at the left text margin
        # (for example Zinc.). Require the line midpoint near the page centre.
        centred = (x0 > 0.18 * W and W - x1 > 0.18 * W
                   and abs((x0 + x1) / 2 - W / 2) <= 0.05 * W)
        if centred and txt.endswith("."):
            heading_lines.add(ln)
    ws = [w for w in ws if w["line"] not in heading_lines]

    # expand dash-glued headings into [heading-token, remainder-word]
    seq = []   # each item: (kind, word)  kind in {'head','word'}
    for w in ws:
        head, rest = _split_dash(w)
        if head is not None and head["text"].strip():
            seq.append(("head", head))
            if rest["text"].strip():
                seq.append(("word", rest))
        else:
            seq.append(("word", w))

    toks = []
    cur = None          # accumulating remedy token
    rubric = None
    after_head = False

    def close():
        nonlocal cur, after_head
        if cur and cur["parts"]:
            cur["is_heading"] = (after_head and len(toks) >= 0 and cur.get("_fresh", False))
            toks.append(cur)
        cur = None

    for kind, w in seq:
        if kind == "head":
            # Multi-word headings ("Disposition generally affected.—") arrive as
            # separate plain words plus a dash-glued last word. The preceding
            # heading words, having no comma, get swallowed into the open remedy
            # (the previous rubric's last remedy ends in "." not ","), so reclaim
            # any words sitting on the head's own text line as the name prefix.
            prefix = []
            if cur and cur["parts"]:
                hline = w["line"]
                keep = [p for p in cur["parts"] if p["line"] != hline]
                pref = [p for p in cur["parts"] if p["line"] == hline]
                prefix = [p["text"] for p in pref]
                if keep:
                    cur["parts"] = keep
                    cur["text"] = " ".join(p["text"] for p in keep)
                    close()
                else:
                    cur = None
            else:
                close()
            name_txt = (" ".join(prefix) + " " + w["text"]).strip()
            # Keep the OCR heading text as evidence; clean only its boundary
            # punctuation so an isolated dash cannot create a second rubric.
            rubric = name_txt.strip(" .\t\r\n-—―‒–")
            toks.append(dict(text=name_txt, parts=[w], is_heading=True,
                             rubric=rubric))
            after_head = True
            continue
        if cur is None:
            cur = dict(text="", parts=[], is_heading=False, rubric=rubric,
                       _fresh=after_head)
            after_head = False
        cur["text"] = (cur["text"] + " " + w["text"]).strip()
        cur["parts"].append(w)
        # a remedy ends at a comma (sometimes OCR'd ';' or trailing ',')
        if re.search(r"[,;]\s*$", w["text"]) or w["text"].endswith(".,"):
            close()
    close()

    for t in toks:
        t.pop("_fresh", None)
    return toks


def union_box(parts):
    x0 = min(p["x"] for p in parts); y0 = min(p["y"] for p in parts)
    x1 = max(p["x"] + p["w"] for p in parts); y1 = max(p["y"] + p["h"] for p in parts)
    return x0, y0, x1, y1


def line_boxes(parts):
    """Return tight per-line bounding boxes for parts. When a remedy wraps across lines
    (e.g. 'Calc.' at line-end and 'ph.,' at next line-start), this returns separate
    boxes for each line rather than a single giant page-wide box that overlaps all text."""
    if not parts:
        return []
    lines = []
    for p in sorted(parts, key=lambda p: (p["y"], p["x"])):
        placed = False
        for line in lines:
            line_y = sum(x["y"] for x in line) / len(line)
            line_h = sum(x["h"] for x in line) / len(line)
            if abs(p["y"] - line_y) < 0.6 * line_h:
                line.append(p)
                placed = True
                break
        if not placed:
            lines.append([p])
    boxes = []
    for line in lines:
        x0 = min(p["x"] for p in line)
        y0 = min(p["y"] for p in line)
        x1 = max(p["x"] + p["w"] for p in line)
        y1 = max(p["y"] + p["h"] for p in line)
        boxes.append([int(x0), int(y0), int(x1), int(y1)])
    return boxes


def main_part(parts):
    """The constituent word carrying the remedy's leading capital — widest box
    on the first line of the token (used for face measurement)."""
    y0 = min(p["y"] for p in parts)
    first_line = [p for p in parts if p["y"] - y0 < 0.6 * p["h"]]
    cand = first_line or parts
    return max(cand, key=lambda p: p["w"])


def first_line_box(parts):
    """Union box of all word-parts sitting on the token's first line. Gives
    more ink than a single word, so stroke-weight/slant are steadier, while
    excluding a hyphenated continuation that wrapped to the next line."""
    y0 = min(p["y"] for p in parts)
    hmed = sorted(p["h"] for p in parts)[len(parts) // 2]
    fl = [p for p in parts if p["y"] - y0 < 0.6 * hmed]
    fl = fl or parts
    x0 = min(p["x"] for p in fl); yy0 = min(p["y"] for p in fl)
    x1 = max(p["x"] + p["w"] for p in fl); y1 = max(p["y"] + p["h"] for p in fl)
    return x0, yy0, x1, y1
