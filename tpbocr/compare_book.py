# -*- coding: utf-8 -*-
"""Book-wide MACHINE vs VISION comparison.

For every book page where both exist — vision gold ocr_out/..._bp0NN.md and
machine out/book/pNNN.json — align remedy tokens (by rubric + normalised name)
and compare the typographic RANK. Emits a per-page table + aggregate accuracy +
a 5x5 confusion matrix + the systematic error breakdown, to out/book/COMPARISON.md.

Usage: python -m tpbocr.compare_book [START] [END]   (default 17..495)
"""
import sys, os, re, json, glob, collections
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tpbocr import dict_correct as DC
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OCR_OUT = os.path.join(ROOT, "..", "tpb-data", "public-domain", "books",
                       "07_Allen_1891_New_American_Edition_Boston", "ocr_out")
BOOK = os.path.join(ROOT, "out", "book")

def nkey(s): return re.sub(r"[^a-z0-9]", "", s.lower())
def tok_rank(t):
    t = t.strip()
    if t.startswith("(") and t.endswith(")"): return 1
    if t.startswith("**") and t.endswith("**"): return 4
    if t.startswith("*") and t.endswith("*"): return 3
    c = re.sub(r"[*()]", "", t); L = [x for x in c if x.isalpha()]
    return 5 if (L and all(x.isupper() for x in L)) else 2
def parse_md(p):
    rub = []
    for line in open(p, encoding="utf-8"):
        m = re.match(r"\*\*(.+?)\.\*\*\s*[—-]+\s*(.*)", line.strip())
        if m: rub.append((m.group(1).strip(),
            [(re.sub(r"[*()?]|\*\*","",t).strip(), tok_rank(t)) for t in m.group(2).split(",") if t.strip()]))
    return rub
def machine_rubrics(jp):
    d = json.load(open(jp, encoding="utf-8"))
    return [(ru["rubric"], [(r["text"], r["rank"], r.get("confidence"), bool(r.get("flag")))
                            for r in ru["remedies"]])
            for ru in d["rubrics"] if ru["rubric"]]
def match_rubric(rn, keys):
    rk = nkey(rn)
    for k in keys:
        if nkey(k)[:6]==rk[:6] or nkey(k).startswith(rk[:5]) or rk.startswith(nkey(k)[:5]): return k

def main():
    start = int(sys.argv[1]) if len(sys.argv) > 1 else 17
    end = int(sys.argv[2]) if len(sys.argv) > 2 else 495
    vocab = DC.default_vocab(OCR_OUT); vkeys = list(vocab.keys())
    rows = []
    disagree = []        # (page, rubric, remedy, vgrade, mgrade, mconf, mflag)
    cm = {a: collections.Counter() for a in (1,2,3,4,5)}
    tot = agree = only_v = only_m = 0
    for bp in range(start, end + 1):
        vg = os.path.join(OCR_OUT, "therapeuticpocke0000timo_bp0%d.md" % bp)
        mj = os.path.join(BOOK, "p%03d.json" % bp)
        if not (os.path.exists(vg) and os.path.exists(mj)):
            continue
        vis = parse_md(vg); mac = machine_rubrics(mj)
        mkeys = [r[0] for r in mac]
        mdict = {k: dict() for k in mkeys}
        for rn, items in mac:
            for txt, rk, conf, flag in items:
                mdict[rn].setdefault(nkey(txt), (rk, conf, flag))
                cor, _, _, unc = DC.correct(txt, vocab, vkeys)   # snap OCR text
                if not unc and nkey(cor) != nkey(txt):
                    mdict[rn].setdefault(nkey(cor), (rk, conf, flag))
        pt = pa = 0
        for rn, items in vis:
            mk = match_rubric(rn, mkeys)
            mm = mdict.get(mk, {})
            vmap = {}
            for txt, rk in items: vmap.setdefault(nkey(txt), (rk, txt))
            for k, (vr, vtxt) in vmap.items():
                if k in mm:
                    mr, mconf, mflag = mm[k]; tot += 1; pt += 1
                    cm[vr][mr] += 1
                    if vr == mr:
                        agree += 1; pa += 1
                    else:
                        disagree.append((bp, rn, vtxt, vr, mr, mconf, mflag))
                else:
                    only_v += 1
            for k in mm:
                if k not in vmap: only_m += 1
        if pt: rows.append((bp, pt, 100.0*pa/pt))
    # report
    os.makedirs(BOOK, exist_ok=True)
    out = []
    out.append("# Machine vs Vision — book-wide comparison\n")
    out.append("pages compared: %d | matched tokens: %d | **overall rank agreement: %.1f%%**"
               % (len(rows), tot, 100.0*agree/max(1,tot)))
    out.append("only-in-vision (machine missed/misspelled): %d | only-in-machine: %d\n" % (only_v, only_m))
    out.append("## Confusion matrix — vision(row) x machine(col)")
    out.append("| v\\m | 5 CAPS | 4 Antq | 3 Ital | 2 Rom | 1 () |")
    out.append("|---|---|---|---|---|---|")
    for a in (5,4,3,2,1):
        out.append("| **%d** | %d | %d | %d | %d | %d |" % (a, cm[a][5],cm[a][4],cm[a][3],cm[a][2],cm[a][1]))
    # worst pages
    worst = sorted(rows, key=lambda r: r[2])[:15]
    out.append("\n## 15 lowest-agreement pages")
    out.append("| page | tokens | agree% |")
    out.append("|---|---|---|")
    for bp, n, ac in worst: out.append("| %d | %d | %.1f |" % (bp, n, ac))
    rep = os.path.join(BOOK, "COMPARISON.md")
    open(rep, "w", encoding="utf-8").write("\n".join(out))

    # per-token disagreements + the confident-machine QA review queue (machine
    # disagrees with vision AND is not self-flagged -> candidate vision slip)
    import csv
    with open(os.path.join(BOOK, "disagreements.csv"), "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["page", "rubric", "remedy", "vision_grade", "machine_grade",
                    "machine_conf", "machine_flag"])
        for d in disagree:
            w.writerow(d)
    qa = [d for d in disagree if (not d[6]) and (d[5] or 0) >= 0.60
          and d[3] in (2, 3, 4) and d[4] in (2, 3, 4)]   # typeface-face slips only
    qa.sort(key=lambda d: -(d[5] or 0))
    with open(os.path.join(BOOK, "qa_review_queue.csv"), "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["page", "rubric", "remedy", "vision_grade", "machine_grade", "machine_conf"])
        for d in qa:
            w.writerow([d[0], d[1], d[2], d[3], d[4], d[5]])

    print("pages=%d matched=%d agreement=%.1f%% only_v=%d only_m=%d  disagree=%d qa_queue=%d -> %s"
          % (len(rows), tot, 100.0*agree/max(1,tot), only_v, only_m,
             len(disagree), len(qa), rep))

if __name__ == "__main__":
    main()
