# -*- coding: utf-8 -*-
"""End-to-end: page image -> graded rubrics (JSON) + overlay + proof.

Usage:
  python -m tpbocr.pipeline INPUT.(webp|png|jpg|tif) [--scale N] [--out DIR]
                            [--tag NAME] [--tess PATH]

Outputs (in --out, default ./out):
  <tag>.json      structured  {page, rubrics:[{rubric, remedies:[{text,rank,
                              rank_name,confidence,bbox,features}]}]}
  <tag>_proof.txt human-readable, remedies grouped by rank per rubric
  <tag>_overlay.png  the page with every token boxed in its rank colour
"""
import sys, os, io, json, argparse
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import numpy as np
import cv2
from PIL import Image, ImageDraw, ImageFont

from tpbocr import segment, features, classify
from tpbocr import glyphs as _glyphs
from tpbocr import shape_model as _shape
from tpbocr import model_mlp as _mlp

DEFAULT_TESS = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

RANK_COLOR = {   # RGB
    5: (198, 40, 40),    # CAPITALS  - red
    4: (216, 120, 0),    # Antique   - orange
    3: (26, 122, 60),    # Italic    - green
    2: (30, 90, 200),    # Roman     - blue
    1: (120, 60, 170),   # paren     - purple
}


def load_gray(path, scale):
    data = np.fromfile(path, dtype=np.uint8)
    im = cv2.imdecode(data, cv2.IMREAD_GRAYSCALE)
    if im is None:
        raise SystemExit("cannot read image: %s" % path)
    if scale != 1:
        im = cv2.resize(im, None, fx=scale, fy=scale,
                        interpolation=cv2.INTER_CUBIC)
    return im


def process(path, scale=1, tess=DEFAULT_TESS, adaptive=True, shape_model_path=None,
            mlp_model_path=None):
    for model_path in (shape_model_path, mlp_model_path):
        if model_path and not os.path.isfile(model_path):
            raise FileNotFoundError("Requested classifier model is missing: %s" % model_path)
    gray = load_gray(path, scale)
    toks = segment.tokens(gray, tess_cmd=tess)
    # optional shape model = independent 2nd opinion on each token's face
    smodel = chars = None
    if shape_model_path and os.path.exists(shape_model_path):
        smodel = _shape.ShapeModel.load(shape_model_path)
        chars = _glyphs.page_chars(gray, tess_cmd=tess)
    # optional trained MLP = upgraded PRIMARY face engine (needs glyphs too)
    mlp = None
    if mlp_model_path and os.path.exists(mlp_model_path):
        mlp = _mlp.MLPFace.load(mlp_model_path)
        if chars is None:
            chars = _glyphs.page_chars(gray, tess_cmd=tess)
    # pass 1: measure every remedy token
    measured = []
    for t in toks:
        if t["is_heading"]:
            measured.append((t, None, None))
            continue
        x0, y0, x1, y1 = segment.first_line_box(t["parts"])
        pad = 3
        crop = gray[max(0, y0 - pad):y1 + pad, max(0, x0 - pad):x1 + pad]
        f = features.measure(crop)
        measured.append((t, f, (x0, y0, x1, y1)))

    # adaptive antique/roman split from this page's upright-token weights
    weight_t = classify.WEIGHT_T
    upright = [f["weight"] for (t, f, _) in measured
               if f and f["slant"] < classify.SLANT_T
               and not classify.is_caps(t["text"])
               and not classify.is_paren(t["text"])]
    if adaptive:
        split = classify.otsu_split(upright)
        if split:
            weight_t = split
    page_norm = _mlp.page_norm(upright) if mlp else None

    rubrics = []
    cur = None
    seen_heading = False
    for t, f, box in measured:
        if t["is_heading"]:
            seen_heading = True
            cur = dict(rubric=t["rubric"], remedies=[])
            rubrics.append(cur)
            continue
        # drop running head / chapter title appearing before the first rubric
        if not seen_heading:
            import re as _re
            if not _re.search(r"[a-z]", t["text"]) and "," not in t["text"]:
                continue
        cls = classify.classify(t["text"], f, weight_t=weight_t)
        lboxes = segment.line_boxes(t["parts"]) if hasattr(segment, "line_boxes") else []
        if len(lboxes) > 1:
            primary_bbox = lboxes[0]
        else:
            ub = segment.union_box(t["parts"])
            primary_bbox = [int(ub[0]), int(ub[1]), int(ub[2]), int(ub[3])]
        if not lboxes:
            lboxes = [primary_bbox]
        scalar_rank = cls["rank"]
        rank = scalar_rank
        conf = cls["confidence"]; why = cls["why"]
        shape_rank = None; mlp_rank = None; agree = None
        ocr_conf = min(p.get("conf", 0) for p in t["parts"]) / 100.0
        flag = bool(conf < 0.6 or ocr_conf < 0.8 or f is None)
        if scalar_rank == 1:
            flag = flag or not _clean(t["text"]).endswith(")")
        if scalar_rank in (2, 3, 4):           # a measured lower-case face
            gl = _glyphs.token_glyphs(gray, box, chars) if chars is not None else []
            # upgraded primary: trained MLP (falls back to scalar if no glyphs)
            if mlp is not None:
                res = mlp.classify(gl, f, page_norm)
                if res:
                    mlp_rank = res["face"]; rank = mlp_rank
                    conf = res["confidence"]; why = "mlp p=%.2f" % res["confidence"]
            # independent shape opinion
            if smodel is not None:
                sres = smodel.classify(gl)
                if sres:
                    shape_rank = sres["face"]
            margin = (abs(f["weight"] - weight_t) / weight_t) if (f and rank in (2, 4)) else 1.0
            votes = [v for v in (scalar_rank, mlp_rank, shape_rank) if v is not None]
            agree = (len(votes) == 3 and len(set(votes)) == 1)
            flag = bool(flag or (not agree) or (margin < 0.10) or (conf < 0.6))
        rec = dict(
            text=_clean(t["text"]),
            raw=t["text"],
            rank=rank, rank_name=classify.RANK_NAME[rank],
            scalar_rank=scalar_rank, mlp_rank=mlp_rank, shape_rank=shape_rank,
            confidence=conf, why=why, agree=agree, flag=flag,
            ocr_confidence=ocr_conf,
            bbox=primary_bbox,
            boxes=lboxes,
            features=f,
        )
        if cur is None:
            cur = dict(rubric=None, remedies=[]); rubrics.append(cur)
        cur["remedies"].append(rec)
    return dict(page=os.path.basename(path), scale=scale,
                weight_threshold=round(weight_t, 4),
                image_size=[int(gray.shape[1]), int(gray.shape[0])],
                rubrics=rubrics), gray


