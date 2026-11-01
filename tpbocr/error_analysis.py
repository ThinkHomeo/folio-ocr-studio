# -*- coding: utf-8 -*-
"""Error analysis across pages: which tokens/letters does the classifier miss?
Aligns my JSON vs the gold .md by remedy name, collects every rank mismatch,
and aggregates by confusion type, leading letter, token length, and letter set."""
import sys, os, re, json, collections
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

def nkey(s):
    return re.sub(r"[^a-z0-9]", "", s.lower())

def tok_rank(t):
    t = t.strip()
    if t.startswith("(") and t.endswith(")"): return 1
    if t.startswith("**") and t.endswith("**"): return 4
    if t.startswith("*") and t.endswith("*"): return 3
    core = re.sub(r"[*()]", "", t)
    L = [c for c in core if c.isalpha()]
    if L and all(c.isupper() for c in L): return 5
    return 2

def parse_ref(path):
    rub = {}
    for line in open(path, encoding="utf-8"):
        m = re.match(r"\*\*(.+?)\.\*\*\s*[—-]+\s*(.*)", line.strip())
        if not m: continue
        items = []
        for t in m.group(2).split(","):
            t = t.strip()
            if not t: continue
            txt = re.sub(r"[*()]|\*\*", "", t).strip()
            items.append((txt, tok_rank(t)))
        rub[m.group(1).strip()] = items
    return rub

def parse_mine(path):
    d = json.load(open(path, encoding="utf-8"))
    rub = {}
    for ru in d["rubrics"]:
        if ru["rubric"]:
            rub[ru["rubric"]] = [(r["text"], r["rank"], r.get("features")) for r in ru["remedies"]]
    return rub

def match_rubric(rn, keys):
    rk = nkey(rn)
    for mk in keys:
        if nkey(mk)[:6] == rk[:6] or nkey(mk).startswith(rk[:5]) or rk.startswith(nkey(mk)[:5]):
            return mk
    return None

pairs = sys.argv[1:]  # ref.md mine.json ref.md mine.json ...
mism = []
conf = collections.Counter()
for i in range(0, len(pairs), 2):
    ref = parse_ref(pairs[i]); mine = parse_mine(pairs[i+1])
    for rn, ritems in ref.items():
        mn = match_rubric(rn, list(mine.keys()))
        mitems = mine.get(mn, []) if mn else []
        rmap = {};
        for txt, rk in ritems: rmap.setdefault(nkey(txt), (txt, rk))
        mmap = {}
        for txt, rk, f in mitems: mmap.setdefault(nkey(txt), (txt, rk, f))
        for k in set(rmap) & set(mmap):
            gtxt, grank = rmap[k]; mtxt, mrank, f = mmap[k]
            if grank != mrank:
                mism.append((gtxt, grank, mrank, f))
                conf[(grank, mrank)] += 1

print("TOTAL rank mismatches:", len(mism))
print("\n== confusion types (gold -> mine) ==")
for (g, m), n in conf.most_common():
    print("  %d -> %d : %d" % (g, m, n))

print("\n== by LEADING letter ==")
byfirst = collections.Counter(re.sub(r"[^a-z]", "", t[0].lower())[:1] for t in mism)
for c, n in byfirst.most_common():
    print("  %s : %d" % (c, n))

print("\n== by token length (letters in first word) ==")
def wlen(t):
    w = t.split()[0] if t.split() else t
    return len(re.sub(r"[^a-z]", "", w.lower()))
byl = collections.Counter(wlen(t[0]) for t in mism)
for L in sorted(byl): print("  %d-letter : %d" % (L, byl[L]))

print("\n== round-letter dominated? (c/o/e/a/s/u share of first word) ==")
hi = lo = 0
for t in mism:
    w = re.sub(r"[^a-z]", "", t[0].split()[0].lower()) if t[0].split() else ""
    if not w: continue
    share = sum(ch in "coeasu" for ch in w) / len(w)
    if share >= 0.5: hi += 1
    else: lo += 1
print("  >=50%% round: %d   <50%%: %d" % (hi, lo))

print("\n== the mismatched tokens (gold/mine  weight,slant) ==")
for gtxt, g, m, f in sorted(mism, key=lambda x: (x[1], x[2], x[0].lower())):
    fs = "" if not f else " w=%.3f sl=%.1f" % (f["weight"], f["slant"])
    print("  %-12s gold=%d mine=%d%s" % (gtxt, g, m, fs))
