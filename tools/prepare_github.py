"""Build a source-only GitHub upload ZIP for Folio by ThinkHomeo.in.

Uses only the standard library. Run from any working directory; local user
data, models, QA evidence and environments are never source candidates.
"""
import argparse
import hashlib
import json
import re
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE_ROOT = "folio-ocr-studio"
ROOT_FILES = (
    ".gitignore", ".gitattributes", "README.md", "APPLICATION.md",
    "ARCHITECTURE_REVIEW.md", "NOTICE.md", "pyproject.toml",
    "requirements-lock.txt", "run_app.bat", "setup_folio.bat",
    "folio_bootstrap.bat", "setup_folio.py", "out/README.md", "CONTRIBUTING.md",
)
SOURCE_DIRS = ("formatocr", "tpbocr", "tests", "docs", ".github", "tools")
OPTIONAL_ROOT_FILES = ("LICENSE", "LICENSE.md", "LICENSE.txt")
TEXT_SUFFIXES = {".py", ".cjs", ".js", ".css", ".html", ".json", ".md", ".yml", ".yaml"}
SKIP_DIRS = {"__pycache__", "node_modules", ".venv", ".git", ".pytest_cache"}
MAX_SOURCE_BYTES = 5 * 1024 * 1024
BLOCKED_CONTENT = (
    ("personal Windows path", re.compile(r"[A-Za-z]:[\\/]+Users[\\/]+", re.I)),
    ("GitHub token", re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})\b")),
    ("API credential", re.compile(r"\b(?:sk-[A-Za-z0-9_-]{24,}|AKIA[A-Z0-9]{16})\b")),
    ("private key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----")),
)


def source_files():
    candidates = {ROOT / name for name in ROOT_FILES}
    candidates.update(ROOT / name for name in OPTIONAL_ROOT_FILES if (ROOT / name).is_file())
    for name in SOURCE_DIRS:
        directory = ROOT / name
        if not directory.is_dir():
            raise ValueError(f"Required source folder missing: {name}")
        for path in directory.rglob("*"):
            relative = path.relative_to(ROOT)
            if not path.is_file() or any(part in SKIP_DIRS for part in relative.parts):
                continue
            if path.suffix in TEXT_SUFFIXES or (relative.parts[:2] == ("docs", "images") and path.suffix == ".png"):
                candidates.add(path)
    for path in sorted(candidates, key=lambda p: p.relative_to(ROOT).as_posix()):
        relative = path.relative_to(ROOT).as_posix()
        if path.is_symlink() or not path.resolve().is_relative_to(ROOT):
            raise ValueError(f"Linked or external source file: {relative}")
        if not path.is_file():
            raise ValueError(f"Required source file missing: {relative}")
        if path.stat().st_size > MAX_SOURCE_BYTES:
            raise ValueError(f"Unexpectedly large source file: {relative}")
        content = path.read_bytes()
        if path.suffix == ".png":
            if not content.startswith(b"\x89PNG\r\n\x1a\n"):
                raise ValueError(f"Invalid documentation screenshot: {relative}")
        else:
            decoded = content.decode("utf-8-sig")
            for label, pattern in BLOCKED_CONTENT:
                if pattern.search(decoded):
                    # Report the file and category without printing a credential.
                    raise ValueError(f"Review {relative}: found {label}")
        yield relative, content


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "dist/folio-ocr-studio-github.zip")
    args = parser.parse_args()
    output = args.output.resolve()
    if output.suffix != ".zip" or not output.is_relative_to(ROOT / "dist"):
        parser.error("Output must be a .zip inside this project's dist/ folder.")
    try:
        sources = list(source_files())  # Validate everything before writing.
        output.parent.mkdir(parents=True, exist_ok=True)
        manifest = []
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for name, content in sources:
                archive.writestr(f"{ARCHIVE_ROOT}/{name}", content)
                manifest.append({"path": name, "bytes": len(content),
                                 "sha256": hashlib.sha256(content).hexdigest()})
        with zipfile.ZipFile(output) as archive:
            if archive.testzip() is not None or len(archive.namelist()) != len(sources):
                raise ValueError("Archive verification failed")
        report = {"project": "Folio OCR Studio", "website": "https://thinkhomeo.in/",
                  "archive": output.name, "archive_sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
                  "file_count": len(manifest), "source_bytes": sum(entry["bytes"] for entry in manifest),
                  "files": manifest}
        manifest_path = output.with_suffix(".manifest.json")
        manifest_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    except (OSError, UnicodeError, ValueError) as exc:
        parser.exit(1, f"Source preparation failed: {exc}\n")
    print(f"Ready: {len(sources)} source files, {output.stat().st_size:,} ZIP bytes")
    print(f"ZIP: {output}\nManifest: {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
