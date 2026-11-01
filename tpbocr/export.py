# -*- coding: utf-8 -*-
"""Flatten the dashboard's graded tokens into consolidated repertory files.

Reads out/_dashboard_data.json (one blob per graded page) and emits one row
per remedy token into out/tpb_grades.csv + out/tpb_grades.json, ready for
thinkhomeo.in ingestion. Standard-library only; fully decoupled from the
vision pipeline (no cv2/numpy/model imports, no heavy side effects).

Usage:
  python -m tpbocr.export                 # defaults: out/_dashboard_data.json
  python -m tpbocr.export --data d.json --out out
"""
import sys, os, json, csv, argparse
sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # Windows console is cp1252

# CSV column order is a contract with the ingestion side — do not reorder.
COLS = ["book", "page_tag", "rubric", "remedy", "final_rank", "final_name",
        "scalar_rank", "mlp_rank", "shape_rank", "confidence", "flag",
        "adjudicated", "gold_rank", "correct"]
# final rank 1..5 -> the typeface face it was read from
NAME = {5: "CAPITALS", 4: "Antique", 3: "Italic", 2: "Roman", 1: "paren"}


def build_rows(data):
    """-> list of row dicts (keys == COLS), one per remedy token."""
    rows = []
    for p in data.get("pages", []):
        book, tag = p.get("book", ""), p.get("tag", "")
        for t in p.get("tokens", []):
            fr = t.get("rank")                       # final rank 1..5
            # engine votes: null means the token was text-derived (caps/parens)
            # and has no engine opinion -> fall back to the final rank.
            eng = lambda k: fr if t.get(k) is None else t.get(k)
            gold = t.get("gold")
            correct = "" if gold is None else (1 if gold == fr else 0)
            rows.append({
                "book": book, "page_tag": tag,
                "rubric": t.get("rubric", ""), "remedy": t.get("text", ""),
                "final_rank": fr, "final_name": NAME.get(fr, ""),
                "scalar_rank": eng("scalar"), "mlp_rank": eng("mlp"),
                "shape_rank": eng("shape"), "confidence": t.get("conf", ""),
                "flag": 1 if t.get("flag") else 0,
                "adjudicated": 1 if t.get("adj") else 0,
                "gold_rank": "" if gold is None else gold,
                "correct": correct,
            })
    return rows


def summarize(data, rows):
    with_gold = sum(1 for r in rows if r["gold_rank"] != "")
    ncorrect = sum(1 for r in rows if r["correct"] == 1)
    acc = round(100 * ncorrect / with_gold, 2) if with_gold else 0.0
    return {"pages": len(data.get("pages", [])), "tokens": len(rows),
            "with_gold": with_gold, "accuracy_pct": acc}


def main():
    ap = argparse.ArgumentParser(description="Export graded tokens to CSV + JSON.")
    ap.add_argument("--data", default="out/_dashboard_data.json")
    ap.add_argument("--out", default="out")
    a = ap.parse_args()

    data = json.load(open(a.data, encoding="utf-8"))
    rows = build_rows(data)
    summary = summarize(data, rows)

    csv_path = os.path.join(a.out, "tpb_grades.csv")
    json_path = os.path.join(a.out, "tpb_grades.json")

    # utf-8-sig: Excel then renders the Devanagari rubrics correctly.
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=COLS, quoting=csv.QUOTE_MINIMAL)
        w.writeheader()
        w.writerows(rows)
    json.dump({"summary": summary, "rows": rows},
              open(json_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    print("pages            : %d" % summary["pages"])
    print("tokens (rows)    : %d" % summary["tokens"])
    print("rows with gold   : %d" % summary["with_gold"])
    print("overall accuracy : %.2f%%" % summary["accuracy_pct"])
    print("csv  -> %s" % csv_path)
    print("json -> %s" % json_path)


if __name__ == "__main__":
    main()
