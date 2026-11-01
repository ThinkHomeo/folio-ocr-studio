# -*- coding: utf-8 -*-
"""Extract a clean, upright, hi-res single page from the Archive.org *_orig jp2
camera scans of the Therapeutic Pocket Book.

Each jp2 leaf is one book page shot sideways in a dark scanning cradle
(6000x4000 landscape; the page's TOP edge points right, so a 90 CCW rotation
makes it upright). We rotate, find the bright page rectangle (Otsu + morphology,
largest portrait blob) and crop it out of the dark surround.

mapping: book page = leaf - 6   (verified: leaf 0023 = p.17, leaf 0036 = p.30)

Usage: python -m tpbocr.extract_hires 30 31 32 ...   (book page numbers)
       python -m tpbocr.extract_hires --leaf 36       (by leaf index instead)
Outputs per page into --out (default input/):
   p0NN_hires.png   full-resolution upright crop (for archival / zoom)
   p0NN.png         downscaled (height --read-h) upright crop (for vision OCR)
and a debug box image into out/_calib/ so the crop can be eyeballed.
"""
import sys, os, argparse
import numpy as np, cv2

JP2 = os.path.join(os.path.dirname(__file__), "..", "..", "tpb-data", "New folder1",
                   "therapeuticpocke0000timo_orig_jp2",
                   "therapeuticpocke0000timo_orig_%04d.jp2")

def _page_bbox(im):
    """largest bright portrait rectangle = the in-focus page."""
    blur = cv2.GaussianBlur(im, (0, 0), 3)
    th = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
    k = cv2.getStructuringElement(cv2.MORPH_RECT, (41, 41))
    th = cv2.morphologyEx(th, cv2.MORPH_CLOSE, k)
    cnts, _ = cv2.findContours(th, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    H, W = im.shape
    best = None
    for c in cnts:
        x, y, w, h = cv2.boundingRect(c)
        if w < W * 0.2 or h < H * 0.25:        # ignore small blobs / strips
            continue
        fill = cv2.contourArea(c) / float(w * h)
        score = (w * h) * fill
        if best is None or score > best[0]:
            best = (score, (x, y, w, h))
    return best[1] if best else (0, 0, W, H)


def extract(leaf, outdir, read_h=2600, margin=45, debug=True):
    raw = np.fromfile(JP2 % leaf, np.uint8)
    im = cv2.imdecode(raw, cv2.IMREAD_GRAYSCALE)
    if im is None:
        raise SystemExit("cannot decode leaf %d" % leaf)
    im = cv2.rotate(im, cv2.ROTATE_90_COUNTERCLOCKWISE)   # sideways -> upright
    H, W = im.shape
    x, y, w, h = _page_bbox(im)
    x0, y0 = max(0, x - margin), max(0, y - margin)
    x1, y1 = min(W, x + w + margin), min(H, y + h + margin)
    crop = im[y0:y1, x0:x1]
    page = leaf - 6
    os.makedirs(outdir, exist_ok=True)
    hires = os.path.join(outdir, "p%03d_hires.png" % page)
    cv2.imencode(".png", crop)[1].tofile(hires)
    ch, cw = crop.shape
    sc = read_h / float(ch)
    small = cv2.resize(crop, (max(1, int(cw * sc)), read_h), interpolation=cv2.INTER_AREA)
    read = os.path.join(outdir, "p%03d.png" % page)
    cv2.imencode(".png", small)[1].tofile(read)
    if debug:
        dbg = cv2.cvtColor(cv2.resize(im, (W // 4, H // 4)), cv2.COLOR_GRAY2BGR)
        cv2.rectangle(dbg, (x0 // 4, y0 // 4), (x1 // 4, y1 // 4), (0, 0, 255), 3)
        os.makedirs("out/_calib", exist_ok=True)
        cv2.imencode(".png", dbg)[1].tofile("out/_calib/box_p%03d.png" % page)
    print("page %d (leaf %d): crop %dx%d -> %s , %s" % (page, leaf, cw, ch, hires, read))
    return hires, read


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pages", nargs="*", type=int, help="book page numbers")
    ap.add_argument("--leaf", type=int, action="append", default=[],
                    help="extract by leaf index instead of page number")
    ap.add_argument("--out", default="input")
    ap.add_argument("--read-h", type=int, default=2600)
    a = ap.parse_args()
    leaves = [p + 6 for p in a.pages] + list(a.leaf)
    if not leaves:
        raise SystemExit("give page numbers (e.g. 30 31 32) or --leaf N")
    for lf in leaves:
        extract(lf, a.out, read_h=a.read_h)


if __name__ == "__main__":
    main()
