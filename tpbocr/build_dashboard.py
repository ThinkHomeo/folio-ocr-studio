# -*- coding: utf-8 -*-
"""Build a self-contained HTML dashboard visualising the TPB grader:
page image + colour-coded token overlays, gold comparison (errors ringed),
per-page accuracy, confusion matrix, and error breakdowns. One openable file."""
import sys, os, re, json, base64
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import numpy as np, cv2
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
B = os.path.join(ROOT, "..", "tpb-data", "public-domain", "books",
                 "07_Allen_1891_New_American_Edition_Boston", "ocr_out")
PAGES = [("p0%d" % bp, str(bp), "bp0%d" % bp) for bp in range(17, 31)]

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

def match_rubric(rn, keys):
    rk = nkey(rn)
    for mk in keys:
        if nkey(mk)[:6] == rk[:6] or nkey(mk).startswith(rk[:5]) or rk.startswith(nkey(mk)[:5]):
            return mk
    return None

def b64(path):
    ext = os.path.splitext(path)[1].lstrip(".").lower()
    mime = {"webp":"image/webp","jpg":"image/jpeg","jpeg":"image/jpeg","png":"image/png"}[ext]
    return "data:%s;base64,%s" % (mime, base64.b64encode(open(path,"rb").read()).decode())

def build_page(tag, bookno, refcode):
    doc = json.load(open(os.path.join(HERE, "..", "out", tag + "_webp.json"), encoding="utf-8"))
    scale = doc.get("scale", 2)
    refpath = os.path.join(B, "therapeuticpocke0000timo_%s.md" % refcode)
    goldmap = {}
    if os.path.exists(refpath):          # pages without vision gold yet: no comparison
        ref = parse_ref(refpath)
        myrubs = [r["rubric"] for r in doc["rubrics"] if r["rubric"]]
        for rn, items in ref:
            mk = match_rubric(rn, myrubs)
            for txt, rk in items:
                goldmap.setdefault((mk, nkey(txt)), rk)
    toks = []
    for ru in doc["rubrics"]:
        for rem in ru["remedies"]:
            g = goldmap.get((ru["rubric"], nkey(rem["text"])))
            f = rem.get("features") or {}
            bb = [round(v/scale, 1) for v in rem["bbox"]]
            toks.append(dict(text=rem["text"], rubric=ru["rubric"],
                             rank=rem["rank"], gold=g, conf=rem["confidence"],
                             scalar=rem.get("scalar_rank"), mlp=rem.get("mlp_rank"),
                             shape=rem.get("shape_rank"), flag=bool(rem.get("flag")),
                             adj=bool(rem.get("adjudicated")),
                             weight=f.get("weight"), slant=f.get("slant"),
                             bbox=bb,
                             ok=(None if g is None else (g == rem["rank"]))))
    img = b64(os.path.join(HERE, "..", "input", tag + ".webp"))
    im = cv2.imdecode(np.fromfile(os.path.join(HERE,"..","input",tag+".webp"),np.uint8), cv2.IMREAD_GRAYSCALE)
    H, W = im.shape
    return dict(tag=tag, book=bookno, image=img, w=W, h=H,
                weight_threshold=doc.get("weight_threshold"), tokens=toks)

data = {"pages": [build_page(*p) for p in PAGES]}
data_text = json.dumps(data, ensure_ascii=False)
OUT = os.path.join(HERE, "..", "out")
with open(os.path.join(OUT, "_dashboard_data.json"), "w", encoding="utf-8") as f:
    f.write(data_text)

# assemble the single-file dashboard: template with the data + js inlined
tpl = open(os.path.join(HERE, "dashboard_template.html"), encoding="utf-8").read()
js = open(os.path.join(HERE, "dashboard.js"), encoding="utf-8").read()
html = tpl.replace("__DATA__", data_text).replace("__JS__", js)
with open(os.path.join(OUT, "dashboard.html"), "w", encoding="utf-8") as f:
    f.write(html)

print("pages:", len(data["pages"]),
      "tokens:", sum(len(p["tokens"]) for p in data["pages"]),
      "-> out/dashboard.html")
