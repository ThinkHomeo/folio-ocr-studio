# Troubleshooting Folio OCR Studio

For installation, start with [INSTALLATION.md](INSTALLATION.md). For upload,
review and export, use [APPLICATION.md](../APPLICATION.md).

## Python is missing, too old or 32-bit

Install Python 3.10+ **64-bit** from
[python.org](https://www.python.org/downloads/windows/), select **Add Python to PATH**,
then reopen `setup_folio.bat`. Closing and reopening the launcher lets it
see updated environment settings. The batch launcher does not require changing
PowerShell's execution policy.

## Packages are installed elsewhere, but Setup reports a missing local environment

Python packages belong to the environment into which they were installed.
A package in one app's environment is not automatically present in another.

When the standalone wizard identifies a running Folio instance, it checks the
environment actually used by that app. A separate uncreated `.venv` is described
as a portable setup option. When no app is running and no local environment
exists, package cards show **Not checked** until Setup creates it.

Read the **Python environment locations** section. For a portable installation,
save work, stop Folio and use **Install / repair packages** in standalone Setup.

## A package exists but cannot import / a DLL is missing

The checker imports packages in isolated probes to catch broken dependencies.
Save work, stop the app and use **Install / repair packages**. Read the installer
output and recheck after it finishes. If the same error remains, record the
Python architecture, package version and error message when reporting an issue.

## Installation buttons are disabled

The app's **System setup** screen is read-only, and the standalone wizard blocks
package changes while Folio is running. Save corrections and finish OCR first,
stop the app, then open `setup_folio.bat` to install or repair dependencies.

## Tesseract is missing / Windows Package Manager is unavailable

Use the manual installer link in Setup. Configure an installation in PATH or
set `TESSERACT_CMD` before starting the launcher, then recheck. See
[Tesseract configuration](INSTALLATION.md#tesseract-and-language-locations).

## English works but Hindi OCR fails

Choose **Download English + Hindi** in standalone Setup, then recheck. The Hindi
pack must load successfully in Tesseract; a file with the right name can still
be corrupt. Hindi mode needs `hin`; English + Hindi needs both `eng` and `hin`.
The language choice recognises the source text; it does not translate it.

## Format-aware models show missing or optional

Text OCR still works. For the TPB profile, supply trusted `mlp_model.pkl` and
`shape_model.pkl` files in `out/` or another configured model folder.
Missing classifier evidence remains subject to review. Presence alone is not
a successful recognition or compatibility test.

## The app or Setup port is busy

Use the URL of the existing instance, close its own server window when finished,
or choose another port:

```powershell
.\run_app.bat --app-port 8791
.\setup_folio.bat --port 8792
```

Only one normal Folio instance can run from the same project folder at a time.

## Upload failed / OCR output looks wrong

- Use clear, correctly oriented original scans and inspect the page layout.
- Supported formats are PNG, JPEG, WEBP, TIFF, JP2 and PDF.
- Limits are 100 files, 500 MB total, 500 pages and 90 megapixels per page.
- For Text OCR, select the correct language and try a suitable layout option.
- For structured OCR, generated rank-box overlays are not clean source scans;
  upload the original page.
- Format-aware recognition is limited to the current TPB 1891 profile.

The app targets printed text. Handwriting, damaged scans and complex layouts
may need substantial manual correction. Independent accuracy measurements
require a representative, held-out source set.

## Printed page numbers do not match the uploaded page count

First page labels the first uploaded page, including zero. Last page can be
left blank. Numbering does not select a subset of a PDF. If the actual count
differs from the expected range, Folio keeps all scanned pages and shows a notice.

## Save failed or a review is stale

Check that the server is running and a reviewer name is filled in. Stale writes
can return a conflict. Keep your unsaved correction safe before reloading the
latest document state, then compare and apply it again. Failed UI saves retain
edited fields. Do not navigate away without resolving unsaved changes.

## Export is disabled or contains fewer pages/rows than expected

Wait for OCR to finish and save your edits. **Draft** includes extracted content;
**Human reviewed** includes saved reviews only. A zero-row selection disables
export. SQLite and SQL are available for reviewed Format-aware entries only.
Use Text OCR for TXT, Word and text JSON exports.

## A document cannot be deleted

Processing documents cannot be deleted until OCR finishes. Export anything you
want to keep first: confirmed deletion permanently removes that document's scans,
text and review history.

## OCR was interrupted by a server restart

Completed pages remain saved, but the interrupted job is marked failed on
restart. Upload the source again to rerun it. Automatic resumable OCR is future work.

## GitHub Actions does not appear after browser upload

Verify that `.github/workflows/checks.yml` exists at that exact repository path.
If the folder was omitted, use **Add file → Create new file**, enter that full
path, paste the local workflow file's contents and commit. Do not create a
root-level `checks.yml`. See [GitHub upload guide](GITHUB_UPLOAD.md).

## Logs and useful checks

Setup writes `setup-status.log` and `setup-command.log` locally. Use the page's
error/log section for details. Review logs for private local paths before sharing.

```powershell
python setup_folio.py --check
.\.venv\Scripts\python.exe -m formatocr --check-dependencies
```

When opening an [issue](https://github.com/ThinkHomeo/folio-ocr-studio/issues),
include version, mode, language, steps and relevant errors with a shareable sample.
