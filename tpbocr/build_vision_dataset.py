# -*- coding: utf-8 -*-
"""Build the VISION-AUTHORITATIVE rubric -> remedy -> grade dataset for the whole
TPB (1891), straight from the vision-gold .md pages (the authoritative truth).

Grade = typeface rank, read by the vision model and encoded in the markdown:
  CAPS = 5 | **bold** = Antique 4 | *italic* = Italic 3 | plain = Roman 2 | (parens) = 1

Emits, under out/dataset/:
  tpb_vision_rows.{json,csv}   one row per (rubric, remedy) with grade + context
  rep_rubric.csv  rep_remedy.csv  rep_link.csv   normalised thinkhomeo.in tables
  tpb_vision_dataset.json      everything + build summary

Standard library only (no cv2/numpy/model) — decoupled from the OCR pipeline.
Usage: python -m tpbocr.build_vision_dataset [START] [END]   (default 17..495)
"""
import sys, os, re, json, csv, glob, argparse, collections
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BK = os.path.join(ROOT, "..", "tpb-data", "public-domain", "books",
                  "07_Allen_1891_New_American_Edition_Boston")
OCR_OUT = os.path.join(BK, "ocr_out")
# reference data folder was renamed reference-copyright -> reference; accept either
REFC = next((p for p in (
    os.path.join(ROOT, "..", "tpb-data", "reference"),
    os.path.join(ROOT, "..", "tpb-data", "reference-copyright"))
    if os.path.isdir(p)), os.path.join(ROOT, "..", "tpb-data", "reference"))
OUTDIR = os.path.join(ROOT, "out", "dataset")

GRADE_NAME = {5: "CAPITALS", 4: "Antique", 3: "Italic", 2: "Roman", 1: "paren"}
DASH = "—–―-"                       # em / en / horizontal-bar / hyphen
CONT = re.compile(r"जारी|continued", re.I)   # continuation markers (Hindi/Eng)


def tok_grade(t):
    """Typeface rank 1..5 of one markdown-marked remedy token."""
    t = t.strip()
    if t.startswith("(") and (t.endswith(")") or t.endswith(").")):
        return 1
    if t.startswith("**") and t.endswith("**"):
        return 4
    if t.startswith("*") and t.endswith("*"):
        return 3
    core = re.sub(r"[*()]", "", t)
    L = [c for c in core if c.isalpha()]
    return 5 if (L and all(c.isupper() for c in L)) else 2


def tok_surface(t):
    """Printed abbreviation, markdown & stray punctuation stripped, as the book
    prints it (keeps internal '.' and ' ', e.g. 'Am. carb.', 'Nux v.')."""
    s = re.sub(r"\*", "", t).strip()
    s = s.strip("()").strip()
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"\.\.+", ".", s)        # 'Nat. m..' -> 'Nat. m.'
    s = s.strip(" ,;")
    return s


def split_toks(blob):
    """-> list of (surface, grade) from a comma-separated remedy list, dropping
    a trailing '… (book p.N पर जारी)' cross-page continuation marker."""
    if "जारी" in blob or "continued" in blob.lower():
        blob = re.split(r"…|\.\.\.", blob)[0]       # cut at the ellipsis marker
    out = []
    for raw in blob.split(","):
        if not raw.strip():
            continue
        g = tok_grade(raw)
        s = tok_surface(raw)
        if s and re.search(r"[A-Za-z]", s):
            out.append((s, g))
    return out


def token_issue(surf):
    """Classify a structurally suspect remedy surface for the review queue;
    '' means it looks like a clean single abbreviation."""
    if "जारी" in surf or "book p" in surf.lower() or "…" in surf:
        return "continuation-leak"
    if surf.count("(") != surf.count(")"):
        return "unbalanced-parens"
    letters = re.sub(r"[^A-Za-z]", "", surf)
    allcaps = bool(letters) and letters.isupper()
    if not allcaps and re.search(r"[a-z]\.\s+[A-Z]", surf):
        return "glued-tokens"      # a second Capital-initial abbrev (missing comma)
    return ""


# ---- line patterns -------------------------------------------------------
RE_H1 = re.compile(r"^#\s+(.*\S)\s*$")
RE_H2 = re.compile(r"^##\s+(.*\S)\s*$")
# optional leading dashes (sub-rubric), **Name**, a dash, then the remedy list
RE_RUB = re.compile(r"^\s*([%s]+)?\s*\*\*(.+?)\*\*\s*[%s]+\s*(.*)$" % (DASH, DASH))
RE_SUBHEAD = re.compile(r"^\s*\*\*(.+?)\*\*\s*$")           # standalone bold label
RE_PAGENO = re.compile(r"^#\s*\(?\s*\d+\s*\)?\s*$")
RE_INDEX_LINE = re.compile(r"^[A-Z].*,\s*\d")              # 'Abdomen, 78'


