# -*- coding: utf-8 -*-
"""CONSENSUS TIERING — split every vision-gold remedy token into
   Set A (100%-confident) vs Set B (doubtful), by cross-checking the vision
   grade against the three INDEPENDENT machine engines (scalar / mlp / shape)
   read off the actual print, plus an optional CSV doubt-flag layer.

Vision (bp0NN.md) is the candidate published grade; the machine engines and the
OpenRep CSV never SET a grade — they only CONFIRM (push to A) or cast DOUBT
(push to B). Strict rule: a Roman/Antique token reaches A only when all three
engines agree with vision, confidently, away from the page weight threshold.

Reuses compare_book's parsing/alignment. Standard library + json only (the
per-engine votes and features already live in out/book/pNNN.json).

Outputs under out/verify/:
  setA_confident.csv   one row per token that reached A
  setB_doubtful.csv    one row per doubtful token, with a `reasons` column
  SUMMARY.md           A/B counts, per-grade breakdown, reason histogram

Usage: python -m tpbocr.consensus [START] [END]   (default 17..483, graded range)
"""
import sys, os, re, json, csv, collections, argparse
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tpbocr import dict_correct as DC
from tpbocr.compare_book import nkey, parse_md, match_rubric

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OCR_OUT = os.path.join(ROOT, "..", "tpb-data", "public-domain", "books",
                       "07_Allen_1891_New_American_Edition_Boston", "ocr_out")
BOOK = os.path.join(ROOT, "out", "book")
OUTDIR = os.path.join(ROOT, "out", "verify")

# strict-tier knobs (tuned on the pilot; see SUMMARY.md)
WEIGHT_MARGIN = 0.015      # min |token_weight - page_threshold| for a confident Roman/Antique
MIN_CONF      = 0.80       # min pipeline confidence for a confident Roman/Antique
ITALIC_SLANT  = 6.0        # min |slant| (deg) for a confident Italic
GNAME = {5: "CAPITALS", 4: "Antique", 3: "Italic", 2: "Roman", 1: "paren"}


def machine_tokens(jp):
    """DEPRECATED (superseded by build_machine_page); kept for ad-hoc diagnostics.
    -> (weight_threshold, {rubric: {nkey: tokendict}}), headingless rubrics dropped."""
    d = json.load(open(jp, encoding="utf-8"))
    out = {}
    for ru in d["rubrics"]:
        if not ru["rubric"]:
            continue
        bucket = out.setdefault(ru["rubric"], {})
        for t in ru["remedies"]:
            bucket.setdefault(nkey(t["text"]), t)
    return d.get("weight_threshold"), out


# ---- alignment helpers (reduce the no-machine-match pile) -------------------
_RUNHEAD = re.compile(r"^\s*[A-Z][A-Z .']{0,18}?\.?\s*\d{1,3}\s*[-—–]+\s*")  # "MIND. 19 - "
_DROPTOK = re.compile(r"जारी|continued|book\s*p\.|…|\.\.\.|पर\b", re.I)


def clean_vision_items(items):
    """drop vision continuation-markers / non-remedy junk from (text, grade) list."""
    out = []
    for txt, g in items:
        if _DROPTOK.search(txt) or not re.search(r"[A-Za-z]", txt):
            continue
        out.append((txt, g))
    return out


def _edit_le2(a, b):
    """True if Levenshtein(a, b) <= 2 (cheap banded check)."""
    if a == b:
        return True
    la, lb = len(a), len(b)
    if abs(la - lb) > 2:
        return False
    prev = list(range(lb + 1))
    for i in range(1, la + 1):
        cur = [i] + [0] * lb
        lo, hi = max(1, i - 2), min(lb, i + 2)
        for j in range(1, lb + 1):
            if j < lo or j > hi:
                cur[j] = 9
                continue
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (a[i - 1] != b[j - 1]))
        prev = cur
    return prev[lb] <= 2


