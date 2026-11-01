# -*- coding: utf-8 -*-
"""Train/evaluate the shape model on the gold pages (leave-one-page-out),
and measure consensus with the scalar weight/slant classifier.

Faces considered: 2 Roman, 3 Italic, 4 Antique (CAPS=5 / parens=1 are read from
text and excluded here). Prints per-page shape accuracy, scalar accuracy, and
the two-engine consensus (agree-rate + accuracy on the agreed set)."""
import sys, os, re, json
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import numpy as np, cv2
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tpbocr import segment, features, classify, glyphs, shape_model

TESS = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
B = r"../tpb-data/public-domain/books/07_Allen_1891_New_American_Edition_Boston/ocr_out"
PAGES = [("p0%d" % bp, B + "/therapeuticpocke0000timo_bp0%d.md" % bp)
         for bp in range(17, 25)]   # book pages 17..24 (vision gold bp017..bp024)

def nkey(s): return re.sub(r"[^a-z0-9]", "", s.lower())

def tok_rank(t):
    t = t.strip()
    if t.startswith("(") and t.endswith(")"): return 1
    if t.startswith("**") and t.endswith("**"): return 4
    if t.startswith("*") and t.endswith("*"): return 3
    core = re.sub(r"[*()]", "", t); L = [c for c in core if c.isalpha()]
    if L and all(c.isupper() for c in L): return 5
    return 2

def parse_ref(path):
    rub = []
    for line in open(path, encoding="utf-8"):
        m = re.match(r"\*\*(.+?)\.\*\*\s*[—-]+\s*(.*)", line.strip())
        if not m: continue
        items = [(re.sub(r"[*()]|\*\*","",t).strip(), tok_rank(t))
                 for t in m.group(2).split(",") if t.strip()]
        rub.append((m.group(1).strip(), items))
    return rub

def load_gray(name):
    im = cv2.imdecode(np.fromfile("input/%s.webp" % name, np.uint8), cv2.IMREAD_GRAYSCALE)
    return cv2.resize(im, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)

def match_rubric(rn, keys):
    rk = nkey(rn)
    for mk in keys:
        if nkey(mk)[:6] == rk[:6] or nkey(mk).startswith(rk[:5]) or rk.startswith(nkey(mk)[:5]):
            return mk
    return None

def page_tokens(name, refpath):
    """-> list of dict(name, gold, glyphs, feat) for tokens with gold in 2/3/4."""
    gray = load_gray(name)
    toks = segment.tokens(gray, tess_cmd=TESS)
    chars = glyphs.page_chars(gray, tess_cmd=TESS)
    # group my tokens by rubric
    myrub = {}; cur = None
    for t in toks:
        if t["is_heading"]:
            cur = t["rubric"]; myrub[cur] = []
        elif cur is not None:
            myrub[cur].append(t)
    ref = parse_ref(refpath)
    rows = []
    for rn, ritems in ref:
        mk = match_rubric(rn, list(myrub.keys()))
        if not mk: continue
        gmap = {}
        for txt, rk in ritems: gmap.setdefault(nkey(txt), rk)
        for t in myrub[mk]:
            k = nkey(t["text"])
            if k not in gmap: continue
            gold = gmap[k]
            if gold not in (2, 3, 4): continue
            box = segment.first_line_box(t["parts"])
            gl = glyphs.token_glyphs(gray, box, chars)
            pad = 3
            crop = gray[max(0,box[1]-pad):box[3]+pad, max(0,box[0]-pad):box[2]+pad]
            feat = features.measure(crop)
            rows.append(dict(name=t["text"], gold=gold, glyphs=gl, feat=feat))
    return rows

# cache token rows per page
DATA = {name: page_tokens(name, ref) for name, ref in PAGES}

def scalar_face(feat, weight_t):
    if feat is None: return 2
    if feat["slant"] >= classify.SLANT_T: return 3
    return 4 if feat["weight"] >= weight_t else 2

print("Leave-one-page-out evaluation (faces 2/3/4 only)\n")
tot_sh=tot_sc=tot=0; tot_agree=tot_agree_ok=0
for test_name, _ in PAGES:
    train = [s for n, rows in DATA.items() if n != test_name for s in rows]
    samples = [(ch, r["gold"], g) for r in train for ch, g in r["glyphs"]]
    model = shape_model.ShapeModel().fit(samples)
    # per-page scalar threshold from this page's upright weights
    up = [r["feat"]["weight"] for r in DATA[test_name]
          if r["feat"] and r["feat"]["slant"] < classify.SLANT_T]
    wt = classify.otsu_split(up) or classify.WEIGHT_T
    n=sh=sc=agree=agree_ok=0
    for r in DATA[test_name]:
        n += 1
        sc_face = scalar_face(r["feat"], wt)
        res = model.classify(r["glyphs"])
        sh_face = res["face"] if res else sc_face
        if sh_face == r["gold"]: sh += 1
        if sc_face == r["gold"]: sc += 1
        if sh_face == sc_face:
            agree += 1
            if sh_face == r["gold"]: agree_ok += 1
    print("%s  n=%3d  shape=%.1f%%  scalar=%.1f%%  consensus-agree=%.0f%% (acc on agreed=%.1f%%)"
          % (test_name, n, 100*sh/n, 100*sc/n, 100*agree/n, 100*agree_ok/max(1,agree)))
    tot+=n; tot_sh+=sh; tot_sc+=sc; tot_agree+=agree; tot_agree_ok+=agree_ok

print("\nOVERALL  n=%d  shape=%.1f%%  scalar=%.1f%%" % (tot, 100*tot_sh/tot, 100*tot_sc/tot))
print("consensus: %.0f%% of tokens agree, %.1f%% accurate there; %d flagged for review"
      % (100*tot_agree/tot, 100*tot_agree_ok/max(1,tot_agree), tot-tot_agree))
