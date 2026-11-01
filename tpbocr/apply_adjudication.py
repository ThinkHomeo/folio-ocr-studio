# -*- coding: utf-8 -*-
"""Merge vision adjudications back into a page's machine OCR JSON.

Takes montage_<tag>.json (what was sent) + the vision answers (id -> face),
overrides those tokens' rank with the vision verdict, marks them adjudicated
(confidence 1.0, flag cleared). Answers come from a real vision pass over the
montage PNG; --from-gold simulates a perfect pass to test the plumbing.

Usage:
  python -m tpbocr.apply_adjudication p024 --answers ans.json
  python -m tpbocr.apply_adjudication p024 --from-gold <bp024.md>   # test
"""
import sys, os, re, json, argparse

FACEMAP = {"R":2,"A":4,"I":3,"C":5,"P":1, "2":2,"3":3,"4":4,"5":5,"1":1,
           2:2,3:3,4:4,5:5,1:1}

def nkey(s): return re.sub(r"[^a-z0-9]", "", s.lower())
def tok_rank(t):
    t = t.strip()
    if t.startswith("(") and t.endswith(")"): return 1
    if t.startswith("**") and t.endswith("**"): return 4
    if t.startswith("*") and t.endswith("*"): return 3
    c = re.sub(r"[*()]", "", t); L = [x for x in c if x.isalpha()]
    return 5 if (L and all(x.isupper() for x in L)) else 2

def gold_map(md):
    g = {}
    for line in open(md, encoding="utf-8"):
        m = re.match(r"\*\*(.+?)\.\*\*\s*[—-]+\s*(.*)", line.strip())
        if not m: continue
        rub = m.group(1).strip()
        for t in m.group(2).split(","):
            s = re.sub(r"[*()]|\*\*", "", t).strip()
            if s: g.setdefault((rub, nkey(s)), tok_rank(t))
    return g

def match_rubric(rn, keys):
    rk = nkey(rn)
    for k in keys:
        if nkey(k)[:6]==rk[:6] or nkey(k).startswith(rk[:5]) or rk.startswith(nkey(k)[:5]): return k

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("tag"); ap.add_argument("--out", default="out")
    ap.add_argument("--answers", default=None, help="JSON {id: 'R'/'A'/'I' or 2/3/4}")
    ap.add_argument("--from-gold", default=None, help="simulate perfect vision from a gold .md")
    a = ap.parse_args()
    idx = json.load(open(os.path.join(a.out, "montage_%s.json" % a.tag), encoding="utf-8"))
    doc = json.load(open(os.path.join(a.out, a.tag + "_webp.json"), encoding="utf-8"))

    answers = {}
    if a.answers:
        raw = json.load(open(a.answers, encoding="utf-8"))
        for k, v in raw.items():
            if v in FACEMAP:            # 'skip'/unknown -> leave token, stays flagged
                answers[int(k)] = FACEMAP[v]
    elif a.from_gold:
        gm = gold_map(a.from_gold)
        myrubs = [ru["rubric"] for ru in doc["rubrics"] if ru["rubric"]]
        for it in idx["items"]:
            mk = match_rubric(it["rubric"], myrubs) if it["rubric"] else None
            g = gm.get((it["rubric"], nkey(it["text"]))) or gm.get((mk, nkey(it["text"])))
            if g in (2,3,4): answers[it["id"]] = g
    else:
        raise SystemExit("provide --answers or --from-gold")

    # id -> montage item (has bbox)
    byid = {it["id"]: it for it in idx["items"]}
    applied = 0
    for ru in doc["rubrics"]:
        for rem in ru["remedies"]:
            for i, it in byid.items():
                if i in answers and it["bbox"] == rem["bbox"] and nkey(it["text"]) == nkey(rem["text"]):
                    rem["rank"] = answers[i]; rem["rank_name_src"] = "vision"
                    rem["adjudicated"] = True; rem["flag"] = False
                    rem["confidence"] = 1.0
                    applied += 1
                    break
    json.dump(doc, open(os.path.join(a.out, a.tag + "_webp.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("%s: applied %d vision adjudications (of %d sent)" % (a.tag, applied, idx["count"]))

if __name__ == "__main__":
    main()
