# -*- coding: utf-8 -*-
"""VISION-ERROR audit queue — rank the tokens where the machine's INDEPENDENT
typeface reading contradicts the vision gold, so the user can verify likely
vision slips first.

Vision is authoritative, but it can slip. The machine's independent engines read
the actual print, not vision's answers:
  * scalar  — pure per-page weight/slant measurement (never sees vision labels)
  * shape   — glyph-prototype matcher (bootstrap/limited-gold; vision-light)
  * mlp     — the trained net; after the whole-book retrain it largely PARROTS
              vision, so it is the weakest auditor — used only as a tie-breaker.
A token where scalar AND shape agree with each other but DISAGREE with vision,
with a strong signal (weight far from the page's Antique/Roman threshold, or a
clear italic slant), is a strong candidate that VISION is wrong there.

Most machine-vs-vision disagreements are MACHINE errors (machine ~85-90% on the
hard Roman/Antique pair), so the queue is TIERED and ranked to surface the
genuine vision slips at the top; plain machine noise sinks to the bottom.

Outputs out/book/vision_audit_queue.csv  (+ a short summary).
Usage: python -m tpbocr.vision_audit [START] [END]
"""
import sys, os, re, json, csv, collections
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tpbocr import dict_correct as DC, classify

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OCR_OUT = os.path.join(ROOT, "..", "tpb-data", "public-domain", "books",
                       "07_Allen_1891_New_American_Edition_Boston", "ocr_out")
BOOK = os.path.join(ROOT, "out", "book")
DS = os.path.join(ROOT, "out", "dataset")
GN = {5: "CAPITALS", 4: "Antique", 3: "Italic", 2: "Roman", 1: "paren"}


def nkey(s):
    return re.sub(r"[^a-z0-9]", "", s.lower())


def tok_rank(t):
    t = t.strip()
    if t.startswith("(") and t.endswith(")"):
        return 1
    if t.startswith("**") and t.endswith("**"):
        return 4
    if t.startswith("*") and t.endswith("*"):
        return 3
    core = re.sub(r"[*()]", "", t); L = [c for c in core if c.isalpha()]
    return 5 if (L and all(c.isupper() for c in L)) else 2


def parse_md(p):
    rub = []
    for line in open(p, encoding="utf-8"):
        m = re.match(r"\*\*(.+?)\.\*\*\s*[—-]+\s*(.*)", line.strip())
        if m:
            rub.append((m.group(1).strip(),
                        [(re.sub(r"[*()?]|\*\*", "", t).strip(), tok_rank(t))
                         for t in m.group(2).split(",") if t.strip()]))
    return rub


def match_rubric(rn, keys):
    rk = nkey(rn)
    for k in keys:
        if nkey(k)[:6] == rk[:6] or nkey(k).startswith(rk[:5]) or rk.startswith(nkey(k)[:5]):
            return k


def score_candidate(vg, s, sh, m, wdist, slant):
    """Return (score, independent_votes) for a vision/machine disagreement.
    score>0 only when the INDEPENDENT engines (scalar, shape) form a consensus
    AGAINST vision; higher = the machine's reading is more unambiguous, so the
    stronger the suspicion that VISION slipped. mlp is NOT part of the gate
    (after the whole-book retrain it parrots vision)."""
    indep = [v for v in (s, sh) if v is not None]
    if not indep:
        return 0.0, 0
    consensus = s if (s is not None and s == sh) else None
    if consensus is None or consensus == vg:
        # allow a lone strong independent engine too
        if len(indep) == 1 and indep[0] != vg:
            consensus = indep[0]
        else:
            return 0.0, 0
    if consensus == vg:
        return 0.0, 0
    # involves italic? slant is a clean, reliable discriminator -> high base score
    if 3 in (vg, consensus):
        base = 0.6 + min(abs(slant) / 20.0, 0.6)
    else:                                   # Roman<->Antique: weight clarity
        base = wdist
    if s == sh == m:                        # even the vision-trained net agrees
        base += 0.15
    return round(base, 3), len(indep)