def clean_name(s):
    return re.sub(r"\s+", " ", s).strip().rstrip(".").strip()


def parse_book(start, end):
    """Walk the gold pages in order, accumulating an ordered list of rubric
    records. Handles chapters (#), sub-chapters/subject-remedies (##), bold
    sub-headings, nested (——) sub-rubrics, index pages, and cross-page
    continuations."""
    rubrics = []                 # ordered: dict(page,chapter,section,group,path,name,parent,depth,remedies)
    chapter = section = group = None
    index_mode = False
    depth_rubric = {}            # depth -> last rubric record (for parenting)

    def add_rubric(page, name, blob, depth):
        nonlocal rubrics
        parent = depth_rubric.get(depth - 1) if depth > 0 else None
        parts = [chapter, group, (parent["name"] if parent else None), name]
        path = " > ".join([clean_name(p) for p in parts if p])
        rec = dict(page=page, chapter=chapter or "", section=section or "main",
                   group=group or "", name=clean_name(name),
                   parent=(parent["name"] if parent else ""),
                   depth=depth, path=path, remedies=split_toks(blob))
        rubrics.append(rec)
        depth_rubric[depth] = rec
        for d in list(depth_rubric):      # deeper levels reset
            if d > depth:
                depth_rubric.pop(d)
        return rec

    for bp in range(start, end + 1):
        p = os.path.join(OCR_OUT, "therapeuticpocke0000timo_bp0%d.md" % bp)
        if not os.path.exists(p):
            continue
        for line in open(p, encoding="utf-8"):
            s = line.strip()
            if not s or s.startswith("<!--"):
                continue
            if RE_PAGENO.match(s):
                continue
            m = RE_H1.match(s)
            if m:
                title = clean_name(m.group(1))
                index_mode = title.upper().startswith("INDEX")
                if "RELATIONSHIP" in title.upper():
                    new_section, new_chapter = "relationships", "Relationships of Remedies"
                else:
                    new_section, new_chapter = "main", title
                if new_chapter != chapter:       # real chapter change, not a running head
                    chapter = new_chapter; section = new_section
                    group = None; depth_rubric.clear()
                continue
            m = RE_H2.match(s)
            if m:
                group = clean_name(m.group(1)); depth_rubric.clear()
                continue
            if index_mode or RE_INDEX_LINE.match(s):
                continue
            m = RE_RUB.match(s)
            if m:
                dashes, name, blob = m.group(1), m.group(2), m.group(3)
                depth = 1 if dashes else 0
                if CONT.search(name) and rubrics:      # '(पिछली रूब्रिक जारी)'
                    rubrics[-1]["remedies"].extend(split_toks(blob))
                    continue
                add_rubric(bp, name, blob, depth)
                continue
            m = RE_SUBHEAD.match(s)
            if m:                                       # bold label, no remedies
                group = clean_name(m.group(1)); depth_rubric.clear()
                continue
            # anything else (NOTE.— paragraphs, stray text) is ignored
    return rubrics


# ---- remedy-name authority (best-effort; site owns final id mapping) -----
def _nkey(s):
    return re.sub(r"[^a-z]", "", s.lower())


