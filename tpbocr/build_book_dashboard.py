# -*- coding: utf-8 -*-
"""One self-contained, instantly-openable HTML view of the WHOLE book: the
vision-authoritative dataset stats, grade distribution, the machine-vs-vision
agreement + confusion matrix, a per-chapter breakdown, and the two review
queues (confident machine/vision typeface disagreements, and structurally
suspect tokens). No per-page images, so it stays light across all 479 pages.

Reads the JSON/CSV artifacts (build_vision_dataset + compare_book). Stdlib only.
Usage: python -m tpbocr.build_book_dashboard
"""
import sys, os, re, json, csv, html, collections
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DS = os.path.join(ROOT, "out", "dataset")
BOOK = os.path.join(ROOT, "out", "book")
OUT = os.path.join(ROOT, "out", "book_dashboard.html")

GRADE_NAME = {5: "CAPITALS", 4: "Antique", 3: "Italic", 2: "Roman", 1: "paren"}
GRADE_COLOR = {5: "#c62828", 4: "#d87800", 3: "#1a7a3c", 2: "#1e5ac8", 1: "#783caa"}


def readcsv(path):
    if not os.path.exists(path):
        return []
    return list(csv.DictReader(open(path, encoding="utf-8-sig")))


def esc(s):
    return html.escape(str(s if s is not None else ""))


def bars(dist, total):
    out = []
    for g in (5, 4, 3, 2, 1):
        n = dist.get(g, 0)
        pct = 100.0 * n / max(1, total)
        out.append(
            "<div class=row><span class=lbl>%d %s</span>"
            "<span class=bar><i style='width:%.1f%%;background:%s'></i></span>"
            "<span class=num>%s (%.1f%%)</span></div>"
            % (g, GRADE_NAME[g], pct, GRADE_COLOR[g], f"{n:,}", pct))
    return "".join(out)


def confusion_from_comparison(comp):
    """Parse the 5x5 vision(row)xmachine(col) matrix out of COMPARISON.md."""
    cm = {}
    for a in (5, 4, 3, 2, 1):
        m = re.search(r"\|\s*\*\*%d\*\*\s*\|([^\n]+)\|" % a, comp)
        if not m:
            return None
        nums = [int(x) for x in re.findall(r"\d+", m.group(1))]
        if len(nums) >= 5:
            cm[a] = dict(zip((5, 4, 3, 2, 1), nums[:5]))
    if len(cm) != 5:
        return None
    rows = ["<table class=cm><tr><th>v \\ m</th>%s</tr>" %
            "".join("<th>%d %s</th>" % (g, GRADE_NAME[g]) for g in (5, 4, 3, 2, 1))]
    for a in (5, 4, 3, 2, 1):
        tds = []
        for b in (5, 4, 3, 2, 1):
            v = cm[a][b]
            cls = "diag" if a == b else ("hot" if v else "")
            tds.append("<td class='%s'>%s</td>" % (cls, f"{v:,}" if v else "·"))
        rows.append("<tr><th>%d %s</th>%s</tr>" % (a, GRADE_NAME[a], "".join(tds)))
    rows.append("</table>")
    return "".join(rows)


def main():
    ds = json.load(open(os.path.join(DS, "tpb_vision_dataset.json"), encoding="utf-8"))
    S = ds["summary"]
    rows = json.load(open(os.path.join(DS, "tpb_vision_rows.json"), encoding="utf-8"))["rows"]
    gdist = collections.Counter(int(r["grade"]) for r in rows)
    disagree = readcsv(os.path.join(BOOK, "disagreements.csv"))
    audit = readcsv(os.path.join(BOOK, "vision_audit_queue.csv"))
    qa = [r for r in audit if r["tier"] in ("definite", "P1-review-first", "P2")]
    review = readcsv(os.path.join(DS, "review_tokens.csv"))

    # agreement counts per grade (matched - disagreed) from COMPARISON.md header
    comp = ""
    cpath = os.path.join(BOOK, "COMPARISON.md")
    if os.path.exists(cpath):
        comp = open(cpath, encoding="utf-8").read()
    m = re.search(r"matched tokens: (\d+) .*?agreement: ([\d.]+)%", comp)
    matched = int(m.group(1)) if m else 0
    agree_pct = m.group(2) if m else "?"

    # per-chapter row counts
    chap = collections.Counter(r["chapter"] for r in rows)
    chap_rows = "".join(
        "<tr><td>%s</td><td>%s</td></tr>" % (esc(c), f"{n:,}")
        for c, n in sorted(chap.items(), key=lambda x: -x[1])[:40])

    def qa_table(data, cols, hdr, limit=400):
        head = "".join("<th>%s</th>" % h for h in hdr)
        body = []
        for d in data[:limit]:
            body.append("<tr>%s</tr>" % "".join("<td>%s</td>" % esc(d.get(c, "")) for c in cols))
        more = ("<tr><td colspan=%d class=more>… %d more (see CSV)</td></tr>"
                % (len(cols), len(data) - limit)) if len(data) > limit else ""
        return "<table class=q><tr>%s</tr>%s%s</table>" % (head, "".join(body), more)

    qa_tbl = qa_table(qa, ["tier", "page", "rubric", "remedy", "vision", "machine_reads", "score"],
                      ["tier", "pg", "rubric", "remedy", "vision", "machine reads", "score"])
    rev_tbl = qa_table(review, ["abbrev", "occurrences", "issue"],
                       ["token", "occ", "issue"], limit=300)
    cm_html = confusion_from_comparison(comp) or "<i>run compare_book first</i>"

    doc = TEMPLATE.format(
        agree_pct=agree_pct, matched=f"{matched:,}",
        rubrics=f"{S['rubrics']:,}", remedies=S["remedies"],
        remedies_clean=S.get("remedies_clean", "?"), rows=f"{S['rows']:,}",
        mapped_pct=S.get("name_mapped_pct", "?"),
        rows_review=S.get("rows_review", 0), review_n=len(review),
        qa_n=len(qa), disagree_n=len(disagree),
        bars=bars(gdist, sum(gdist.values())),
        cm=cm_html, chap_rows=chap_rows, qa_tbl=qa_tbl, rev_tbl=rev_tbl,
        gen=__import__("time").strftime("%Y-%m-%d %H:%M"))
    open(OUT, "w", encoding="utf-8").write(doc)
    print("-> %s  (%d rubrics, %d rows, qa=%d, review=%d)"
          % (OUT, S["rubrics"], S["rows"], len(qa), len(review)))


