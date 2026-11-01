# -*- coding: utf-8 -*-
"""Set-C consensus auto-resolution (makes the user's job ~16x smaller).

Every Set C token has three independent signals: first-vision (v1 = the row's
grade), second-vision (v2, from the revision), and the machine engine-majority
(scalar/mlp/shape). In Set C v1 != v2 by construction, so the engine is the swing
vote: wherever engine-majority agrees with v1 OR v2, 2-of-3 signals concur →
auto-resolve to that grade and promote to Set A. Only the genuine 3-way splits
(v1, v2, engine all differ) stay in Set C for the user.

Also writes a reproducible random audit sample of the auto-resolved rows so the
user can spot-check the rule's accuracy before trusting the bulk.

Usage: python -m tpbocr.resolve_consensus [--sample 150]
"""
import sys, os, csv, re, random, collections, argparse
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VERIFY = os.path.join(ROOT, "out", "verify")
COLS = ["page", "rubric", "remedy", "grade", "grade_name", "scalar", "mlp",
        "shape", "machine_final", "conf", "bbox", "reasons"]
GNAME = {5: "CAPITALS", 4: "Antique", 3: "Italic", 2: "Roman", 1: "paren"}


def _rows(p):
    if not os.path.exists(p):
        return []
    with open(p, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def _write(p, rows):
    with open(p, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=COLS, extrasaction="ignore"); w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in COLS})


def emaj(r):
    v = [int(x) for x in (r.get("scalar"), r.get("mlp"), r.get("shape"))
         if x not in ("", "None", None)]
    return collections.Counter(v).most_common(1)[0][0] if v else None


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--sample", type=int, default=150)
    a = ap.parse_args()
    A = _rows(os.path.join(VERIFY, "setA_confident.csv"))
    C = _rows(os.path.join(VERIFY, "setC_residual.csv"))
    resolved, ties = [], []
    for r in C:
        m = re.search(r"v1=(\d),v2=(\d)", r["reasons"])
        if not m:
            ties.append(r); continue
        v1, v2 = int(m.group(1)), int(m.group(2))
        em = emaj(r)
        if em == v2 or em == v1:                       # 2-of-3 agree -> majority
            final = em
            r = dict(r)
            r["grade"] = final; r["grade_name"] = GNAME.get(final, "")
            r["reasons"] = "consensus-2of3(v1=%d,v2=%d,eng=%d->%d)" % (v1, v2, em, final)
            resolved.append(r)
        else:                                          # 3-way split -> user
            ties.append(r)
    A2 = A + resolved
    _write(os.path.join(VERIFY, "setA_confident.csv"), A2)
    _write(os.path.join(VERIFY, "setC_residual.csv"), ties)
    # reproducible audit sample of the auto-resolved
    random.seed(1891)
    sample = random.sample(resolved, min(a.sample, len(resolved)))
    _write(os.path.join(VERIFY, "setC_audit_sample.csv"), sample)
    tot = len(A2) + len(ties)
    took_v2 = sum(1 for r in resolved if "->%d)" % int(re.search(r"v2=(\d)", r["reasons"]).group(1)) in r["reasons"])
    print("auto-resolved: %d  (stay as ties for user: %d)" % (len(resolved), len(ties)))
    print("  of resolved, took 2nd-vision over 1st: %d" % took_v2)
    print("now: Set A %d (%.1f%%) | Set C ties %d | audit sample %d" %
          (len(A2), 100.0 * len(A2) / max(1, tot), len(ties), len(sample)))


if __name__ == "__main__":
    main()