def load_authority():
    """-> dict(norm_abbrev -> (name, source)). PD core125 wins over GPL oorep;
    oorep names are marked 'oorep(ref)' = reference-only, not for shipping."""
    auth = {}
    try:
        op = os.path.join(REFC, "oorep-remedies_by_abbrev.json")
        for ab, rec in json.load(open(op, encoding="utf-8")).items():
            k = _nkey(ab)
            if k and k not in auth:
                auth[k] = (rec.get("name", ""), "oorep(ref)")
    except Exception:
        pass
    try:
        sys.path.insert(0, os.path.join(ROOT, "..", "tpb-data"))
        import core125
        for _, ab, latin in core125.CORE_125:
            if ab:
                auth[_nkey(ab)] = (latin, "core125(PD)")   # PD overrides
    except Exception:
        pass
    return auth


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("start", nargs="?", type=int, default=17)
    ap.add_argument("end", nargs="?", type=int, default=495)
    a = ap.parse_args()
    os.makedirs(OUTDIR, exist_ok=True)

    rubrics = parse_book(a.start, a.end)

    # merge adjacent records with identical path (silent cross-page spillover)
    merged = []
    for r in rubrics:
        if merged and merged[-1]["path"] == r["path"] and merged[-1]["page"] != r["page"]:
            merged[-1]["remedies"].extend(r["remedies"])
        else:
            merged.append(r)
    rubrics = merged

    auth = load_authority()

    # normalised remedy registry: norm-key -> {display, count, name, source}
    reg = {}
    for r in rubrics:
        for surf, g in r["remedies"]:
            k = _nkey(surf)
            if not k:
                continue
            e = reg.setdefault(k, dict(forms=collections.Counter(), key=k))
            e["forms"][surf] += 1

    remedy_id = {}
    rep_remedy = []
    for i, (k, e) in enumerate(sorted(reg.items()), 1):
        display = e["forms"].most_common(1)[0][0]
        name, src = auth.get(k, ("", ""))
        issue = token_issue(display)
        remedy_id[k] = i
        rep_remedy.append(dict(id=i, abbrev=display, norm=k, name=name,
                               name_source=src,
                               occurrences=sum(e["forms"].values()),
                               issue=issue))
    issue_of = {r["norm"]: r["issue"] for r in rep_remedy}

    rubric_id = {}
    rep_rubric = []
    rep_link = []
    rows = []
    for r in rubrics:
        path = r["path"]
        if path not in rubric_id:
            rid = len(rep_rubric) + 1
            rubric_id[path] = rid
            rep_rubric.append(dict(id=rid, book="TPB", page=r["page"],
                                   section=r["section"], chapter=r["chapter"],
                                   group=r["group"], parent=r["parent"],
                                   rubric=r["name"], path=path))
        rid = rubric_id[path]
        for surf, g in r["remedies"]:
            k = _nkey(surf)
            mid = remedy_id.get(k, "")
            issue = issue_of.get(k, "")
            rep_link.append(dict(rubric_id=rid, remedy_id=mid, grade=g,
                                 grade_name=GRADE_NAME[g], review=1 if issue else 0))
            rows.append(dict(book="TPB", page=r["page"], section=r["section"],
                             chapter=r["chapter"], group=r["group"],
                             parent=r["parent"], rubric=r["name"], path=path,
                             remedy=surf, grade=g, grade_name=GRADE_NAME[g],
                             review=issue))

    _write(rows, rep_rubric, rep_remedy, rep_link, auth)


def _write(rows, rep_rubric, rep_remedy, rep_link, auth):
    def wcsv(name, data, cols):
        with open(os.path.join(OUTDIR, name), "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=cols, quoting=csv.QUOTE_MINIMAL)
            w.writeheader(); w.writerows(data)

    wcsv("tpb_vision_rows.csv", rows,
         ["book", "page", "section", "chapter", "group", "parent", "rubric",
          "path", "remedy", "grade", "grade_name", "review"])
    wcsv("rep_rubric.csv", rep_rubric,
         ["id", "book", "page", "section", "chapter", "group", "parent", "rubric", "path"])
    wcsv("rep_remedy.csv", rep_remedy,
         ["id", "abbrev", "norm", "name", "name_source", "occurrences", "issue"])
    wcsv("rep_link.csv", rep_link,
         ["rubric_id", "remedy_id", "grade", "grade_name", "review"])

    review = [r for r in rep_remedy if r["issue"]]
    wcsv("review_tokens.csv", review,
         ["id", "abbrev", "norm", "name", "name_source", "occurrences", "issue"])

    mapped = sum(1 for r in rep_remedy if r["name"])
    clean = [r for r in rep_remedy if not r["issue"]]
    gdist = collections.Counter(r["grade"] for r in rows)
    summary = dict(
        rubrics=len(rep_rubric), remedies=len(rep_remedy),
        remedies_clean=len(clean), remedies_review=len(review),
        links=len(rep_link), rows=len(rows),
        rows_review=sum(1 for r in rows if r["review"]),
        remedies_name_mapped=mapped,
        name_mapped_pct=round(100 * mapped / max(1, len(rep_remedy)), 1),
        name_mapped_pct_clean=round(100 * sum(1 for r in clean if r["name"]) / max(1, len(clean)), 1),
        grade_distribution={GRADE_NAME[g]: gdist.get(g, 0) for g in (5, 4, 3, 2, 1)},
        review_issues=dict(collections.Counter(r["issue"] for r in review)),
        sections=dict(collections.Counter(r["section"] for r in rep_rubric)),
    )
    json.dump(dict(summary=summary, rep_rubric=rep_rubric, rep_remedy=rep_remedy,
                   rep_link=rep_link),
              open(os.path.join(OUTDIR, "tpb_vision_dataset.json"), "w",
                   encoding="utf-8"), ensure_ascii=False)
    json.dump(dict(summary=summary, rows=rows),
              open(os.path.join(OUTDIR, "tpb_vision_rows.json"), "w",
                   encoding="utf-8"), ensure_ascii=False)
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    print("-> %s" % OUTDIR)


if __name__ == "__main__":
    main()
