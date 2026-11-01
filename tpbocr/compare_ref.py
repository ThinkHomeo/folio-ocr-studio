# -*- coding: utf-8 -*-
"""Compare my pipeline JSON vs a hand-transcribed reference .md (rank-marked).
Reports, per rubric: matched tokens, rank agreements/disagreements, and tokens
present in only one side; and how many rubrics differ at all."""
import sys, os, re, json
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

def nkey(s):
    s = s.lower()
    s = re.sub(r"[^a-z0-9]", "", s)
    return s

def parse_ref(path):
    rub = {}
    for line in open(path, encoding="utf-8"):
        m = re.match(r"\*\*(.+?)\.\*\*\s*[—-]+\s*(.*)", line.strip())
        if not m:
            continue
        name = m.group(1).strip()
        body = m.group(2)
        toks = [t.strip() for t in body.split(",") if t.strip()]
        items = []
        for t in toks:
            rank = tok_rank(t)
            txt = re.sub(r"[*()]|\*\*", "", t).strip()
            items.append((txt, rank))
        rub[name] = items
    return rub

def tok_rank(t):
    t = t.strip()
    if t.startswith("(") and t.endswith(")"):
        return 1
    if t.startswith("**") and t.endswith("**"):
        return 4
    if t.startswith("*") and t.endswith("*"):
        return 3
    core = re.sub(r"[*()]", "", t)
    letters = [c for c in core if c.isalpha()]
    if letters and all(c.isupper() for c in letters):
        return 5
    return 2

def parse_mine(path):
    d = json.load(open(path, encoding="utf-8"))
    rub = {}
    for ru in d["rubrics"]:
        if not ru["rubric"]:
            continue
        rub[ru["rubric"]] = [(r["text"], r["rank"]) for r in ru["remedies"]]
    return rub, d.get("weight_threshold")

def match_rubric(ref_name, mine_keys):
    rk = nkey(ref_name)
    best = None
    for mk in mine_keys:
        if nkey(mk).startswith(rk[:6]) or rk.startswith(nkey(mk)[:6]):
            best = mk; break
    return best

ref = parse_ref(sys.argv[1])
mine, wt = parse_mine(sys.argv[2])
print("my weight_threshold:", wt)
print("reference rubrics: %d | my rubrics: %d\n" % (len(ref), len(mine)))

rub_diff = 0
tot_match = tot_rank_ok = tot_rank_bad = tot_only_ref = tot_only_mine = 0
for rname, ritems in ref.items():
    mname = match_rubric(rname, list(mine.keys()))
    mitems = mine.get(mname, []) if mname else []
    rmap = {}
    for txt, rk in ritems:
        rmap.setdefault(nkey(txt), (txt, rk))
    mmap = {}
    for txt, rk in mitems:
        mmap.setdefault(nkey(txt), (txt, rk))
    keys = set(rmap) | set(mmap)
    rank_ok = rank_bad = only_ref = only_mine = 0
    bad_list = []
    for k in keys:
        if k in rmap and k in mmap:
            if rmap[k][1] == mmap[k][1]:
                rank_ok += 1
            else:
                rank_bad += 1
                bad_list.append("%s ref=%d mine=%d" % (rmap[k][0], rmap[k][1], mmap[k][1]))
        elif k in rmap:
            only_ref += 1
        else:
            only_mine += 1
    differs = (rank_bad or only_ref or only_mine)
    if differs:
        rub_diff += 1
    tot_match += rank_ok + rank_bad
    tot_rank_ok += rank_ok; tot_rank_bad += rank_bad
    tot_only_ref += only_ref; tot_only_mine += only_mine
    print("### %s  (ref %d / mine %d tokens)%s" % (
        rname, len(ritems), len(mitems), "   <-- MATCHES" if not differs else ""))
    print("   matched=%d  rank-agree=%d  rank-DISAGREE=%d  only-in-ref=%d  only-in-mine=%d"
          % (rank_ok + rank_bad, rank_ok, rank_bad, only_ref, only_mine))
    if bad_list:
        print("   rank mismatches: " + "; ".join(bad_list))
    print()

print("=" * 60)
print("RUBRICS THAT DIFFER: %d of %d" % (rub_diff, len(ref)))
print("token rank-agreements: %d  disagreements: %d  (of %d matched)"
      % (tot_rank_ok, tot_rank_bad, tot_match))
print("only-in-reference (I missed/misspelled): %d" % tot_only_ref)
print("only-in-mine (extra/misspelled): %d" % tot_only_mine)
if tot_match:
    print("rank accuracy on matched tokens: %.1f%%" % (100.0*tot_rank_ok/tot_match))
