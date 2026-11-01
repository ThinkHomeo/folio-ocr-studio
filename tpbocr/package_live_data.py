# -*- coding: utf-8 -*-
"""Consolidate all TPB 1891 final data, 100% bounding boxes, and normalized percentages
into a unified live deliverable package under out/tpb_live_package/.
"""
import os, sys, csv, json, re

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_FINAL = os.path.join(ROOT, "out", "dataset", "final")
SRC_VERIFY = os.path.join(ROOT, "out", "verify")

PKG_DIR = os.path.join(ROOT, "out", "tpb_live_package")
DATA_DIR = os.path.join(PKG_DIR, "data")
PAGES_DIR = os.path.join(PKG_DIR, "pages")
UI_DIR = os.path.join(PKG_DIR, "ui")
SCHEMA_DIR = os.path.join(PKG_DIR, "schema")

for d in [DATA_DIR, PAGES_DIR, UI_DIR, SCHEMA_DIR]:
    os.makedirs(d, exist_ok=True)

REF_W = 2600.0
REF_H = 4242.0

def normalize_bbox(bbox_raw):
    """Convert [x0, y0, x1, y1] pixel string to normalized percentage dict [x, y, w, h]."""
    try:
        if isinstance(bbox_raw, str):
            bbox = json.loads(bbox_raw)
        else:
            bbox = bbox_raw
        if bbox and len(bbox) == 4:
            x0, y0, x1, y1 = [float(v) for v in bbox]
            x_pct = round((x0 / REF_W) * 100, 3)
            y_pct = round((y0 / REF_H) * 100, 3)
            w_pct = round(((x1 - x0) / REF_W) * 100, 3)
            h_pct = round(((y1 - y0) / REF_H) * 100, 3)
            return json.dumps([x_pct, y_pct, w_pct, h_pct])
    except Exception:
        pass
    return "[]"

def nkey(s):
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())

