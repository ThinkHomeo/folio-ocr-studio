# -*- coding: utf-8 -*-
"""Ingest user-certified CSVs (e.g., from Downloads) and fold their grades
into setA_confident.csv, then re-export the final dataset.

Usage: python -m tpbocr.ingest_certified [CSV_PATH]
"""
import sys, os, csv, json, re
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VERIFY = os.path.join(ROOT, "out", "verify")
GNAME = {5: "CAPITALS", 4: "Antique", 3: "Italic", 2: "Roman", 1: "paren"}
GCODE = {"5": 5, "4": 4, "3": 3, "2": 2, "1": 1, "C": 5, "A": 4, "I": 3, "R": 2, "P": 1}


def _rows(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def _write(path, rows, fieldnames):
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fieldnames})


def main():
    csv_path = None
    if len(sys.argv) > 1 and os.path.exists(sys.argv[1]):
        csv_path = sys.argv[1]
    else:
        downloads = os.path.join(os.path.expanduser("~"), "Downloads")
        candidates = [
            os.path.join(downloads, "tpb_certified_v2.csv"),
            os.path.join(downloads, "tpb_certified_audit.csv"),
            os.path.join(downloads, "tpb_certified_ties.csv"),
        ]
        # check candidate paths
        for p in candidates:
            if os.path.exists(p):
                csv_path = p
                break
        # fallback: find latest tpb_certified*.csv in Downloads
        if not csv_path and os.path.isdir(downloads):
            import glob
            files = glob.glob(os.path.join(downloads, "tpb_certified*.csv"))
            if files:
                files.sort(key=os.path.getmtime, reverse=True)
                csv_path = files[0]

    if not csv_path or not os.path.exists(csv_path):
        print("Certified CSV not found in Downloads or specified path.")
        return

    cert_rows = _rows(csv_path)
    print("Loaded certified rows: %d from %s" % (len(cert_rows), csv_path))

    setA_path = os.path.join(VERIFY, "setA_confident.csv")
    setA_rows = _rows(setA_path)
    if not setA_rows:
        print("Error: setA_confident.csv not found.")
        return

    # index Set A by (page, norm_rubric, norm_remedy)
    def nkey(s): return re.sub(r"[^a-z0-9]", "", (s or "").lower())

    setA_index = {}
    for idx, r in enumerate(setA_rows):
        k = (int(r["page"]), nkey(r["rubric"]), nkey(r["remedy"]))
        setA_index[k] = idx

    updated = 0
    for cr in cert_rows:
        try:
            page = int(cr["page"])
        except:
            continue
        rub = cr["rubric"]
        rem = cr["remedy"]
        grade_raw = cr.get("certified_grade", "").strip()
        # extract code letter or digit
        match_g = re.search(r"([1-5CARIP])", grade_raw, re.I)
        if not match_g:
            continue
        g_char = match_g.group(1).upper()
        g_int = GCODE.get(g_char, 2)

        k = (page, nkey(rub), nkey(rem))
        if k in setA_index:
            idx = setA_index[k]
            setA_rows[idx]["grade"] = g_int
            setA_rows[idx]["grade_name"] = GNAME.get(g_int, "Roman")
            setA_rows[idx]["reasons"] = "user-certified(grade=%d)" % g_int
            updated += 1

    fieldnames = list(setA_rows[0].keys())
    _write(setA_path, setA_rows, fieldnames)
    print("Successfully updated %d rows in setA_confident.csv with user certifications!" % updated)

    # Re-run export_final
    from tpbocr import export_final
    export_final.main()


if __name__ == "__main__":
    main()