TEMPLATE = """<!doctype html><html lang=en><meta charset=utf-8>
<title>TPB 1891 — whole-book grade dashboard</title>
<style>
*{{box-sizing:border-box}}body{{font:14px/1.5 -apple-system,Segoe UI,Roboto,sans-serif;
margin:0;background:#f6f5f2;color:#1a1a1a}}
header{{background:#1b2a4a;color:#fff;padding:18px 26px}}
header h1{{margin:0;font-size:20px}}header p{{margin:4px 0 0;opacity:.8;font-size:13px}}
main{{max-width:1120px;margin:0 auto;padding:22px}}
.cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin-bottom:22px}}
.card{{background:#fff;border:1px solid #e3e0d8;border-radius:10px;padding:14px 16px}}
.card b{{display:block;font-size:26px;color:#1b2a4a}}.card span{{font-size:12px;color:#666}}
section{{background:#fff;border:1px solid #e3e0d8;border-radius:10px;padding:18px;margin-bottom:20px}}
h2{{margin:0 0 12px;font-size:16px;color:#1b2a4a}}
.row{{display:flex;align-items:center;gap:10px;margin:5px 0}}
.lbl{{width:110px;font-size:13px}}.bar{{flex:1;background:#eee;border-radius:5px;height:18px;overflow:hidden}}
.bar i{{display:block;height:100%}}.num{{width:150px;text-align:right;font-variant-numeric:tabular-nums;font-size:13px}}
table{{border-collapse:collapse;width:100%;font-size:13px}}
.cm td,.cm th{{border:1px solid #ddd;padding:6px 10px;text-align:center}}
.cm .diag{{background:#e8f5e9;font-weight:600}}.cm .hot{{background:#fdecea}}
.q{{display:block;max-height:420px;overflow:auto}}
.q th,.q td{{border-bottom:1px solid #eee;padding:5px 8px;text-align:left}}
.q th{{position:sticky;top:0;background:#f0eee8}}
.more{{text-align:center;color:#888;font-style:italic}}
.two{{display:grid;grid-template-columns:1fr 1fr;gap:20px}}
@media(max-width:800px){{.two{{grid-template-columns:1fr}}}}
.note{{font-size:12px;color:#777;margin-top:6px}}
</style>
<header><h1>Boenninghausen / Allen — Therapeutic Pocket Book (1891)</h1>
<p>Whole-book rubric → remedy → <b>grade</b> (typeface rank). Vision gold = authoritative; machine = QA auditor. Generated {gen}.</p></header>
<main>
<div class=cards>
<div class=card><b>{rows}</b><span>graded (rubric,remedy) rows</span></div>
<div class=card><b>{rubrics}</b><span>rubrics</span></div>
<div class=card><b>{remedies}</b><span>distinct remedies ({remedies_clean} clean)</span></div>
<div class=card><b>{agree_pct}%</b><span>machine agrees w/ vision ({matched} matched)</span></div>
<div class=card><b>{qa_n}</b><span>vision-audit queue (likely vision slips)</span></div>
<div class=card><b>{review_n}</b><span>structurally suspect tokens</span></div>
</div>
<section><h2>Grade distribution (vision, authoritative)</h2>{bars}
<p class=note>5=CAPITALS · 4=Antique(bold) · 3=Italic · 2=Roman · 1=(parens). Remedy-name authority mapped on {mapped_pct}% of distinct tokens (site remedy-master resolves the rest).</p></section>
<section><h2>Machine vs Vision — confusion matrix</h2>{cm}
<p class=note>Rows = vision grade, columns = machine grade. Off-diagonal = machine disagrees; the Roman↔Antique (2↔4) cell is the known hard pair.</p></section>
<div class=two>
<section><h2>Vision-audit queue — likely VISION errors to verify <small>({qa_n})</small></h2>
<p class=note>Where the machine's INDEPENDENT typeface reading (scalar+shape) contradicts the vision gold, ranked so genuine vision slips surface first. tier: definite = structural OCR slip · P1 = review first · P2 = next. Full list: out/book/vision_audit_queue.csv</p>{qa_tbl}</section>
<section><h2>Structurally suspect tokens <small>({review_n})</small></h2>
<p class=note>Glued/paren OCR slips in the vision gold → re-read these. Full list: out/dataset/review_tokens.csv</p>{rev_tbl}</section>
</div>
<section><h2>Rows per chapter (top 40)</h2><div class=q><table class=q>
<tr><th>chapter</th><th>rows</th></tr>{chap_rows}</table></div></section>
</main></html>"""


if __name__ == "__main__":
    main()