def main():
    start = int(sys.argv[1]) if len(sys.argv) > 1 else 17
    end = int(sys.argv[2]) if len(sys.argv) > 2 else 495
    vocab = DC.default_vocab(OCR_OUT); vkeys = list(vocab.keys())
    out = []
    for bp in range(start, end + 1):
        vg_path = os.path.join(OCR_OUT, "therapeuticpocke0000timo_bp0%d.md" % bp)
        mj = os.path.join(BOOK, "p%03d.json" % bp)
        if not (os.path.exists(vg_path) and os.path.exists(mj)):
            continue
        vis = parse_md(vg_path)
        d = json.load(open(mj, encoding="utf-8"))
        thr = d.get("weight_threshold") or classify.WEIGHT_T
        mac = [(ru["rubric"], ru["remedies"]) for ru in d["rubrics"] if ru["rubric"]]
        mkeys = [r[0] for r in mac]
        mdict = {}
        for rn, rems in mac:
            dd = mdict.setdefault(rn, {})
            for r in rems:
                rec = (r.get("rank"), r.get("scalar_rank"), r.get("mlp_rank"),
                       r.get("shape_rank"), (r.get("features") or {}), bool(r.get("flag")),
                       r.get("confidence"))
                dd.setdefault(nkey(r["text"]), rec)
                cor, _, _, unc = DC.correct(r["text"], vocab, vkeys)
                if not unc and nkey(cor) != nkey(r["text"]):
                    dd.setdefault(nkey(cor), rec)
        for rn, items in vis:
            mk = match_rubric(rn, mkeys)
            mm = mdict.get(mk, {})
            for txt, vgrade in items:
                if vgrade not in (2, 3, 4):
                    continue
                rec = mm.get(nkey(txt))
                if not rec:
                    continue
                rank, s, m, sh, f, flag, conf = rec
                w = f.get("weight"); slant = f.get("slant") or 0.0
                wdist = abs(w - thr) / thr if (w and thr) else 0.0
                sc, nind = score_candidate(vgrade, s, sh, m, wdist, slant)
                if sc <= 0:
                    continue
                cons = s if (s is not None and s == sh) else (
                    s if s is not None else sh)
                out.append(dict(score=sc, page=bp, rubric=rn, remedy=txt,
                                vision=GN[vgrade], machine_reads=GN.get(cons, ""),
                                scalar=GN.get(s, ""), shape=GN.get(sh, ""), mlp=GN.get(m, ""),
                                weight=round(w, 4) if w else "", threshold=round(thr, 4),
                                weight_dist=round(wdist, 3), slant=round(slant, 1)))

    # structural vision slips (glued / unbalanced parens) = definite re-read
    definite = []
    rp = os.path.join(DS, "tpb_vision_rows.json")
    if os.path.exists(rp):
        for r in json.load(open(rp, encoding="utf-8"))["rows"]:
            if r.get("review"):
                definite.append(dict(tier="definite", score="", page=r["page"], rubric=r["rubric"],
                                     remedy=r["remedy"], vision=GN[int(r["grade"])],
                                     machine_reads="", scalar="", shape="", mlp="", weight="",
                                     threshold="", weight_dist="", slant="", note=r["review"]))

    out.sort(key=lambda r: -r["score"])
    # priority tiers by rank within the independent-consensus candidates
    for i, r in enumerate(out):
        r["tier"] = "P1-review-first" if i < 200 else ("P2" if i < 800 else "P3")
    allrows = definite + out

    cols = ["tier", "score", "page", "rubric", "remedy", "vision", "machine_reads",
            "scalar", "shape", "mlp", "weight", "threshold", "weight_dist", "slant", "note"]
    os.makedirs(BOOK, exist_ok=True)
    with open(os.path.join(BOOK, "vision_audit_queue.csv"), "w", newline="", encoding="utf-8-sig") as fp:
        w = csv.DictWriter(fp, fieldnames=cols, extrasaction="ignore")
        w.writeheader(); w.writerows(allrows)

    cnt = collections.Counter(r["tier"] for r in allrows)
    print("vision-audit queue -> out/book/vision_audit_queue.csv")
    for t in ("definite", "P1-review-first", "P2", "P3"):
        print("  %-16s %d" % (t, cnt.get(t, 0)))
    print("  TOTAL           %d" % len(allrows))


if __name__ == "__main__":
    main()