def _clean(s):
    import re
    s = s.strip()
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"[,;]+$", "", s).strip()
    s = re.sub(r"\.{2,}", ".", s)
    return s


def write_json(doc, p):
    with open(p, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=1)


def write_proof(doc, p):
    order = [5, 4, 3, 2, 1]
    with open(p, "w", encoding="utf-8") as f:
        f.write("PAGE %s   (scale %s)\n" % (doc["page"], doc["scale"]))
        f.write("rank 5=CAPITALS 4=Antique/bold 3=Italic 2=Roman 1=(paren)\n")
        f.write("=" * 64 + "\n")
        for ru in doc["rubrics"]:
            f.write("\n%s\n" % (ru["rubric"] or "(no heading)"))
            by = {r: [] for r in order}
            for rem in ru["remedies"]:
                by[rem["rank"]].append(rem)
            for r in order:
                if not by[r]:
                    continue
                items = []
                for rem in by[r]:
                    mark = "" if rem["confidence"] >= 0.6 else "?"
                    items.append("%s%s" % (rem["text"], mark))
                f.write("  [%d %s] %s\n" % (
                    r, classify.RANK_NAME[r], ", ".join(items)))


def write_overlay(doc, gray, p):
    rgb = cv2.cvtColor(gray, cv2.COLOR_GRAY2RGB)
    im = Image.fromarray(rgb)
    d = ImageDraw.Draw(im)
    for ru in doc["rubrics"]:
        for rem in ru["remedies"]:
            x0, y0, x1, y1 = rem["bbox"]
            col = RANK_COLOR[rem["rank"]]
            w = 3 if rem["confidence"] >= 0.6 else 1
            d.rectangle([x0, y0, x1, y1], outline=col, width=w)
            d.text((x0, max(0, y0 - 14)), str(rem["rank"]), fill=col)
    # legend
    lx, ly = 10, 10
    for r in [5, 4, 3, 2, 1]:
        d.rectangle([lx, ly, lx + 16, ly + 16], fill=RANK_COLOR[r])
        d.text((lx + 22, ly + 2), "%d %s" % (r, classify.RANK_NAME[r]),
               fill=(0, 0, 0))
        ly += 20
    im.save(p)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input")
    ap.add_argument("--scale", type=int, default=1)
    ap.add_argument("--out", default="out")
    ap.add_argument("--tag", default=None)
    ap.add_argument("--tess", default=DEFAULT_TESS)
    ap.add_argument("--shape-model", default=None,
                    help="pickle: independent shape 2nd-opinion + review flag")
    ap.add_argument("--mlp-model", default=None,
                    help="pickle: trained MLP face classifier (upgraded primary)")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    tag = a.tag or os.path.splitext(os.path.basename(a.input))[0]
    doc, gray = process(a.input, a.scale, a.tess, shape_model_path=a.shape_model,
                        mlp_model_path=a.mlp_model)
    write_json(doc, os.path.join(a.out, tag + ".json"))
    write_proof(doc, os.path.join(a.out, tag + "_proof.txt"))
    write_overlay(doc, gray, os.path.join(a.out, tag + "_overlay.png"))
    n = sum(len(r["remedies"]) for r in doc["rubrics"])
    low = sum(1 for r in doc["rubrics"] for x in r["remedies"]
              if x["confidence"] < 0.6)
    print("%s: %d rubrics, %d remedy tokens (%d low-confidence)" % (
        tag, len(doc["rubrics"]), n, low))
    print("wrote %s.json / _proof.txt / _overlay.png in %s" % (tag, a.out))


if __name__ == "__main__":
    main()
