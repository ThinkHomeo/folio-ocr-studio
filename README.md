# Folio OCR Studio

**Turn scanned pages into editable documents.** A project by
[**ThinkHomeo.in**](https://thinkhomeo.in/).

Folio is a local browser application for uploading scans or PDFs, checking OCR
against the original pages, saving corrections and exporting documents.
English and Hindi recognition are supported through Tesseract language packs.

## What you can do

| Mode | Purpose | Export formats |
| --- | --- | --- |
| **Text OCR** | Books, notes and printed documents | TXT, Word (DOCX), JSON |
| **Format-aware OCR** | Printed entries using the TPB 1891 profile | JSON, CSV, reviewed SQLite and SQL |

- Upload PNG, JPEG, WEBP, TIFF, JP2 or PDF files.
- Number pages from any printed page number, including zero.
- Compare scans with extracted text and retain saved review history.
- Search, rename and delete completed documents.
- Check dependencies and see installation progress in the Setup screen.
- Keep OCR processing, scans and saved documents on your computer.

Format-aware recognition is specific to the current TPB 1891 profile. Review
OCR results against the source before relying on them.

## Quick start on Windows

1. Download the repository with **Code → Download ZIP** and extract it.
2. Double-click **setup_folio.bat**.
3. If requested, install **Python 3.10 or newer, 64-bit** from
   [python.org](https://www.python.org/downloads/windows/), with
   **Add Python to PATH** selected, then run Setup again.
4. Use Setup to install app packages, Tesseract and English/Hindi language data.
5. When required checks are ready, click **Start Folio**, then **Open Folio**.

For later sessions, double-click **run_app.bat**. Keep its command window open.
The default app address is [http://127.0.0.1:8788/](http://127.0.0.1:8788/);
the standalone Setup address is
[http://127.0.0.1:8790/](http://127.0.0.1:8790/).

To use another app port:

```powershell
.\run_app.bat --app-port 8791
```

**हिन्दी में:** ZIP निकालें और **setup_folio.bat** चलाएँ। Setup में दिखाई गई
ज़रूरी dependencies install करें, फिर **Start Folio → Open Folio** चुनें।
अगली बार ऐप खोलने के लिए **run_app.bat** चलाएँ। स्कैन की भाषा **OCR language**
में चुनें।

First setup needs internet for downloads. OCR runs locally afterwards.
Windows launchers and automatic Tesseract installation are intended for Windows.

## Manual installation / development

Use Python 3.10+ with a separate environment. Install Tesseract 5 and the
language data you need. On Windows:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[test]"
.\.venv\Scripts\python.exe -m formatocr --port 8788
```

If Tesseract is installed in a nonstandard location, pass
`--tess "PATH-TO-TESSERACT"` or set `TESSERACT_CMD`.
The setup wizard installs dependencies from the ranges in `pyproject.toml`.
`requirements-lock.txt` is a snapshot of one previously validated environment;
it is not a universal lock file for every Python version and operating system.

The app uses loopback networking. This repository is a Python application;
GitHub Pages cannot run its OCR server.

## Documents, models and moving to another computer

A fresh installation stores documents in **app-data/**. An existing local
**dev-data/** folder is selected by the Windows launcher when present.
For a custom folder, use `run_app.bat --data-dir "YOUR-FOLDER"`.

Documents, scans, databases, logs, language packs and virtual environments are
excluded from Git and the prepared upload ZIP. To transfer saved documents,
stop the old server and copy the entire data folder separately, then recreate
the environment on the new computer.

**Text OCR works without classifier models.** For Format-aware OCR, copy trusted
`mlp_model.pkl` and `shape_model.pkl` files into **out/** or use `--models PATH`.
The repository does not bundle those optional models; see [out/README.md](out/README.md).
Setup can download English and Hindi language packs.

## Verification

The Python suite uses temporary workspaces, generated images and mocked OCR,
and the UI controller checks run offline. They do not replace a real scan
benchmark or browser layout review.

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
node --test tests/test_review_ui.cjs tests/test_setup_ui.cjs
python tools/prepare_github.py
```

Node.js 22+ is needed only for the UI controller tests. GitHub Actions runs the
checks on Windows with Python 3.10 and 3.12 after the repository is uploaded.

## Project layout and documentation

| Location | Contents |
| --- | --- |
| `formatocr/` | Local app, persistence, exports, Setup checks and browser UI |
| `tpbocr/` | TPB recognition engine and legacy research scripts |
| `tests/` | Python regression and offline UI controller checks |
| `setup_folio.py` | Dependency wizard using the Python standard library |
| `tools/prepare_github.py` | Clean source ZIP and file/hash manifest |
| [APPLICATION.md](APPLICATION.md) | Detailed upload, review, export and setup guide |
| [docs/GITHUB_UPLOAD.md](docs/GITHUB_UPLOAD.md) | Upload instructions in Hindi |
| [docs/RESEARCH.md](docs/RESEARCH.md) | Historical prototype notes |
| [ARCHITECTURE_REVIEW.md](ARCHITECTURE_REVIEW.md) | Historical architecture assessment |

Legacy research scripts may require external datasets and training artifacts
that are not in this repository. The optional BBCR translation reference can
be configured with `BBCR_HI_PATH`; otherwise those scripts check the sibling
`bbcr-repertory/output/rubrics_hi.json` path. These scripts are separate from
the normal Folio application workflow.

## Attribution and license

Visit [ThinkHomeo.in](https://thinkhomeo.in/) for the project website.
An open-source license has not yet been selected; see [NOTICE.md](NOTICE.md)
for attribution and the existing reference-data provenance.