def build_machine_page(jp, vocab, vkeys):
    """-> (weight_threshold, [(name_or_None, {nkey: token})] in page order).
    Keeps HEADINGLESS rubrics (continuations), strips a running-head glued to the
    first token, and pre-snaps OCR text to the vision vocab via dict_correct."""
    d = json.load(open(jp, encoding="utf-8"))
    wthr = d.get("weight_threshold")
    rubs = []
    for ru in d["rubrics"]:
        toks = {}
        for i, t in enumerate(ru["remedies"]):
            txt = _RUNHEAD.sub("", t["text"]).strip() if i == 0 else t["text"]
            k = nkey(txt)
            if k:
                toks.setdefault(k, t)
            cor, _, _, unc = DC.correct(txt, vocab, vkeys)
            if not unc and nkey(cor) and nkey(cor) != k:
                toks.setdefault(nkey(cor), t)
        rubs.append((ru["rubric"], toks))
    return wthr, rubs


def match_rubric_overlap(name, vset, machine_rubs):
    """Pick the machine rubric for a vision rubric: largest remedy-set overlap
    (catches headingless continuations and garbled headings), falling back to
    name-prefix for tiny rubrics with weak overlap. Returns index or None."""
    best_i, best_ov = None, 0
    for i, (rn, toks) in enumerate(machine_rubs):
        ov = len(vset & set(toks))
        if ov > best_ov:
            best_ov, best_i = ov, i
    if best_i is not None and (best_ov >= 3 or best_ov >= 0.30 * max(1, len(vset))):
        return best_i
    hit = match_rubric(name, [rn for rn, _ in machine_rubs if rn])
    if hit:
        for i, (rn, _) in enumerate(machine_rubs):
            if rn == hit:
                return i
    return None



def tier_token(vr, mt, wthr):
    """Decide A vs B for one vision token (vr=vision grade) given its matched
    machine token mt and the page weight threshold. Returns (set, reasons[])."""
    if mt is None:
        return "B", ["no-machine-match"]
    s, m, h = mt.get("scalar_rank"), mt.get("mlp_rank"), mt.get("shape_rank")
    mf = mt.get("rank")
    conf = mt.get("confidence") or 0.0
    flag = bool(mt.get("flag"))
    feats = mt.get("features") or {}
    weight, slant = feats.get("weight"), feats.get("slant")
    reasons = []

    if vr == 5:                                   # CAPS — text-determined (~100%)
        if s == 5:
            return "A", ["caps-text"]
        reasons.append("vision-caps-machine=%s" % s)
    elif vr == 1:                                 # (parens) — text-determined
        if s == 1:
            return "A", ["paren-text"]
        reasons.append("vision-paren-machine=%s" % s)
    elif vr == 3:                                 # Italic — slant is unambiguous
        engines = [x for x in (s, m, h) if x is not None]
        if slant is not None and abs(slant) >= ITALIC_SLANT and 3 in engines and not flag:
            return "A", ["italic-slant"]
        reasons.append("weak-italic(slant=%s,eng=%s,flag=%s)" % (slant, engines, flag))
    elif vr in (2, 4):                            # Roman <-> Antique — the hard pair
        if s == vr and m == vr and h == vr and not flag:
            if weight is not None and wthr is not None and abs(weight - wthr) >= WEIGHT_MARGIN:
                if conf >= MIN_CONF:
                    return "A", ["rom-antq-unanimous"]
                reasons.append("low-conf(%.2f)" % conf)
            else:
                reasons.append("near-threshold(w=%s,thr=%s)" % (weight, wthr))
        else:
            reasons.append("engines-split(s=%s,m=%s,h=%s)" % (s, m, h))

    if mf is not None and mf != vr:
        reasons.append("vision!=machine(%s!=%s)" % (vr, mf))
    if not reasons:
        reasons.append("unclassified")
    return "B", reasons


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("start", nargs="?", type=int, default=17)
    ap.add_argument("end", nargs="?", type=int, default=483)
    ap.add_argument("--csv", action="store_true",
                    help="apply the OpenRep-CSV doubt-flag layer (tpbocr.csv_align)")
    a = ap.parse_args()
    os.makedirs(OUTDIR, exist_ok=True)
    vocab = DC.default_vocab(OCR_OUT); vkeys = list(vocab.keys())

    csv_conf = {}
    if a.csv:
        try:
            from tpbocr import csv_align
            csv_conf = csv_align.load_conflicts(a.start, a.end)
            print("csv doubt-flag layer: %d conflicting tokens loaded" % len(csv_conf))
        except Exception as e:
            print("csv layer unavailable (%s) -> skipping" % e)

    setA, setB = [], []
    by_grade = collections.Counter()          # grade -> [A,B]
    gradeA = collections.Counter(); gradeB = collections.Counter()
    reasons_hist = collections.Counter()
    csv_only_pushes = 0

    for bp in range(a.start, a.end + 1):
        vg = os.path.join(OCR_OUT, "therapeuticpocke0000timo_bp0%d.md" % bp)
        mj = os.path.join(BOOK, "p%03d.json" % bp)
        if not (os.path.exists(vg) and os.path.exists(mj)):
            continue
        vis = parse_md(vg)
        wthr, machine_rubs = build_machine_page(mj, vocab, vkeys)

        for rn, items in vis:
            items = clean_vision_items(items)
            vset = {nkey(txt) for txt, _ in items}
            mi = match_rubric_overlap(rn, vset, machine_rubs)
            mm = machine_rubs[mi][1] if mi is not None else {}
            mm_keys = list(mm.keys())
            seen = set()
            for txt, vr in items:
                k = nkey(txt)
                if not k or k in seen:
                    continue
                seen.add(k)
                mt = mm.get(k)
                if mt is None and mm_keys:                 # fuzzy within the paired rubric
                    for mk2 in mm_keys:
                        if _edit_le2(k, mk2):
                            mt = mm[mk2]; break
                tier, reasons = tier_token(vr, mt, wthr)
                # CSV doubt-flag: a token that would be A gets demoted to B
                ckey = (bp, nkey(rn), k)
                if tier == "A" and ckey in csv_conf:
                    tier = "B"; reasons = ["csv-conflict(%s)" % csv_conf[ckey]]
                    csv_only_pushes += 1
                row = {"page": bp, "rubric": rn, "remedy": txt,
                       "grade": vr, "grade_name": GNAME.get(vr, ""),
                       "scalar": (mt or {}).get("scalar_rank"),
                       "mlp": (mt or {}).get("mlp_rank"),
                       "shape": (mt or {}).get("shape_rank"),
                       "machine_final": (mt or {}).get("rank"),
                       "conf": (mt or {}).get("confidence"),
                       "bbox": json.dumps((mt or {}).get("bbox")),
                       "reasons": "; ".join(reasons)}
                if tier == "A":
                    setA.append(row); gradeA[vr] += 1
                else:
                    setB.append(row); gradeB[vr] += 1
                    for r in reasons:
                        reasons_hist[re.sub(r"\(.*\)", "", r)] += 1

    _write(setA, setB, gradeA, gradeB, reasons_hist, csv_only_pushes, a)


