# -*- coding: utf-8 -*-
"""Merge the Set-B re-vision answers back in. For every doubtful token that got
an INDEPENDENT second vision read (out/verify/revis_p<NN>*.json, written by a
vision agent reading montage_setb_*.png), compare the second grade with the
first-vision grade:

  second == first  -> PROMOTE to Set A  (two independent visions agree)
  second != first  -> Set C (residual)  -> the user certifies these
  (no answer yet)   -> stays in Set B

Rewrites out/verify/setA_confident.csv (+ promoted), setC_residual.csv, and
setB_doubtful.csv (remaining). Idempotent: re-run after each batch of answers.

Letter codes in revis json: C/c=5(CAPS) A=4(Antique) I=3(Italic) R=2(Roman) P=1(parens);
plain digits 1..5 also accepted. Value "skip"/"?" leaves the token in Set B.

Usage: python -m tpbocr.revision_merge
"""
import sys, os, csv, json, glob, collections
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VERIFY = os.path.join(ROOT, "out", "verify")
COLS = ["page", "rubric", "remedy", "grade", "grade_name", "scalar", "mlp",
        "shape", "machine_final", "conf", "bbox", "reasons"]
GNAME = {5: "CAPITALS", 4: "Antique", 3: "Italic", 2: "Roman", 1: "paren"}
LET = {"C": 5, "c": 5, "A": 4, "I": 3, "R": 2, "P": 1,
       "5": 5, "4": 4, "3": 3, "2": 2, "1": 1}


def _rows(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def _write(path, rows):
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=COLS); w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in COLS})


def load_answers():
    """-> {global_id: second_rank}. global_id = 'p<NN>#<id>' built from index+answers."""
    ans = {}
    for jf in glob.glob(os.path.join(VERIFY, "montage_setb_p*.json")):
        idx = json.load(open(jf, encoding="utf-8"))
        base = os.path.basename(jf)[:-5]                     # montage_setb_pNNN[_k]
        af = os.path.join(VERIFY, base.replace("montage_setb_", "revis_") + ".json")
        if not os.path.exists(af):
            # also accept a per-page answer file revis_pNNN.json (covers all parts)
            af = os.path.join(VERIFY, "revis_p%03d.json" % idx["page"])
            if not os.path.exists(af):
                continue
        raw = json.load(open(af, encoding="utf-8"))
        for it in idx["items"]:
            v = raw.get(str(it["id"]), raw.get(it["id"]))
            if v is None:
                continue
            rank = LET.get(str(v).strip())
            if rank:
                ans[(it["page"], it["rubric"], it["remedy"])] = (rank, it["first_grade"])
    return ans


def main():
    setA = _rows(os.path.join(VERIFY, "setA_confident.csv"))
    setB = _rows(os.path.join(VERIFY, "setB_doubtful.csv"))
    setC = _rows(os.path.join(VERIFY, "setC_residual.csv"))
    ans = load_answers()
    print("re-vision answers loaded: %d tokens" % len(ans))

    stay, promoted, residual = [], [], []
    for r in setB:
        key = (int(r["page"]), r["rubric"], r["remedy"])
        if key not in ans:
            stay.append(r); continue
        second, first = ans[key]
        if second == first:                              # two visions agree -> A
            r = dict(r); r["reasons"] = "revision-confirmed(v1=v2=%d)" % second
            promoted.append(r)
        else:                                            # disagree -> user certifies
            r = dict(r)
            r["reasons"] = "revision-disagree(v1=%d,v2=%d)" % (first, second)
            r["second_grade"] = second
            residual.append(r)

    setA += promoted
    # merge new residuals with any existing Set C (dedupe by page+rubric+remedy)
    seen = {(c["page"], c["rubric"], c["remedy"]) for c in setC}
    for r in residual:
        k = (r["page"], r["rubric"], r["remedy"])
        if k not in seen:
            setC.append(r); seen.add(k)

    _write(os.path.join(VERIFY, "setA_confident.csv"), setA)
    _write(os.path.join(VERIFY, "setB_doubtful.csv"), stay)
    _write(os.path.join(VERIFY, "setC_residual.csv"), setC)
    tot = len(setA) + len(stay) + len(setC)
    print("promoted B->A: %d | residual B->C: %d | still B: %d" %
          (len(promoted), len(residual), len(stay)))
    print("now: A=%d (%.1f%%)  B=%d  C=%d  total=%d" %
          (len(setA), 100.0*len(setA)/max(1, tot), len(stay), len(setC), tot))


if __name__ == "__main__":
    main()
