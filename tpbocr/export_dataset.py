# -*- coding: utf-8 -*-
"""Consolidate the whole-book MACHINE OCR (out/book/pNNN.json) into single
machine-readable datasets with all info: page, rubric, remedy (raw + dictionary-
corrected), rank/grade, rank name, confidence, review flag, bbox.

Outputs (in out/book/):
  tpb_machine_dataset.json   full nested structure
  tpb_machine_dataset.csv    flat, DB-ready (one row per rubric-remedy)
Usage: python -m tpbocr.export_dataset
"""
import os, re, json, glob, csv
import sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tpbocr import dict_correct as DC

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BOOK = os.path.join(ROOT, "out", "book")
OCR_OUT = os.path.join(ROOT, "..", "tpb-data", "public-domain", "books",
                       "07_Allen_1891_New_American_Edition_Boston", "ocr_out")
RANK_NAME = {5: "CAPITALS", 4: "Antique", 3: "Italic", 2: "Roman", 1: "Roman-paren"}


def main():
    vocab = DC.default_vocab(OCR_OUT); vkeys = list(vocab.keys())
    pages = []
    flat = []
    files = sorted(glob.glob(os.path.join(BOOK, "p[0-9][0-9][0-9].json")))
    n_rub = n_rem = 0
    for fp in files:
        bp = int(re.search(r"p(\d+)\.json$", fp).group(1))
        doc = json.load(open(fp, encoding="utf-8"))
        prub = []
        for ru in doc["rubrics"]:
            if not ru["rubric"]:
                continue
            rems = []
            for seq, rem in enumerate(ru["remedies"], 1):
                raw = rem["text"]
                cor, k, dist, unc = DC.correct(raw, vocab, vkeys)
                name = cor if not unc else raw
                low = bool(rem.get("flag") or unc)
                rec = dict(seq=seq, remedy=name, remedy_raw=raw,
                           rank=rem["rank"], grade=rem["rank"],
                           rank_name=RANK_NAME.get(rem["rank"], "?"),
                           confidence=rem.get("confidence"),
                           low_confidence=low, bbox=rem.get("bbox"))
                rems.append(rec)
                flat.append([bp, ru["rubric"], seq, name, raw, rem["rank"],
                             RANK_NAME.get(rem["rank"], "?"), rem.get("confidence"),
                             int(low)])
                n_rem += 1
            prub.append(dict(rubric=ru["rubric"], n=len(rems), remedies=rems))
            n_rub += 1
        pages.append(dict(page=bp, weight_threshold=doc.get("weight_threshold"),
                          image_size=doc.get("image_size"), rubrics=prub))

    meta = dict(book="Boenninghausen/Allen Therapeutic Pocket Book",
                edition="1891 New American Edition (Boston)",
                source="machine OCR (tpbocr pipeline: Tesseract + MLP/shape/scalar typeface rank)",
                rank_legend={5:"CAPITALS (highest)",4:"Antique/bold",3:"Italic",
                             2:"Roman",1:"Roman in parentheses (lowest)"},
                note="grade == rank (typeface-derived). low_confidence=true -> needs review. "
                     "Vision gold (ocr_out/bp0NN.md) is the authoritative reference.",
                pages=len(pages), rubrics=n_rub, remedies=n_rem)
    outj = os.path.join(BOOK, "tpb_machine_dataset.json")
    json.dump(dict(meta=meta, pages=pages), open(outj, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    outc = os.path.join(BOOK, "tpb_machine_dataset.csv")
    with open(outc, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["page","rubric","seq","remedy","remedy_raw","rank","grade",
                    "rank_name","confidence","low_confidence"])
        for row in flat:
            w.writerow([row[0],row[1],row[2],row[3],row[4],row[5],row[5],
                        row[6],row[7],row[8]])
    print("pages=%d rubrics=%d remedies=%d" % (len(pages), n_rub, n_rem))
    print("-> %s" % outj)
    print("-> %s" % outc)

if __name__ == "__main__":
    main()