def main():
    print("=== STEP 1: CONSOLIDATING TPB LIVE DATA PACKAGE ===")

    # 1. Load setA_confident.csv for BBoxes
    setA_file = os.path.join(SRC_VERIFY, "setA_confident.csv")
    with open(setA_file, encoding="utf-8-sig") as f:
        setA = list(csv.DictReader(f))
    print(f"Loaded setA_confident: {len(setA):,} rows")

    # Map (page, nkey(rubric), nkey(remedy)) -> bbox
    bbox_map = {}
    for r in setA:
        k = (int(r["page"]), nkey(r["rubric"]), nkey(r["remedy"]))
        bbox_map[k] = r.get("bbox", "[]")

    # 2. Load and enhance tpb_final_graded.csv
    final_file = os.path.join(SRC_FINAL, "tpb_final_graded.csv")
    with open(final_file, encoding="utf-8-sig") as f:
        final_rows = list(csv.DictReader(f))
    print(f"Loaded tpb_final_graded: {len(final_rows):,} rows")

    enhanced_rows = []
    page_stats = collections.defaultdict(int)

    for r in final_rows:
        page = int(r["page"])
        page_stats[page] += 1
        k = (page, nkey(r["rubric"]), nkey(r["remedy"]))
        bbox = bbox_map.get(k, "[]")
        bbox_pct = normalize_bbox(bbox)

        enhanced_rows.append({
            "page": r["page"],
            "rubric": r["rubric"],
            "rubric_hi": r.get("rubric_hi", ""),
            "remedy": r["remedy"],
            "remedy_name": r.get("remedy_name", ""),
            "remedy_name_hi": r.get("remedy_name_hi", ""),
            "standard_abbrev": r.get("standard_abbrev", ""),
            "grade": r["grade"],
            "grade_name": r["grade_name"],
            "norm_remedy": r.get("norm_remedy", ""),
            "bbox": bbox,
            "bbox_pct": bbox_pct,
            "provenance": r.get("provenance", "")
        })

    # Save to data/tpb_final_graded.csv
    pkg_final_csv = os.path.join(DATA_DIR, "tpb_final_graded.csv")
    with open(pkg_final_csv, "w", newline="", encoding="utf-8-sig") as f:
        fieldnames = list(enhanced_rows[0].keys())
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(enhanced_rows)

    # Save to data/tpb_final_graded.json
    pkg_final_json = os.path.join(DATA_DIR, "tpb_final_graded.json")
    json.dump({"total_tokens": len(enhanced_rows), "tokens": enhanced_rows},
              open(pkg_final_json, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    print(f"SUCCESS: Wrote enhanced tpb_final_graded.csv & .json ({len(enhanced_rows):,} rows)")

    # 3. Copy & Enhance rep_rubric.csv
    src_rub = os.path.join(SRC_FINAL, "rep_rubric.csv")
    with open(src_rub, encoding="utf-8-sig") as f:
        rubs = list(csv.DictReader(f))

    # Add page ranges for rubrics
    rub_pages = collections.defaultdict(list)
    for r in enhanced_rows:
        rub_pages[r["rubric"]].append(int(r["page"]))

    for r in rubs:
        ps = rub_pages.get(r["name"], [])
        r["page_start"] = min(ps) if ps else ""
        r["page_end"] = max(ps) if ps else ""
        r["token_count"] = len(ps)

    pkg_rub_csv = os.path.join(DATA_DIR, "rep_rubric.csv")
    with open(pkg_rub_csv, "w", newline="", encoding="utf-8-sig") as f:
        fieldnames = ["id", "path", "name", "name_hi", "level", "page_start", "page_end", "token_count"]
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rubs)

    pkg_rub_json = os.path.join(DATA_DIR, "rep_rubric.json")
    json.dump({"total_rubrics": len(rubs), "rubrics": rubs},
              open(pkg_rub_json, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    print(f"SUCCESS: Wrote enhanced rep_rubric.csv & .json ({len(rubs):,} rubrics)")

    # 4. Copy rep_remedy.csv
    src_rem = os.path.join(SRC_FINAL, "rep_remedy.csv")
    with open(src_rem, encoding="utf-8-sig") as f:
        rems = list(csv.DictReader(f))

    pkg_rem_csv = os.path.join(DATA_DIR, "rep_remedy.csv")
    with open(pkg_rem_csv, "w", newline="", encoding="utf-8-sig") as f:
        fieldnames = list(rems[0].keys())
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rems)

    pkg_rem_json = os.path.join(DATA_DIR, "rep_remedy.json")
    json.dump({"total_remedies": len(rems), "remedies": rems},
              open(pkg_rem_json, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    print(f"SUCCESS: Wrote rep_remedy.csv & .json ({len(rems):,} remedies)")

    # 5. Build enhanced rep_link.csv
    rem_id_map = {r["norm"]: r["id"] for r in rems}
    rub_id_map = {r["name"]: r["id"] for r in rubs}

    links = []
    for r in enhanced_rows:
        rub_id = rub_id_map.get(r["rubric"], "")
        rem_id = rem_id_map.get(r["norm_remedy"], "")
        links.append({
            "rubric_id": rub_id,
            "remedy_id": rem_id,
            "rubric_path": r["rubric"],
            "remedy_abbrev": r["remedy"],
            "grade": r["grade"],
            "page": r["page"],
            "bbox_pct": r["bbox_pct"]
        })

    pkg_link_csv = os.path.join(DATA_DIR, "rep_link.csv")
    with open(pkg_link_csv, "w", newline="", encoding="utf-8-sig") as f:
        fieldnames = ["rubric_id", "remedy_id", "rubric_path", "remedy_abbrev", "grade", "page", "bbox_pct"]
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(links)

    pkg_link_json = os.path.join(DATA_DIR, "rep_link.json")
    json.dump({"total_links": len(links), "links": links},
              open(pkg_link_json, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    print(f"SUCCESS: Wrote enhanced rep_link.csv & .json ({len(links):,} links)")

    # 6. Build page_manifest.json (all 466 pages 17 to 482)
    manifest = []
    for p in range(17, 483):
        leaf = p + 6
        tok_cnt = page_stats[p]
        manifest.append({
            "book_page": p,
            "leaf_number": leaf,
            "image_filename": f"p{p:03d}.webp",
            "canvas_width": int(REF_W),
            "canvas_height": int(REF_H),
            "token_count": tok_cnt
        })

    manifest_path = os.path.join(DATA_DIR, "page_manifest.json")
    json.dump({"total_pages": len(manifest), "pages": manifest},
              open(manifest_path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

    print(f"SUCCESS: Wrote page_manifest.json ({len(manifest)} pages)")

if __name__ == "__main__":
    import collections
    main()
