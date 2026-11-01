# Contributing to Folio OCR Studio

Thank you for helping improve local Hindi and English OCR, scan review and
document export. Folio is a project by [Think Homeo](https://thinkhomeo.in).

## Report an issue

Use [GitHub Issues](https://github.com/ThinkHomeo/folio-ocr-studio/issues).
Include the app version, operating system, Python version, OCR mode and language,
what you expected, what happened, and the steps needed to reproduce it.

For recognition problems, describe scan resolution, orientation and page layout.
Use a synthetic or shareable sample. Do not attach private scans, reviewer
information, credentials or an entire document database.

## Set up development

Fork the repository, clone your fork, then create a branch for your change.
On Windows:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[test]"
.\.venv\Scripts\python.exe -m formatocr --port 8788
```

For actual recognition, install Tesseract 5 and the required language data.
The Windows Setup wizard is described in [Installation](docs/INSTALLATION.md).
Node.js 22+ is used for UI controller checks, not normal OCR operation.

## Verify your change

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
node --test tests/test_review_ui.cjs tests/test_setup_ui.cjs
python tools/prepare_github.py
```

Run checks relevant to the change. Review browser layout for visual changes.
When changing recognition, keep raw machine evidence and validate the change
against source scans; mocked regression tests do not establish OCR accuracy.

The archive script checks selected source files and keeps local documents,
models, language packs and QA evidence out of the upload ZIP. Documentation
screenshots belong in `docs/images/` and should use synthetic demonstration data.

## Submit a pull request

Explain the problem, resulting behavior and relevant verification. Keep changes
focused, update affected documentation, and preserve review history and source
provenance. Do not include generated datasets, private workspaces or model binaries.

Folio uses the [MIT License](LICENSE). Preserve existing third-party notices and
source labels; see [NOTICE.md](NOTICE.md).
