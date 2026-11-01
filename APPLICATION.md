# Folio · Local OCR Studio

A project by **[ThinkHomeo.in](https://thinkhomeo.in/)**.

Folio converts scanned books, notes and documents into editable text. Compare each result with its original scan, save corrections and export your document. Processing and stored scans stay on this computer.

## Start

Open this project's `run_app.bat` and keep its command window open. It checks the project-local `.venv` before starting http://127.0.0.1:8788. Missing requirements open the separate setup wizard. The launcher no longer borrows another project's environment or relies on this computer's old folder names. If an older server uses that port, close its window first.

On a new Windows computer, double-click **setup_folio.bat** first. If Python is missing, the launcher shows the official download page and installation instructions. Install Python 3.10+ (64-bit), select **Add Python to PATH**, then rerun setup. The batch launcher does not require changing PowerShell's execution policy.

The setup wizard runs on http://127.0.0.1:8790 using only Python's standard library, even when FastAPI and the other app packages are absent. It shows:

- Python version/architecture and nine app packages, including version compatibility and isolated import checks.
- Tesseract 5+, with real English/Hindi language-load checks rather than filename checks alone.
- Optional local TPB 1891 model files, with clear file-presence versus model-validation limits.
- **Install / repair packages**, **Install Tesseract** through winget, and **Download English + Hindi** from the Tesseract project's tessdata_fast repository.
- Live installer output, download sizes, completed/failed states, retry, and persistent `setup-status.log` / `setup-command.log` files.

Language packs are verified with Tesseract before being placed in the project-local `tessdata` folder. They do not require writing to Program Files. If winget is unavailable, use the manual installer link and recheck. Package installation uses PyPI and repairs the local environment; first setup needs internet.

The header's **System setup** opens dependency status for the running app in a separate tab. Installation is disabled there: close the server and run `setup_folio.bat` to change dependencies. A process lock also prevents the setup wizard from replacing files used by a running Folio instance.

The standalone setup wizard also detects a running Folio instance and checks its actual Python environment. A working app may use an existing environment even when this folder's separate `.venv` has not been created. That local folder is shown separately as a portable setup option, not as proof that packages are missing from the computer. When no Folio instance is running, the wizard checks the local `.venv`; without one, package checks show **Not checked** until setup creates it. Python packages belong to individual environments, so an installation in one does not automatically become available in another.

After setup, click **Start Folio**, then **Open Folio**. An app started by the wizard can be stopped with **Stop Folio** in that same setup window; save work and finish OCR first. Alternatively, close setup and use `run_app.bat` for the usual foreground server. `run_app.bat --app-port 8791 --data-dir dev-data` selects a different port/data folder; `setup_folio.bat --port 8792` selects a different setup port.

Manual start from this project folder:

```powershell
.\.venv\Scripts\python.exe -m formatocr --port 8788 --tess "C:\Program Files\Tesseract-OCR\tesseract.exe"
```

The service listens on loopback only. `app-data/` stores original uploads, rendered pages, jobs and review history. The launcher chooses `dev-data/` when present; otherwise it uses `app-data/`. Direct `python -m formatocr` uses `app-data/` unless `--data-dir PATH` is specified. Use `--models PATH` for trusted `mlp_model.pkl` and `shape_model.pkl` classifiers. `TESSERACT_CMD` can select another installed executable; the local complete language pack is automatically selected when both language files are present.

To move to another computer, copy the app folder, optional `out/` models and `tessdata/` language packs, but recreate `.venv` with setup. To retain documents, stop the old server before copying the entire data folder, including scans and SQLite files. This is a setup wizard, not a standalone EXE installer.

## 1. Add scanned pages · स्कैन जोड़ें

Click **Add scanned pages** to open the upload form.

| Mode | Use it for | Exports |
| --- | --- | --- |
| **Text OCR** (default) | General books, notes and printed documents; editable page text | TXT, Word (DOCX), JSON |
| **Format-aware OCR** | Structured printed entries matching the current **TPB 1891 template** | JSON, CSV, SQLite, SQL |

Format-aware OCR currently has a TPB-specific recognition engine. Its general name does not imply arbitrary form, table or typeface recognition. Use Text OCR for general documents.

Enter a document title. Text OCR offers English, Hindi or English + Hindi, and Automatic, Single column or Uniform text block layout. Tesseract must have the chosen language data installed.

Set **Page numbering**:

- **First page:** the first printed page number, including `0`.
- **Last page:** the expected last printed page number. Leave it empty to calculate it automatically.
- Three scans starting at `0` receive numbers `0, 1, 2`.
- All uploaded pages are processed in selected file order. The range labels scans; it does not select a PDF subset or skip pages.
- Last page must be at least First page. If the actual page count differs, all scans are kept and Folio shows a notice with the actual range.

Choose PNG, JPEG, WEBP, TIFF, JP2 or PDF files in page order, then click **Start OCR**. The form shows file count, size and an estimated range for single-page images. PDF/TIFF page counts become available during OCR. Limits: 100 files, 500 MB total, 500 pages, 90 megapixels per page. PDFs render at 300 DPI; image dimensions and original files are retained, with EXIF orientation applied.

Chapter is optional in Format-aware upload/review. An empty Chapter produces a warning; exports keep it blank until assigned. Older jobs retain their historical chapter context. Duplicate document titles automatically receive a numeric suffix. Use workspace search and the document list/dropdown to open a document, or Rename/Delete to manage it. Processing documents cannot be deleted until OCR finishes.

## 2. Check and edit · जाँच और सुधार

OCR runs sequentially in one background worker. The job opens automatically and completed pages appear during processing. Wait for processing to finish before saving reviews or exporting.

For **Text OCR**, select a page and compare the scan with **Editable OCR text**. Correct the text, enter your reviewer name, then click **Save page** or **Save & next**. Ctrl+S saves; Alt+Left/Right changes pages. Empty or low-confidence pages are flagged. Unsaved edits trigger a discard prompt before changing pages, opening another document or adding scans.

For **Format-aware OCR**, select a box or queue entry. Inspect its crop, raw OCR, votes and measured features. Correct remedy, rubric and printed grade, then save with your reviewer name. Use **Exclude OCR noise** for false detections and **All tokens** for accepted proposals. The current template uses parentheses=1, roman=2, italic=3, antique/bold=4 and capitals=5. Missing models or uncertain identities require review.

**Save & Next** chooses the next incomplete token in document order. Previous/Skip traverses incomplete entries. Ctrl+S saves the current token without advancing; Ctrl+Enter saves and advances; Alt+Left/Right navigates; S skips when focus is outside an input. Unsaved-change prompts protect token/page/document transitions, and navigation waits for a pending save. Failed writes retain edited fields.

The queue renders 50 entries per page with status, reason and text filters. Batch selection persists through queue pagination and clears when changing scan pages/documents. Assign Chapter/Rubric to selected entries, the current filtered page queue, or all needs-attention entries in the document. An empty filtered batch changes nothing. Inherit copies Chapter/Rubric from the preceding contextual entry on the same page; save to apply it.

**Add missing token** draws a box on the scan and records remedy, rubric, grade and reviewer. It also works when OCR found no tokens. Esc cancels drawing. Split uses semicolon-separated remedies and partitions the existing box horizontally; confirm the inferred crops/grades against the scan. Merge combines selected entries on one page and preserves their boxes and history. A stale merge returns a conflict. A split without a rubric remains incomplete.

Correction and rename input forms use an app dialog, including in browsers that do not support native JavaScript prompts. Cancel/Esc leaves the operation unchanged.

Document percentage counts reviewed/excluded decisions; each page shows its own percentage. Next incomplete page finds a page with remaining work. Narrow layouts provide sticky Scan/Inspector/Queue controls, document search/dropdown and one active review panel. Interface labels use English consistently. The upload form's OCR language setting selects the language to recognise in your scans.

Each decision records reviewer, timestamp, note, old/new values and unchanged machine evidence. Stale saves return a conflict. If the server stops during OCR, completed pages remain; the interrupted job becomes failed on restart. Upload again to rerun it.

## 3. Export · डाउनलोड

Choose **Draft** for all extracted content or **Human reviewed** for saved content. Select a format and click **Export**.

The export preflight shows estimated entry/page rows, incomplete count and incompatible combinations. SQLite/SQL requires Human reviewed scope. A 0-row scope disables export. Preflight checks saved content; save edits before exporting them.

- **Text OCR:** TXT preserves page boundaries with form-feed separators; Word uses page breaks; JSON retains line boxes, confidence, source references and edit history.
- **Format-aware OCR:** JSON/CSV includes entry identity, grade, source references and verification status. Reviewed JSON retains machine evidence and selected entries' review history. SQLite/SQL requires reviewed entries and includes relational tables, provenance and audit events. SQL uses SQLite dialect.

The legacy chapter column remains in structured exports for compatibility and may be empty. Existing nonempty chapter values stay separate in relational exports. Human review records a decision; it does not guarantee OCR accuracy or complete segmentation.

## Installation and verification

Requires Python 3.10+, Tesseract 5 and language data:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[test]"
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

`requirements-lock.txt` records previously validated versions. Python regression tests cover persistence/conflicts, evidence retention, optional chapter context, reviewed-export filtering, relational foreign keys, TIFF/PDF ingestion, page zero/range mismatches, text review/export, document management, token correction, empty batches and segmentation. Run offline UI controller tests with `node --test tests/test_review_ui.cjs tests/test_setup_ui.cjs`; these verify workflow logic and do not verify browser rendering or mobile layout.

The bundled lexicon contains 649 entries labelled for TPB 1891; its included provenance is not an independent accuracy evaluation. Unknown or ambiguous identities remain reviewable. Historical rank datasets may use a reversed direction, so their grades are not imported automatically. Load pickle models only from trusted local training artifacts.

Remaining work includes independent held-out evaluation, automatic cross-page rubric hierarchy, resumable OCR and a standalone EXE installer. See `ARCHITECTURE_REVIEW.md` for earlier findings.
