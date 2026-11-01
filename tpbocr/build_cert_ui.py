# -*- coding: utf-8 -*-
"""Build an interactive UI dashboard for Set-C residual tie certification (1,133 tokens)
and auto-resolved audit sample inspection (150 tokens), embedding direct visual
BOOK CROPS (base64 JPEGs) alongside each row so the user can verify against the actual print.

Reads out/verify/setC_residual.csv and out/verify/setC_audit_sample.csv.
Emits out/verify/cert_ui.html.

Usage: python -m tpbocr.build_cert_ui
"""
import sys, os, csv, json, html, collections, io, zipfile, base64
import numpy as np, cv2
from PIL import Image, ImageDraw
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BK = os.path.join(ROOT, "..", "tpb-data", "public-domain", "books",
                  "07_Allen_1891_New_American_Edition_Boston")
ZIP = os.path.join(BK, "therapeuticpocke0000timo_jp2.zip")
VERIFY = os.path.join(ROOT, "out", "verify")
OUT = os.path.join(VERIFY, "cert_ui.html")


def readcsv(path):
    if not os.path.exists(path):
        return []
    return list(csv.DictReader(open(path, encoding="utf-8-sig")))


def render_leaf_cached(z, leaf, cache, width=1300, scale=2):
    if leaf in cache:
        return cache[leaf]
    name = "therapeuticpocke0000timo_jp2/therapeuticpocke0000timo_%04d.jp2" % leaf
    im = Image.open(io.BytesIO(z.read(name))).convert("L")
    h = int(im.height * width / im.width)
    im = im.resize((width, h), Image.LANCZOS)
    g = np.asarray(im)
    res = cv2.resize(g, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    cache[leaf] = res
    return res


def main():
    ties = readcsv(os.path.join(VERIFY, "setC_residual.csv"))
    audit = readcsv(os.path.join(VERIFY, "setC_audit_sample.csv"))

    print("Opening JP2 zip for crop extraction...")
    z = zipfile.ZipFile(ZIP)
    leaf_cache = {}
    CTX = 230

    import re
    def enrich(rows, tag):
        out = []
        total = len(rows)
        for idx, r in enumerate(rows):
            if idx % 100 == 0 and idx > 0:
                print(f"  processed {idx}/{total} {tag} crops...")
            reasons = r.get("reasons", "")
            m = re.search(r"v1=(\d),v2=(\d)", reasons)
            v1 = m.group(1) if m else r.get("grade", "")
            v2 = m.group(2) if m else "?"

            v = [int(x) for x in (r.get("scalar"), r.get("mlp"), r.get("shape")) if x not in ("", "None", None)]
            eng = str(collections.Counter(v).most_common(1)[0][0]) if v else "?"

            bp = int(r.get("page", 17))
            bbox_str = r.get("bbox", "")
            img_b64 = ""
            try:
                bbox = json.loads(bbox_str) if bbox_str else None
                if bbox and len(bbox) == 4:
                    gray = render_leaf_cached(z, bp + 6, leaf_cache)
                    gh, gw = gray.shape
                    x0, y0, x1, y1 = [int(v) for v in bbox]
                    cx0, cx1 = max(0, x0 - CTX), min(gw, x1 + CTX)
                    cy0, cy1 = max(0, y0 - 8), min(gh, y1 + 8)
                    crop = gray[cy0:cy1, cx0:cx1]
                    if crop.size > 0:
                        rim = Image.fromarray(crop).convert("RGB")
                        # draw red box around target
                        d = ImageDraw.Draw(rim)
                        d.rectangle([x0 - cx0, y0 - cy0, x1 - cx0, y1 - cy0], outline=(220, 30, 30), width=3)
                        # resize thumbnail
                        rim.thumbnail((260, 70), Image.LANCZOS)
                        buf = io.BytesIO()
                        rim.save(buf, format="JPEG", quality=85)
                        img_b64 = "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode("utf-8")
            except Exception as e:
                pass

            out.append({
                "page": bp,
                "rubric": r.get("rubric", ""),
                "remedy": r.get("remedy", ""),
                "v1": v1, "v2": v2, "eng": eng,
                "reasons": reasons,
                "img": img_b64
            })
        return out

    ties_data = enrich(ties, "ties")
    audit_data = enrich(audit, "audit")

    html_template = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>TPB Set-C Certification & Audit UI with Book Crops</title>
<style>
  :root {
    --bg: #0f172a; --card: #1e293b; --text: #f8fafc; --muted: #94a3b8;
    --border: #334155; --accent: #38bdf8; --green: #22c55e; --orange: #f97316;
  }
  body { font-family: system-ui, -apple-system, sans-serif; background: var(--bg); color: var(--text); margin: 0; padding: 24px; }
  h1 { margin-top: 0; font-size: 24px; color: var(--accent); display: flex; justify-content: space-between; align-items: center; }
  .stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 16px; margin-bottom: 24px; }
  .stat-card { background: var(--card); border: 1px solid var(--border); padding: 16px; border-radius: 8px; text-align: center; }
  .stat-val { font-size: 28px; font-weight: bold; color: var(--accent); }
  .stat-lbl { font-size: 13px; color: var(--muted); text-transform: uppercase; margin-top: 4px; }
  .toolbar { background: var(--card); border: 1px solid var(--border); padding: 16px; border-radius: 8px; margin-bottom: 24px; display: flex; gap: 12px; align-items: center; flex-wrap: wrap; }
  input, select, button { background: var(--bg); color: var(--text); border: 1px solid var(--border); padding: 8px 12px; border-radius: 6px; font-size: 14px; }
  input[type="text"] { flex: 1; min-width: 250px; }
  button { background: var(--accent); color: #000; font-weight: 600; cursor: pointer; border: none; }
  button:hover { opacity: 0.9; }
  table { width: 100%; border-collapse: collapse; background: var(--card); border: 1px solid var(--border); border-radius: 8px; overflow: hidden; }
  th, td { padding: 12px 16px; text-align: left; border-bottom: 1px solid var(--border); font-size: 14px; vertical-align: middle; }
  th { background: #111827; color: var(--muted); font-weight: 600; text-transform: uppercase; font-size: 12px; }
  tr:hover { background: rgba(56, 189, 248, 0.04); }
  .badge { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 12px; font-weight: 600; margin-right: 2px; }
  .badge-v1 { background: #312e81; color: #818cf8; }
  .badge-v2 { background: #1e3a8a; color: #60a5fa; }
  .badge-eng { background: #14532d; color: #4ade80; }
  .actions button { margin-right: 4px; padding: 4px 8px; font-size: 12px; background: var(--bg); border: 1px solid var(--border); color: var(--text); }
  .actions button.active { background: var(--accent); color: #000; border-color: var(--accent); }
  .crop-img { border: 1px solid var(--border); border-radius: 4px; background: #fff; max-height: 50px; cursor: zoom-in; }
  .footer { margin-top: 24px; text-align: center; color: var(--muted); font-size: 13px; }
  .tab-bar { display: flex; gap: 8px; margin-bottom: 16px; }
  .tab-btn { background: var(--card); color: var(--muted); border: 1px solid var(--border); padding: 8px 16px; border-radius: 6px; cursor: pointer; }
  .tab-btn.active { background: var(--accent); color: #000; font-weight: bold; border-color: var(--accent); }
</style>
</head>
<body>
  <h1>
    <span>TPB Set-C Certification & Audit UI (with Book Crops)</span>
    <button onclick="exportCSV()">Export Certified CSV</button>
  </h1>

  <div class="stats">
    <div class="stat-card">
      <div class="stat-val">__TIES_LEN__</div>
      <div class="stat-lbl">Set C Genuine Ties</div>
    </div>
    <div class="stat-card">
      <div class="stat-val">__AUDIT_LEN__</div>
      <div class="stat-lbl">Audit Sample (Auto-resolved)</div>
    </div>
    <div class="stat-card">
      <div class="stat-val" id="certified-count">0</div>
      <div class="stat-lbl">Certified in Session</div>
    </div>
  </div>

  <div class="tab-bar">
    <button class="tab-btn active" onclick="switchTab('ties')">Set C Genuine Ties (__TIES_LEN__)</button>
    <button class="tab-btn tab-audit" onclick="switchTab('audit')">Auto-Resolved Audit Sample (__AUDIT_LEN__)</button>
  </div>

  <div class="toolbar">
    <input type="text" id="search" placeholder="Filter by rubric, remedy, or page..." oninput="filterTable()">
    <span id="row-count" style="color: var(--muted); font-size: 13px; margin-left: auto;"></span>
  </div>

  <div id="table-container">
    <table id="data-table">
      <thead>
        <tr>
          <th>Page</th>
          <th>Rubric / Remedy</th>
          <th>Printed Book Crop (Red Box = Target)</th>
          <th>Signals (v1 | v2 | Eng)</th>
          <th>Certify Final Grade</th>
        </tr>
      </thead>
      <tbody id="tbody"></tbody>
    </table>
  </div>

  <div class="footer">
    TPB 1891 Typeface-Rank OCR Project &bull; Data preserved in <code>out/verify/</code>
  </div>

<script>
  const ties = __TIES_JSON__;
  const audit = __AUDIT_JSON__;
  let currentTab = 'ties';
  const certified = {};

  function switchTab(tab) {
    currentTab = tab;
    document.querySelectorAll('.tab-btn').forEach(b => {
      const isTies = b.textContent.includes('Ties');
      b.classList.toggle('active', tab === 'ties' ? isTies : !isTies);
    });
    filterTable();
  }

  function renderTable(data) {
    const tbody = document.getElementById('tbody');
    tbody.innerHTML = '';
    let count = 0;

    data.forEach((row) => {
      const key = currentTab + '_' + row.page + '_' + row.rubric + '_' + row.remedy;
      const finalGrade = certified[key] || row.v2;

      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td><b>p.${row.page}</b></td>
        <td>
          <div style="font-weight: 600; color: var(--accent);">${row.remedy}</div>
          <div style="font-size: 12px; color: var(--muted);">${row.rubric}</div>
        </td>
        <td>
          ${row.img ? `<img src="${row.img}" class="crop-img" onclick="this.style.maxHeight=this.style.maxHeight==='200px'?'50px':'200px'" title="Click to expand/collapse">` : '<span style="color:var(--muted)">No crop</span>'}
        </td>
        <td>
          <span class="badge badge-v1" title="1st Vision">v1:${row.v1}</span>
          <span class="badge badge-v2" title="2nd Revision">v2:${row.v2}</span>
          <span class="badge badge-eng" title="Engine Majority">eng:${row.eng}</span>
        </td>
        <td class="actions">
          ${['5 (C)', '4 (A)', '3 (I)', '2 (R)', '1 (P)'].map(g => {
            const code = g[4];
            const isSel = finalGrade == code || finalGrade == g[0];
            return `<button class="${isSel ? 'active' : ''}" onclick="setGrade('${key}', '${code}', this)">${g}</button>`;
          }).join('')}
        </td>
      `;
      tbody.appendChild(tr);
      count++;
    });

    document.getElementById('row-count').textContent = `Showing ${count} items`;
    document.getElementById('certified-count').textContent = Object.keys(certified).length;
  }

  function setGrade(key, grade, btn) {
    certified[key] = grade;
    Array.from(btn.parentElement.children).forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    document.getElementById('certified-count').textContent = Object.keys(certified).length;
  }

  function filterTable() {
    const q = document.getElementById('search').value.toLowerCase();
    const data = currentTab === 'ties' ? ties : audit;
    const filtered = data.filter(r =>
      r.rubric.toLowerCase().includes(q) ||
      r.remedy.toLowerCase().includes(q) ||
      String(r.page).includes(q)
    );
    renderTable(filtered);
  }

  function exportCSV() {
    const data = currentTab === 'ties' ? ties : audit;
    let csvContent = "data:text/csv;charset=utf-8,page,rubric,remedy,certified_grade,v1,v2,eng,reasons\\n";
    data.forEach(r => {
      const key = currentTab + '_' + r.page + '_' + r.rubric + '_' + r.remedy;
      const g = certified[key] || r.v2;
      csvContent += `"${r.page}","${r.rubric.replace(/"/g,'""')}","${r.remedy}","${g}","${r.v1}","${r.v2}","${r.eng}","${r.reasons.replace(/"/g,'""')}"\\n`;
    });
    const encodedUri = encodeURI(csvContent);
    const link = document.createElement("a");
    link.setAttribute("href", encodedUri);
    link.setAttribute("download", `tpb_certified_${currentTab}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  }

  filterTable();
</script>
</body>
</html>
"""

    html_out = (html_template
                .replace("__TIES_LEN__", f"{len(ties_data):,}")
                .replace("__AUDIT_LEN__", f"{len(audit_data):,}")
                .replace("__TIES_JSON__", json.dumps(ties_data, ensure_ascii=False))
                .replace("__AUDIT_JSON__", json.dumps(audit_data, ensure_ascii=False)))

    os.makedirs(VERIFY, exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(html_out)
    print("Wrote book-crop-embedded certification UI dashboard to:", OUT)


if __name__ == "__main__":
    main()
