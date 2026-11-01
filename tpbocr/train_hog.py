# -*- coding: utf-8 -*-
"""EXPERIMENT: high-resolution glyphs + HOG features + bigger classifier.

Instead of the downsized webp + 20x20 raw-pixel glyph, render each gold page
from the full-resolution jp2 scan, crop each lower-case glyph at that scale,
and describe it with a HOG (histogram-of-oriented-gradients) descriptor — which
captures stroke-orientation energy (bold = more, italic = tilted) far better
than raw pixels. Train a larger MLP on HOG(+per-page weight/slant) and evaluate
leave-one-page-out against the vision gold.
"""
import sys, os, re, io, zipfile
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import numpy as np, cv2
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tpbocr import segment, features, classify, glyphs
from PIL import Image
from sklearn.neural_network import MLPClassifier

TESS = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BK = os.path.join(ROOT, "..", "tpb-data", "public-domain", "books",
                  "07_Allen_1891_New_American_Edition_Boston")
ZIP = os.path.join(BK, "therapeuticpocke0000timo_jp2.zip")
GOLD = os.path.join(BK, "ocr_out", "therapeuticpocke0000timo_bp0%d.md")
PAGES = list(range(17, 25))          # book pages; leaf = page+6

HOGSZ = 32
CELL = 8; NBIN = 9

def _hog_compute(g):
    """Minimal HOG: 8x8 cells, 9 unsigned-orientation bins, 2x2 block L2-norm.
    cv2.HOGDescriptor is absent in this build, so compute it with numpy."""
    g = g.astype(np.float32)
    gx = cv2.Sobel(g, cv2.CV_32F, 1, 0, ksize=1)
    gy = cv2.Sobel(g, cv2.CV_32F, 0, 1, ksize=1)
    mag = np.hypot(gx, gy)
    ang = (np.degrees(np.arctan2(gy, gx)) % 180.0)
    nb = HOGSZ // CELL
    cells = np.zeros((nb, nb, NBIN), np.float32)
    binw = 180.0 / NBIN
    bi = np.minimum((ang / binw).astype(int), NBIN - 1)
    for cy in range(nb):
        for cx in range(nb):
            m = mag[cy*CELL:(cy+1)*CELL, cx*CELL:(cx+1)*CELL]
            b = bi[cy*CELL:(cy+1)*CELL, cx*CELL:(cx+1)*CELL]
            for k in range(NBIN):
                cells[cy, cx, k] = m[b == k].sum()
    feats = []
    for by in range(nb - 1):
        for bx in range(nb - 1):
            blk = cells[by:by+2, bx:bx+2, :].flatten()
            blk = blk / (np.linalg.norm(blk) + 1e-6)
            feats.append(blk)
    return np.concatenate(feats) if feats else np.zeros(1, np.float32)

def nkey(s): return re.sub(r"[^a-z0-9]", "", s.lower())
def tok_rank(t):
    t = t.strip()
    if t.startswith("(") and t.endswith(")"): return 1
    if t.startswith("**") and t.endswith("**"): return 4
    if t.startswith("*") and t.endswith("*"): return 3
    c = re.sub(r"[*()]", "", t); L = [x for x in c if x.isalpha()]
    return 5 if (L and all(x.isupper() for x in L)) else 2
def parse_ref(path):
    rub = []
    for line in open(path, encoding="utf-8"):
        m = re.match(r"\*\*(.+?)\.\*\*\s*[—-]+\s*(.*)", line.strip())
        if m: rub.append((m.group(1).strip(),
            [(re.sub(r"[*()]|\*\*","",t).strip(), tok_rank(t)) for t in m.group(2).split(",") if t.strip()]))
    return rub
def match_rubric(rn, keys):
    rk = nkey(rn)
    for k in keys:
        if nkey(k)[:6]==rk[:6] or nkey(k).startswith(rk[:5]) or rk.startswith(nkey(k)[:5]): return k

def leaf_gray(page):
    z = zipfile.ZipFile(ZIP)
    name = "therapeuticpocke0000timo_jp2/therapeuticpocke0000timo_%04d.jp2" % (page + 6)
    im = Image.open(io.BytesIO(z.read(name))).convert("L")
    return np.asarray(im)

