"""Dependency checks that work with the Python standard library alone.

Keep this module free of app/package imports: it is also used before setup.
"""
import importlib.metadata
import json
import os
import platform
import shutil
import struct
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYTHON_URL = "https://www.python.org/downloads/windows/"
TESSERACT_URL = "https://github.com/UB-Mannheim/tesseract/wiki"
LANGUAGE_URL = "https://github.com/tesseract-ocr/tessdata_fast"
# Shared by the installer and the checker; keep in sync with pyproject.toml.
PACKAGES = (
    ("numpy", "numpy", "1.26", "3"),
    ("Pillow", "PIL", "10", "13"),
    ("opencv-python-headless", "cv2", "4.10", "6"),
    ("pytesseract", "pytesseract", "0.3.13", "1"),
    ("scikit-learn", "sklearn", "1.5", "2"),
    ("fastapi", "fastapi", "0.115", "1"),
    ("uvicorn", "uvicorn", "0.30", "1"),
    ("python-multipart", "python_multipart", "0.0.18", "1"),
    ("pypdfium2", "pypdfium2", "4.30", "6"),
)


def run_capture(command, timeout=30, **kwargs):
    if os.name == "nt":
        kwargs.setdefault("creationflags", subprocess.CREATE_NO_WINDOW)
    return subprocess.run(command, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=timeout, **kwargs)


def local_python(root=ROOT):
    root = Path(root)
    return root / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def resolve_tesseract(explicit=None):
    configured = explicit or os.environ.get("TESSERACT_CMD")
    if configured:
        return shutil.which(str(configured)) or str(configured)
    found = shutil.which("tesseract")
    if found:
        return found
    candidates = [Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Tesseract-OCR/tesseract.exe",
                  Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "Programs/Tesseract-OCR/tesseract.exe"]
    return str(next((p for p in candidates if p.is_file()), candidates[0]))


def tessdata_path(root=ROOT):
    """Prefer the complete local language pack; otherwise honour the user's setting."""
    folder = Path(root) / "tessdata"
    if all((folder / f"{lang}.traineddata").is_file() for lang in ("eng", "hin")):
        return str(folder)
    return os.environ.get("TESSDATA_PREFIX") or None


def runtime_environment(root=ROOT):
    env = os.environ.copy()
    folder = tessdata_path(root)
    if folder:
        env["TESSDATA_PREFIX"] = folder
    return env


def _package_probe():
    """Import each package to catch broken DLLs and incompatible installations."""
    import importlib
    from packaging.version import Version
    result = []
    for name, module, minimum, maximum in PACKAGES:
        version, error = None, None
        try:
            version = importlib.metadata.version(name)
            if not Version(minimum) <= Version(version) < Version(maximum):
                raise ValueError(f"Version {version} is outside >= {minimum}, < {maximum}")
            importlib.import_module(module)
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"[:500]
        result.append({"id": name, "name": name, "version": version,
                       "required": True, "status": "error" if error else "ready",
                       "detail": error or f"Installed and importable · {version}",
                       "requirement": f">={minimum},<{maximum}"})
    return result


def _failed_packages(message):
    return [{"id": name, "name": name, "version": None, "required": True,
             "status": "error", "detail": message, "requirement": f">={minimum},<{maximum}"}
            for name, _, minimum, maximum in PACKAGES]


def check_python(python):
    try:
        result = run_capture([str(python), "-I", "-c",
            "import json,sys,struct; print(json.dumps({'version': list(sys.version_info[:3]), 'bits':struct.calcsize('P')*8}))"], timeout=10)
        if result.returncode:
            raise ValueError(result.stderr.strip()[:400] or "Python did not start.")
        info = json.loads(result.stdout.strip())
        ready = tuple(info["version"]) >= (3, 10) and info["bits"] == 64
        return {"id": "python", "name": "Python", "status": "ready" if ready else "error",
                "required": True, "version": ".".join(map(str, info["version"])),
                "detail": f"Python {'.'.join(map(str, info['version']))} · {info['bits']}-bit" +
                          ("" if ready else " · Requires Python 3.10+ (64-bit)"), "path": str(python)}
    except (OSError, ValueError, KeyError, subprocess.TimeoutExpired) as exc:
        return {"id": "python", "name": "Python", "status": "error", "required": True,
                "detail": f"Create a local Python environment. {str(exc)[:300]}", "path": str(python)}


