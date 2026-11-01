# -*- coding: utf-8 -*-
import json, os, sys

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

VERIFY = os.path.join('.', 'out', 'verify')
data_path = os.path.join(VERIFY, '_cert_data_v2.json')
if not os.path.exists(data_path):
    print("Error: _cert_data_v2.json not found")
    sys.exit(1)

data = json.load(open(data_path, encoding='utf-8'))
conflicts = data.get('conflicts', [])
ties = data.get('ties', [])

print(f"Building UI: {len(conflicts)} conflicts + {len(ties)} ties")

html_template = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>TPB Final Verification: Conflicts + Ties</title>
<style>
  :root {
    --bg: #0f172a; --card: #1e293b; --text: #f8fafc; --muted: #94a3b8;
    --border: #334155; --accent: #38bdf8; --green: #22c55e; --orange: #f97316; --red: #ef4444;
  }
  * { box-sizing: border-box; }
  body { font-family: system-ui, -apple-system, sans-serif; background: var(--bg); color: var(--text); margin: 0; padding: 20px; }
  h1 { margin: 0 0 16px; font-size: 22px; color: var(--accent); display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 8px; }
  .stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; margin-bottom: 20px; }
  .stat-card { background: var(--card); border: 1px solid var(--border); padding: 14px; border-radius: 8px; text-align: center; }
  .stat-val { font-size: 26px; font-weight: bold; color: var(--accent); }
  .stat-lbl { font-size: 12px; color: var(--muted); text-transform: uppercase; margin-top: 4px; }
  .tab-bar { display: flex; gap: 6px; margin-bottom: 14px; }
  .tab-btn { background: var(--card); color: var(--muted); border: 1px solid var(--border); padding: 8px 14px; border-radius: 6px; cursor: pointer; font-size: 13px; }
  .tab-btn.active { background: var(--accent); color: #000; font-weight: bold; border-color: var(--accent); }
  .toolbar { background: var(--card); border: 1px solid var(--border); padding: 12px; border-radius: 8px; margin-bottom: 16px; display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }
  input[type=text] { background: var(--bg); color: var(--text); border: 1px solid var(--border); padding: 8px 10px; border-radius: 6px; font-size: 13px; flex: 1; min-width: 200px; }
  select { background: var(--bg); color: var(--text); border: 1px solid var(--border); padding: 6px 8px; border-radius: 6px; font-size: 13px; }
  button { background: var(--accent); color: #000; font-weight: 600; cursor: pointer; border: none; padding: 8px 12px; border-radius: 6px; font-size: 13px; }
  button:hover { opacity: 0.9; }
  table { width: 100%; border-collapse: collapse; background: var(--card); border: 1px solid var(--border); border-radius: 8px; overflow: hidden; }
  th, td { padding: 10px 12px; text-align: left; border-bottom: 1px solid var(--border); font-size: 13px; vertical-align: middle; }
  th { background: #111827; color: var(--muted); font-weight: 600; text-transform: uppercase; font-size: 11px; }
  tr:hover { background: rgba(56, 189, 248, 0.04); }
  .badge { display: inline-block; padding: 2px 7px; border-radius: 4px; font-size: 11px; font-weight: 600; margin-right: 2px; }
  .badge-v1 { background: #312e81; color: #818cf8; }
  .badge-v2 { background: #1e3a8a; color: #60a5fa; }
  .badge-eng { background: #14532d; color: #4ade80; }
  .badge-conflict { background: #7f1d1d; color: #fca5a5; }
  .actions button { margin-right: 3px; padding: 3px 7px; font-size: 11px; background: var(--bg); border: 1px solid var(--border); color: var(--text); }
  .actions button.active { background: var(--accent); color: #000; border-color: var(--accent); font-weight: bold; }
  .crop-img { border: 1px solid var(--border); border-radius: 4px; background: #fff; max-height: 50px; cursor: zoom-in; }
  .footer { margin-top: 20px; text-align: center; color: var(--muted); font-size: 12px; }
  .hint { font-size: 12px; color: var(--orange); margin-bottom: 12px; padding: 8px 12px; background: rgba(249, 115, 22, 0.1); border: 1px solid rgba(249, 115, 22, 0.3); border-radius: 6px; }
</style>
</head>
<body>
  <h1>
    <span>TPB Final Verification (Conflicts + Set-C Ties)</span>
    <button onclick="exportCSV()">Export Certified CSV</button>
  </h1>
  <div class="hint">
    <b>निर्देश:</b> Red box वाले printed crop को देखें:
    <br>• <b>5 (C)</b> = ALL CAPITALS (बड़े अक्षर)
    <br>• <b>4 (A)</b> = Antique (मोटे, सीधे / Bold Roman)
    <br>• <b>3 (I)</b> = Italic (तिरछे)
    <br>• <b>2 (R)</b> = Roman (सामान्य पतले, सीधे)
    <br>• <b>1 (P)</b> = Parentheses (कोष्ठक में)
    <br>बटन दबाकर ग्रेड सेट करें, फिर ऊपर <b>"Export Certified CSV"</b> दबाकर डाउनलोड करें।
  </div>
  <div class="stats">
    <div class="stat-card"><div class="stat-val">__CONF_LEN__</div><div class="stat-lbl">Grade Conflicts (Duplicates)</div></div>
    <div class="stat-card"><div class="stat-val">__TIES_LEN__</div><div class="stat-lbl">Set-C Genuine Ties</div></div>
    <div class="stat-card"><div class="stat-val" id="certified-count">0</div><div class="stat-lbl">Certified This Session</div></div>
    <div class="stat-card"><div class="stat-val" id="remaining-count">0</div><div class="stat-lbl">Remaining</div></div>
  </div>
  <div class="tab-bar">
    <button class="tab-btn active" onclick="switchTab('conflicts')">Grade Conflicts (__CONF_LEN__)</button>
    <button class="tab-btn" onclick="switchTab('ties')">Set-C Ties (__TIES_LEN__)</button>
    <button class="tab-btn" onclick="switchTab('all')">All (__ALL_LEN__)</button>
  </div>
  <div class="toolbar">
    <input type="text" id="search" placeholder="Filter by rubric, remedy, or page..." oninput="filterTable()">
    <select id="grade-filter" onchange="filterTable()">
      <option value="">All Grades</option>
      <option value="5">5 (CAPITALS)</option>
      <option value="4">4 (Antique)</option>
      <option value="3">3 (Italic)</option>
      <option value="2">2 (Roman)</option>
      <option value="1">1 (paren)</option>
    </select>
    <select id="status-filter" onchange="filterTable()">
      <option value="">All Status</option>
      <option value="uncert">Uncertified Only</option>
      <option value="cert">Certified Only</option>
    </select>
    <span id="row-count" style="color:var(--muted);font-size:12px;margin-left:auto"></span>
  </div>
  <div id="table-container">
    <table><thead><tr>
      <th>Page</th><th>Rubric / Remedy</th><th>Book Crop</th><th>Signals</th><th>Certify Grade</th>
    </tr></thead><tbody id="tbody"></tbody></table>
  </div>
  <div class="footer">TPB 1891 Typeface-Rank &bull; Verification UI Dashboard</div>

<script>
  const conflicts = __CONF_JSON__;
  const ties = __TIES_JSON__;
  const allData = conflicts.map(r => ({...r, type: 'conflict'})).concat(ties.map(r => ({...r, type: 'tie'})));
  let currentTab = 'conflicts';
  const certified = {};

  function switchTab(tab) {
    currentTab = tab;
    document.querySelectorAll('.tab-btn').forEach((b, i) => {
      b.classList.toggle('active', (tab === 'conflicts' && i === 0) || (tab === 'ties' && i === 1) || (tab === 'all' && i === 2));
    });
    filterTable();
  }

  function getData() {
    if (currentTab === 'conflicts') return conflicts.map(r => ({...r, type: 'conflict'}));
    if (currentTab === 'ties') return ties.map(r => ({...r, type: 'tie'}));
    return allData;
  }

  function rkey(r) { return r.type + '_' + r.page + '_' + r.rubric + '_' + r.remedy; }

  function filterTable() {
    const q = document.getElementById('search').value.toLowerCase();
    const gf = document.getElementById('grade-filter').value;
    const sf = document.getElementById('status-filter').value;
    let data = getData().filter(r =>
      (r.rubric.toLowerCase().includes(q) || r.remedy.toLowerCase().includes(q) || String(r.page).includes(q))
    );
    if (gf) data = data.filter(r => String(r.v1) === gf || String(r.v2) === gf || String(r.eng) === gf);
    if (sf === 'uncert') data = data.filter(r => !certified[rkey(r)]);
    if (sf === 'cert') data = data.filter(r => !!certified[rkey(r)]);
    renderTable(data);
  }

  function renderTable(data) {
    const tbody = document.getElementById('tbody');
    tbody.innerHTML = '';
    data.forEach(row => {
      const key = rkey(row);
      const fg = certified[key] || '';
      const tr = document.createElement('tr');
      const typeTag = row.type === 'conflict' ?
        '<span class="badge badge-conflict">CONFLICT</span>' :
        '<span class="badge badge-v2">TIE</span>';

      const cropHtml = row.img ?
        '<img src="' + row.img + '" class="crop-img" onclick="this.style.maxHeight=this.style.maxHeight===\\'200px\\'?\\'50px\\':\\'200px\\'" title="Click to zoom">' :
        '<span style="color:var(--muted)">No crop</span>';

      const grades = ['5 (C)', '4 (A)', '3 (I)', '2 (R)', '1 (P)'];
      let btns = '';
      grades.forEach(g => {
        const code = g[0];
        const isSel = (fg === code);
        btns += '<button class="' + (isSel ? 'active' : '') + '" onclick="setGrade(\\'' + key + '\\', \\'' + code + '\\', this)">' + g + '</button>';
      });

      tr.innerHTML = '<td><b>p.' + row.page + '</b></td>' +
        '<td><div style="font-weight:600;color:var(--accent)">' + row.remedy + '</div>' +
        '<div style="font-size:11px;color:var(--muted)">' + row.rubric + '</div>' + typeTag + '</td>' +
        '<td>' + cropHtml + '</td>' +
        '<td><span class="badge badge-v1">v1:' + row.v1 + '</span> <span class="badge badge-v2">v2:' + row.v2 + '</span> <span class="badge badge-eng">eng:' + row.eng + '</span></td>' +
        '<td class="actions">' + btns + '</td>';
      tbody.appendChild(tr);
    });

    document.getElementById('row-count').textContent = 'Showing ' + data.length + ' items';
    const certCount = Object.keys(certified).length;
    document.getElementById('certified-count').textContent = certCount;
    document.getElementById('remaining-count').textContent = (conflicts.length + ties.length) - certCount;
  }

  function setGrade(key, grade, btn) {
    certified[key] = grade;
    Array.from(btn.parentElement.children).forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    const certCount = Object.keys(certified).length;
    document.getElementById('certified-count').textContent = certCount;
    document.getElementById('remaining-count').textContent = (conflicts.length + ties.length) - certCount;
  }

  function exportCSV() {
    let csv = 'page,rubric,remedy,certified_grade,type,v1,v2,eng,reasons\\n';
    allData.forEach(r => {
      const key = rkey(r);
      const g = certified[key] || '';
      csv += '"' + r.page + '","' + r.rubric.replace(/"/g, '""') + '","' + r.remedy + '","' + g + '","' + r.type + '","' + r.v1 + '","' + r.v2 + '","' + r.eng + '","' + (r.reasons || '').replace(/"/g, '""') + '"\\n';
    });
    const blob = new Blob([csv], {type: 'text/csv;charset=utf-8;'});
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'tpb_certified_v2.csv';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }

  filterTable();
</script>
</body>
</html>"""

html = (html_template
    .replace('__CONF_LEN__', str(len(conflicts)))
    .replace('__TIES_LEN__', str(len(ties)))
    .replace('__ALL_LEN__', str(len(conflicts) + len(ties)))
    .replace('__CONF_JSON__', json.dumps(conflicts, ensure_ascii=False))
    .replace('__TIES_JSON__', json.dumps(ties, ensure_ascii=False)))

out_path = os.path.join(VERIFY, 'cert_ui_v2.html')
with open(out_path, 'w', encoding='utf-8') as f:
    f.write(html)

print("SUCCESS: Wrote", out_path)
print("File size:", os.path.getsize(out_path) // 1024, "KB")