def hog_glyph(gray, box, pad=3):
    x0, y0, x1, y1 = box
    crop = gray[max(0,y0-pad):y1+pad, max(0,x0-pad):x1+pad]
    if crop.size == 0 or min(crop.shape) < 4: return None
    h, w = crop.shape; s = max(h, w)
    sq = np.full((s, s), 255, np.uint8)
    sq[(s-h)//2:(s-h)//2+h, (s-w)//2:(s-w)//2+w] = crop
    g = cv2.resize(sq, (HOGSZ, HOGSZ), interpolation=cv2.INTER_AREA)
    return _hog_compute(g)

def page_rows(page):
    gray = leaf_gray(page)
    toks = segment.tokens(gray, tess_cmd=TESS)
    chars = glyphs.page_chars(gray, tess_cmd=TESS)
    myr = {}; cur=None
    for t in toks:
        if t["is_heading"]: cur=t["rubric"]; myr[cur]=[]
        elif cur is not None: myr[cur].append(t)
    gold = {}
    for rn, items in parse_ref(GOLD % page):
        mk = match_rubric(rn, list(myr.keys()))
        for txt, rk in items: gold.setdefault((mk, nkey(txt)), rk)
    rows = []
    for rn, toklist in myr.items():
        for t in toklist:
            g = gold.get((rn, nkey(t["text"])))
            if g not in (2,3,4): continue
            box = segment.first_line_box(t["parts"]); pad=3
            crop = gray[max(0,box[1]-pad):box[3]+pad, max(0,box[0]-pad):box[2]+pad]
            feat = features.measure(crop)
            if not feat: continue
            # hires per-char hog vectors
            x0,y0,x1,y1 = box
            hogs = []
            for c in chars:
                cx=(c["x0"]+c["x1"])/2; cy=(c["y0"]+c["y1"])/2
                if x0<=cx<=x1 and y0<=cy<=y1 and re.match(r"^[a-z]$", c["ch"]):
                    hv = hog_glyph(gray, (c["x0"],c["y0"],c["x1"],c["y1"]))
                    if hv is not None: hogs.append(hv)
            rows.append(dict(gold=g, feat=feat, hogs=hogs))
    return rows

print("Extracting hires HOG glyphs for 8 gold pages (jp2)...")
DATA = {}
for p in PAGES:
    DATA[p] = page_rows(p)
    nh = sum(len(r["hogs"]) for r in DATA[p])
    print("  book p%d: %d tokens, %d glyph-HOGs" % (p, len(DATA[p]), nh))

def pnorm(rows):
    w=[r["feat"]["weight"] for r in rows if r["feat"]["slant"]<classify.SLANT_T]
    m=np.median(w); mad=np.median(np.abs(np.array(w)-m))*1.4826+1e-6; return m,mad

def vecs(rows, norm):
    X=[]; y=[]; tok=[]
    for ti,r in enumerate(rows):
        m,mad=norm; zw=(r["feat"]["weight"]-m)/mad
        extra=np.array([zw, r["feat"]["slant"]/20.0, abs(r["feat"]["slant"])/20.0])
        for hv in r["hogs"]:
            X.append(np.concatenate([hv, extra])); y.append(r["gold"]); tok.append(ti)
    return (np.array(X), np.array(y), tok)

norms={p:pnorm(DATA[p]) for p in PAGES}
print("\nLeave-one-page-out: hires-HOG MLP vs hand scalar")
tot=okH=okS=0
for test in PAGES:
    Xtr=[];ytr=[]
    for p in PAGES:
        if p==test: continue
        X,y,_=vecs(DATA[p],norms[p])
        if len(X): Xtr.append(X); ytr.append(y)
    Xtr=np.vstack(Xtr); ytr=np.concatenate(ytr)
    clf=MLPClassifier(hidden_layer_sizes=(256,64), max_iter=600, alpha=1e-3, random_state=0).fit(Xtr,ytr)
    up=[r["feat"]["weight"] for r in DATA[test] if r["feat"]["slant"]<classify.SLANT_T]
    wt=classify.otsu_split(up) or classify.WEIGHT_T
    Xte,yte,tok=vecs(DATA[test],norms[test])
    proba=clf.predict_proba(Xte); cls=clf.classes_
    agg={}
    for i,ti in enumerate(tok): agg.setdefault(ti,np.zeros(len(cls))); agg[ti]+=proba[i]
    n=h=s=0
    for ti,r in enumerate(DATA[test]):
        n+=1
        if ti in agg: predH=cls[int(np.argmax(agg[ti]))]
        else: predH=3 if r["feat"]["slant"]>=classify.SLANT_T else (4 if r["feat"]["weight"]>=wt else 2)
        predS=3 if r["feat"]["slant"]>=classify.SLANT_T else (4 if r["feat"]["weight"]>=wt else 2)
        h+=(predH==r["gold"]); s+=(predS==r["gold"])
    print("  book p%d  n=%3d  hires-HOG=%.1f%%  scalar=%.1f%%"%(test,n,100*h/n,100*s/n))
    tot+=n; okH+=h; okS+=s
print("\n  OVERALL  hires-HOG=%.1f%%  scalar=%.1f%%"%(100*okH/tot,100*okS/tot))