def _write(setA, setB, gradeA, gradeB, reasons_hist, csv_only_pushes, a):
    cols = ["page", "rubric", "remedy", "grade", "grade_name",
            "scalar", "mlp", "shape", "machine_final", "conf", "bbox", "reasons"]
    for name, rows in (("setA_confident.csv", setA), ("setB_doubtful.csv", setB)):
        with open(os.path.join(OUTDIR, name), "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=cols); w.writeheader()
            for r in rows:
                w.writerow(r)
    tot = len(setA) + len(setB)
    out = ["# Consensus tiering — Set A (confident) vs Set B (doubtful)\n",
           "pages %d..%d%s" % (a.start, a.end, "  [+CSV doubt-flag]" if a.csv else ""),
           "total tokens: %d | **Set A: %d (%.1f%%)** | Set B: %d (%.1f%%)" %
           (tot, len(setA), 100.0*len(setA)/max(1, tot), len(setB), 100.0*len(setB)/max(1, tot)),
           "" if not a.csv else "CSV alone demoted %d A->B\n" % csv_only_pushes,
           "## Per-grade (A / B)", "| grade | A | B | A% |", "|---|---|---|---|"]
    for g in (5, 4, 3, 2, 1):
        gt = gradeA[g] + gradeB[g]
        out.append("| %d %s | %d | %d | %.1f |" %
                   (g, GNAME[g], gradeA[g], gradeB[g], 100.0*gradeA[g]/max(1, gt)))
    out += ["\n## Set B reason histogram", "| reason | tokens |", "|---|---|"]
    for r, n in reasons_hist.most_common():
        out.append("| %s | %d |" % (r, n))
    open(os.path.join(OUTDIR, "SUMMARY.md"), "w", encoding="utf-8").write("\n".join(out))
    print("A=%d B=%d (A %.1f%%) -> %s" %
          (len(setA), len(setB), 100.0*len(setA)/max(1, tot), OUTDIR))


if __name__ == "__main__":
    main()
