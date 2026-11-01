# Installation and moving Folio to another computer

Folio by [Think Homeo](https://thinkhomeo.in) provides local Hindi and English
OCR, scanned-PDF review and document export. This guide covers Windows setup.
For everyday use, see [APPLICATION.md](../APPLICATION.md).

## Requirements

| Component | Needed for |
| --- | --- |
| Windows | Batch launchers and automatic dependency installation |
| Python 3.10+, 64-bit | Running Setup and the app |
| App Python packages | Browser server, page ingestion, recognition and exports |
| Tesseract 5+ | Text recognition |
| English language data (`eng`) | Required English OCR |
| Hindi language data (`hin`) | Hindi and mixed Hindi/English OCR |
| Trusted classifier models | Optional TPB format-aware recognition |
| Node.js 22+ | Developer UI checks only |

Initial installation needs internet access. The OCR workflow runs locally
after packages and language data are ready. The app is not a standalone EXE.

## Windows Setup: recommended

1. Download and extract the [source repository](https://github.com/ThinkHomeo/folio-ocr-studio),
   or clone it with Git.
2. Open the extracted project folder and double-click **setup_folio.bat**.
3. If Python is missing, install a 64-bit version from
   [python.org](https://www.python.org/downloads/windows/), with **Add Python to PATH**
   selected. Close the launcher window and open Setup again.
4. In Setup, use **Install / repair packages**. This creates a project-local
   `.venv` and installs the dependencies from `pyproject.toml`.
5. Use **Install Tesseract** if the OCR engine is missing. Automatic installation
   uses Windows Package Manager and may show an administrator prompt. The manual
   [Tesseract installer information](https://github.com/UB-Mannheim/tesseract/wiki)
   is linked in Setup.
6. Use **Download English + Hindi** to install the local language packs.
7. Click **Recheck dependencies**. When required components are ready, choose
   **Start Folio → Open Folio**.

Setup runs using Python's standard library, so the dependency screen can open
before FastAPI and other application packages are installed. Installer output,
progress and errors are shown in the page. Failed actions can be retried.

**हिन्दी में:** ZIP निकालें और **setup_folio.bat** चलाएँ। Python न होने पर पहले
Python install करें। Setup में packages, Tesseract और language data install
करें, फिर **Start Folio → Open Folio** चुनें। App चलाने के लिए Node.js की
आवश्यकता नहीं है।

## Start and stop later

Double-click **run_app.bat**. Keep its command window open while using Folio.
Save corrections and finish OCR before closing that window.

If Setup started the app, its **Stop Folio** button can stop that owned instance.
If another window started Folio, stop it through that server window instead.
The app header's **System setup** shows status in a separate tab; installation
is disabled while the app is running.

| Service | Default address |
| --- | --- |
| App | `http://127.0.0.1:8788/` |
| Standalone Setup | `http://127.0.0.1:8790/` |

For another port:

```powershell
.\run_app.bat --app-port 8791
.\setup_folio.bat --port 8792
```

The app and Setup use loopback networking. These addresses refer to the
computer on which Folio is running.

## Manual installation

Install Python and Tesseract separately, then run these commands from the
project folder:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e "."
.\.venv\Scripts\python.exe -m formatocr --check-dependencies
.\.venv\Scripts\python.exe -m formatocr --port 8788
```

For development and tests, install `".[test]"` instead of `"."`.
The dependency checker prints JSON and returns a nonzero exit code when
required components are not ready.

`requirements-lock.txt` records one previously validated environment. Normal
Setup uses compatible version ranges in `pyproject.toml`; the snapshot is not
a universal lock for every Python version and operating system.

## Tesseract and language locations

Folio checks configured paths, PATH and standard Windows installation locations.
For a custom executable location:

```powershell
$env:TESSERACT_CMD = "C:\Program Files\Tesseract-OCR\tesseract.exe"
.\run_app.bat
```

For direct Python startup, use `--tess PATH`.
Setup downloads English and Hindi data from the Tesseract project's
[tessdata_fast repository](https://github.com/tesseract-ocr/tessdata_fast)
into the project-local `tessdata/` folder and validates them with Tesseract.
The complete local English/Hindi pack is selected automatically.

## Optional format-aware models

Text OCR does not require the TPB classifier files. For Format-aware OCR, copy
trusted `mlp_model.pkl` and `shape_model.pkl` files into `out/`, or configure
`FORMAT_OCR_MODELS` / the direct app's `--models PATH` option.

These custom models have no configured public download URL. Setup checks
presence; compatibility and recognition quality need actual OCR validation.
See [out/README.md](../out/README.md).

## Data folders and transfer

A fresh installation uses `app-data/`. The batch launcher selects an existing
`dev-data/` folder when present. For another location:

```powershell
.\run_app.bat --data-dir "YOUR-DOCUMENT-FOLDER"
```

To move to another computer:

1. Save work and stop the old app.
2. Copy/download the source code onto the destination computer.
3. Copy the complete document data folder separately if saved work is needed.
   Keep its database, originals and rendered pages together.
4. Optionally copy trusted models and language packs separately.
5. Recreate `.venv` using Setup; do not reuse the old machine's environment.
6. Start Folio with the appropriate data folder and verify saved documents.

GitHub source archives exclude documents, scans, databases, logs, environments,
language packs and model binaries. Documentation screenshots are synthetic
examples and are included under `docs/images/`.

## If setup fails

Use [Troubleshooting](TROUBLESHOOTING.md) for missing Python, import/DLL errors,
Hindi language problems, busy ports and incomplete exports.