def check_packages(python):
    # A separate process isolates native imports from the setup/app server.
    code = ("import sys; sys.path.insert(0, sys.argv[1]); "
            "from formatocr.dependencies import _package_probe; import json; "
            "print('FOLIO_PROBE='+json.dumps(_package_probe()))")
    try:
        result = run_capture([str(python), "-I", "-c", code, str(ROOT)], timeout=60)
        marker = next((line for line in result.stdout.splitlines() if line.startswith("FOLIO_PROBE=")), None)
        if result.returncode or marker is None:
            return _failed_packages((result.stderr.strip() or "Dependency probe failed. Run Install / repair packages.")[-600:])
        return json.loads(marker.partition("=")[2])
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        return _failed_packages(f"Could not verify this environment: {str(exc)[:400]}")


def check_tesseract(tess, root=ROOT):
    base = {"id": "tesseract", "name": "Tesseract OCR", "required": True, "path": str(tess)}
    langs, error, language_errors = [], None, {}
    try:
        version = run_capture([str(tess), "--version"], timeout=10)
        first = (version.stdout or version.stderr).splitlines()[0]
        import re
        match = re.search(r"tesseract\s+v?(\d+)", first, re.I)
        if version.returncode or not match or int(match[1]) < 5:
            raise ValueError("Tesseract 5 or newer is required.")
        listed = run_capture([str(tess), "--list-langs"], timeout=10, env=runtime_environment(root))
        if listed.returncode:
            raise ValueError(listed.stderr.strip()[:400] or "Language data could not be read.")
        langs = [line.strip() for line in listed.stdout.splitlines() if line.strip() in ("eng", "hin")]
        # Listing a filename does not prove its native language data is usable.
        with tempfile.TemporaryDirectory(prefix="folio-language-check-") as scratch:
            sample = Path(scratch) / "blank.pgm"
            sample.write_bytes(b"P5\n100 100\n255\n" + b"\xff" * 10000)
            for language in list(langs):
                probe = run_capture([str(tess), str(sample), "stdout", "-l", language, "--psm", "6"],
                                    timeout=15, env=runtime_environment(root))
                if probe.returncode:
                    langs.remove(language)
                    language_errors[language] = probe.stderr.strip()[-400:]
        base.update(status="ready", detail=first, version=first)
    except (OSError, ValueError, IndexError, subprocess.TimeoutExpired) as exc:
        error = str(exc)[:400]
        base.update(status="error", detail=f"Install Tesseract 5, then recheck. {error}")
    checks = [base]
    for language, label in (("eng", "English"), ("hin", "Hindi")):
        checks.append({"id": language, "name": f"{label} language data", "required": language == "eng",
                       "status": "ready" if language in langs else "warning",
                       "detail": f"{language}.traineddata loaded successfully in Tesseract." if language in langs else
                                 f"Language data is unreadable: {language_errors[language]}" if language in language_errors else
                                 ("Install Tesseract first, then recheck languages." if error else
                                  f"Download the language pack to recognise {label} scans."),
                       "path": tessdata_path(root) or "Tesseract's installed tessdata folder"})
    return checks


def system_report(root=ROOT, python=None, tess=None, models=None):
    root = Path(root)
    python = str(python or sys.executable)
    py = check_python(python)
    packages = check_packages(python) if py["status"] == "ready" else _failed_packages("Python environment is missing or unsupported.")
    checks = [py, *packages, *check_tesseract(resolve_tesseract(tess), root)]
    folder = Path(models or os.environ.get("FORMAT_OCR_MODELS") or root / "out")
    for name in ("mlp_model.pkl", "shape_model.pkl"):
        path = folder / name
        available = path.is_file() and path.stat().st_size > 0
        checks.append({"id": name, "name": name, "required": False,
                       "status": "ready" if available else "warning", "path": str(path),
                       "detail": "File present; model compatibility is checked when OCR runs." if available else
                                 "Optional for Text OCR. Copy your trusted TPB 1891 model into out/. No public download is configured."})
    ready = all(c["status"] == "ready" for c in checks if c["required"])
    return {"checked_at": datetime.now(timezone.utc).isoformat(), "root": str(root),
            "platform": platform.system(), "python": python, "checks": checks,
            "ready": ready, "hindi_ready": ready and next(c for c in checks if c["id"] == "hin")["status"] == "ready",
            "models_present": all(c["status"] == "ready" for c in checks if c["id"].endswith(".pkl")),
            "downloads": {"python": PYTHON_URL, "tesseract": TESSERACT_URL, "languages": LANGUAGE_URL},
            "winget_available": bool(shutil.which("winget"))}
