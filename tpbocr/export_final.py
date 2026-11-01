# -*- coding: utf-8 -*-
"""Export the final consensus-validated TPB dataset (Set A + auto-resolved Set C)
into normalized thinkhomeo.in repertory tables and consolidated CSV/JSON.

Inputs: out/verify/setA_confident.csv
Outputs under out/dataset/final/:
  tpb_final_graded.{csv,json}   all consolidated graded rows with provenance
  rep_rubric.csv                normalized unique rubrics
  rep_remedy.csv                normalized unique remedies mapped via authority
  rep_link.csv                  rubric -> remedy -> grade links

Usage: python -m tpbocr.export_final
"""
import sys, os, csv, json, re, collections
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VERIFY = os.path.join(ROOT, "out", "verify")
OUTDIR = os.path.join(ROOT, "out", "dataset", "final")
REFC = next((p for p in (
    os.path.join(ROOT, "..", "tpb-data", "reference"),
    os.path.join(ROOT, "..", "tpb-data", "reference-copyright"))
    if os.path.isdir(p)), os.path.join(ROOT, "..", "tpb-data", "reference"))

from tpbocr.remedy_authority import resolve_remedy

GRADE_NAME = {5: "CAPITALS", 4: "Antique", 3: "Italic", 2: "Roman", 1: "paren"}


def _nkey(s):
    return re.sub(r"[^a-z]", "", (s or "").lower())


def main():
    os.makedirs(OUTDIR, exist_ok=True)
    setA_path = os.path.join(VERIFY, "setA_confident.csv")
    if not os.path.exists(setA_path):
        print("Error: setA_confident.csv not found. Run consensus + revision_merge + resolve_consensus first.")
        return

    with open(setA_path, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))

    # normalize and build tables
    rubrics_map = {}   # norm_path -> rubric_name
    remedies_map = {}  # norm_abbrev -> remedy_dict
    links = []

    final_rows = []
    for r in rows:
        page = r.get("page", "")
        rubric = r.get("rubric", "").strip()
        remedy = r.get("remedy", "").strip()
        grade = int(r["grade"]) if str(r.get("grade", "")).isdigit() else 2
        reasons = r.get("reasons", "")

        rkey = _nkey(rubric)
        rubrics_map[rkey] = rubric

        # remedy resolution via authoritative master
        info = resolve_remedy(remedy)
        norm_ab = info["norm"]
        name = info["name"]
        std_abbrev = info["standard_abbrev"]
        common_name = info["common_name"]
        src = info["source"]
        raw_abbrev = info["raw_abbrev"]

        if norm_ab not in remedies_map:
            remedies_map[norm_ab] = {
                "id": len(remedies_map) + 1,
                "abbrev": raw_abbrev,
                "norm": norm_ab,
                "name": name,
                "standard_abbrev": std_abbrev,
                "common_name": common_name,
                "name_source": src,
                "occurrences": 0
            }
        remedies_map[norm_ab]["occurrences"] += 1
        rem_id = remedies_map[norm_ab]["id"]

        final_rows.append({
            "page": page,
            "rubric": rubric,
            "remedy": remedy,
            "grade": grade,
            "grade_name": GRADE_NAME.get(grade, "Roman"),
            "norm_remedy": norm_ab,
            "remedy_name": name,
            "standard_abbrev": std_abbrev,
            "provenance": reasons
        })

        links.append({
            "rubric_path": rubric,
            "remedy_abbrev": raw_abbrev,
            "remedy_id": rem_id,
            "grade": grade
        })

    # write outputs
    fn_csv = os.path.join(OUTDIR, "tpb_final_graded.csv")
    with open(fn_csv, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(final_rows[0].keys()))
        w.writeheader(); w.writerows(final_rows)

    fn_json = os.path.join(OUTDIR, "tpb_final_graded.json")
    json.dump({"total_tokens": len(final_rows), "rows": final_rows},
              open(fn_json, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    # normalise thinkhomeo tables
    with open(os.path.join(OUTDIR, "rep_rubric.csv"), "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f); w.writerow(["id", "path", "name"])
        for i, (k, name) in enumerate(sorted(rubrics_map.items()), 1):
            w.writerow([i, name, name])

    with open(os.path.join(OUTDIR, "rep_remedy.csv"), "w", newline="", encoding="utf-8-sig") as f:
        cols = ["id", "abbrev", "norm", "name", "standard_abbrev", "common_name", "name_source", "occurrences"]
        w = csv.DictWriter(f, fieldnames=cols); w.writeheader()
        for rem in sorted(remedies_map.values(), key=lambda x: -x["occurrences"]):
            w.writerow(rem)

    with open(os.path.join(OUTDIR, "rep_link.csv"), "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f); w.writerow(["rubric_path", "remedy_abbrev", "remedy_id", "grade"])
        for l in links:
            w.writerow([l["rubric_path"], l["remedy_abbrev"], l["remedy_id"], l["grade"]])

    mapped_rems = sum(1 for rem in remedies_map.values() if rem["name"])
    mapped_tokens = sum(rem["occurrences"] for rem in remedies_map.values() if rem["name"])
    print("SUCCESS: Exported final dataset to %s" % OUTDIR)
    print("  Total graded tokens : %d" % len(final_rows))
    print("  Unique rubrics      : %d" % len(rubrics_map))
    print("  Unique remedies     : %d" % len(remedies_map))
    print("  Mapped remedies     : %d/%d (%.1f%%)" % (mapped_rems, len(remedies_map), mapped_rems * 100 / len(remedies_map)))
    print("  Mapped tokens       : %d/%d (%.2f%%)" % (mapped_tokens, len(final_rows), mapped_tokens * 100 / len(final_rows)))


if __name__ == "__main__":
    main()
