"""Local FastAPI service; all processing and artifacts stay in the workspace."""
import io
import json
import os
import re
import secrets
import threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

from . import __version__
from .dependencies import ROOT, system_report
from .engine import ALLOWED, Engine, checksum, generated_overlay_reason, ingest
from .exporter import export
from .store import Conflict, Store


class Decision(BaseModel):
    expected_version: int = Field(ge=0, strict=True)
    rank: int = Field(ge=1, le=5, strict=True)
    remedy: str = Field(default="", max_length=300)
    rubric: str = Field(default="", max_length=1000)
    chapter: str = Field(default="", max_length=300)
    reviewer: str = Field(min_length=1, max_length=100)
    note: str = Field(default="", max_length=2000)
    exclude: bool = False


class PageDecision(BaseModel):
    expected_version: int = Field(ge=0, strict=True)
    text: str = Field(default="", max_length=5_000_000)
    reviewer: str = Field(min_length=1, max_length=100)
    note: str = Field(default="", max_length=2000)


class RenameJob(BaseModel):
    title: str = Field(min_length=1, max_length=300)


class BulkAssignment(BaseModel):
    token_ids: list[str] = Field(default_factory=list, max_length=5000)
    status: Literal["needs_review", "machine_accepted", "reviewed", "excluded"] | None = None
    chapter: str | None = Field(default=None, max_length=300)
    rubric: str | None = Field(default=None, max_length=1000)
    reviewer: str = Field(min_length=1, max_length=100)
    note: str = Field(default="Batch assignment", max_length=2000)


class AddToken(BaseModel):
    bbox: list[int] = Field(min_length=4, max_length=4)
    remedy: str = Field(min_length=1, max_length=300)
    rubric: str = Field(min_length=1, max_length=1000)
    chapter: str = Field(default="", max_length=300)
    rank: int = Field(ge=1, le=5)
    reviewer: str = Field(min_length=1, max_length=100)
    note: str = Field(default="Manually added token", max_length=2000)


class SplitToken(BaseModel):
    expected_version: int = Field(ge=0)
    remedies: list[str] = Field(min_length=2, max_length=20)
    reviewer: str = Field(min_length=1, max_length=100)
    note: str = Field(default="Split token", max_length=2000)


class MergeTokens(BaseModel):
    token_ids: list[str] = Field(min_length=2, max_length=20)
    expected_versions: dict[str, int] | None = None
    remedy: str = Field(min_length=1, max_length=300)
    rubric: str = Field(min_length=1, max_length=1000)
    chapter: str = Field(default="", max_length=300)
    rank: int = Field(ge=1, le=5)
    reviewer: str = Field(min_length=1, max_length=100)
    note: str = Field(default="Merged tokens", max_length=2000)


def create_app(data_dir=None, engine=None):
    store = Store(data_dir or os.environ.get("FORMAT_OCR_DATA", Path(__file__).resolve().parents[1] / "app-data"))
    engine = engine or Engine(os.environ.get("TESSERACT_CMD"), os.environ.get("FORMAT_OCR_MODELS"))
    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="format-ocr")

    @asynccontextmanager
    async def lifespan(app):
        store.recover_interrupted()
        yield
        executor.shutdown(wait=False, cancel_futures=True)

    app = FastAPI(title="Format-aware OCR", version=__version__, lifespan=lifespan)
    app.state.store = store
    app.state.engine = engine
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1", "[::1]", "testserver"])

    @app.middleware("http")
    async def origin_guard(request: Request, call_next):
        # Prevent another website from writing to the unauthenticated loopback app.
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            origin = request.headers.get("origin")
            if origin and origin != str(request.base_url).rstrip("/"):
                return Response("Cross-origin writes are disabled.", status_code=403)
        return await call_next(request)

    def get_job(job_id):
        try:
            return store.get(job_id)
        except KeyError:
            raise HTTPException(404, "Job not found")

    def run(job_id):
        job = store.get(job_id)
        doc = job["document"]
        try:
            store.update(job_id, status="running")
            doc["engine"] = {**engine.manifest(), "mode": doc.get("mode", "structured")}
            store.update(job_id, doc=doc)
            job_dir = store.root / job_id
            index = 0
            for source in doc["sources"]:
                source_path = job_dir / source["stored_name"]
                for page_path in ingest(source_path, job_dir, index):
                    if doc.get("mode", "structured") == "plain":
                        machine = engine.process_plain(page_path, doc.get("language", "eng"),
                                                       doc.get("layout", "auto"))
                        page = engine.plain_page(machine, source_hash=source["sha256"], page_index=index,
                                                 book_page=doc["start_page"] + index, image=page_path.name)
                    else:
                        machine = engine.process(page_path)
                        page = engine.page(machine, source_hash=source["sha256"], page_index=index,
                                           book_page=doc["start_page"] + index, chapter=doc.get("chapter", ""),
                                           image=page_path.name)
                    page["image_sha256"] = checksum(page_path)
                    page["source_name"] = source["name"]
                    doc["pages"].append(page)
                    index += 1
                    store.update(job_id, doc=doc)
            if not doc["pages"]:
                raise ValueError("No pages were found in the upload.")
            doc["actual_end_page"] = doc["start_page"] + index - 1
            if doc.get("end_page") is not None and doc["end_page"] != doc["actual_end_page"]:
                doc["diagnostics"].append(
                    f"Page range mismatch: requested {doc['start_page']}–{doc['end_page']}, "
                    f"but {index} scanned pages were found. Actual range: "
                    f"{doc['start_page']}–{doc['actual_end_page']}. All scanned pages were kept."
                )
            store.update(job_id, doc=doc, status="ready")
        except Exception as exc:
            store.update(job_id, doc=doc, status="failed", error=f"{type(exc).__name__}: {exc}")

    @app.get("/api/health")
    def health():
        return {"version": __version__, **engine.diagnostics()}

    setup_cache = {}
    setup_lock = threading.Lock()

    @app.get("/setup", include_in_schema=False)
    def setup_page():
        return FileResponse(ROOT / "formatocr/static/setup.html")

    @app.get("/api/setup/status")
    def setup_status(refresh: bool = False):
        with setup_lock:
            if not setup_cache or refresh:
                setup_cache.update(system_report(tess=engine.tess, models=engine.mlp.parent))
            return {**setup_cache, "read_only": True, "app_running": True}

    @app.post("/api/setup/stop", status_code=204, include_in_schema=False)
    def setup_stop(request: Request):
        # Only the setup instance that launched this app knows the one-use token.
        expected = os.environ.get("FOLIO_SETUP_STOP_TOKEN")
        stop = getattr(app.state, "setup_stop", None)
        if not expected or stop is None:
            raise HTTPException(404, "This app was not started by the setup wizard.")
        if not secrets.compare_digest(request.headers.get("X-Folio-Setup", ""), expected):
            raise HTTPException(403, "Only the originating setup window can stop this app.")
        if any(row["status"] in ("queued", "running") for row in store.list()):
            raise HTTPException(409, "Wait for OCR processing to finish before stopping Folio.")
        stop()
        return Response(status_code=204)

    @app.get("/api/jobs")
    def jobs():
        return store.list()

    @app.post("/api/jobs", status_code=202)
    async def upload(files: list[UploadFile] = File(...), title: str = Form("My Document"),
                     chapter: str = Form(""), start_page: int = Form(0),
                     mode: str = Form("plain"), language: str = Form("eng"),
                     layout: str = Form("auto"), end_page: int | None = Form(None)):
        if (not files or len(files) > 100 or not title.strip() or len(title) > 300 or
                len(chapter) > 300 or start_page < 0 or (end_page is not None and end_page < start_page)):
            raise HTTPException(400, "Provide a title, page numbers from 0 upwards (To ≥ From) and 1 to 100 files.")
        if mode not in ("structured", "plain"):
            raise HTTPException(400, "Choose Text OCR or Format-aware OCR.")
        if language not in ("eng", "hin", "eng+hin"):
            raise HTTPException(400, "Choose English, Hindi or English + Hindi OCR.")
        if layout not in ("auto", "single-column", "uniform-block"):
            raise HTTPException(400, "Choose a supported page layout.")
        for file in files:
            if Path(file.filename or "").suffix.lower() not in ALLOWED:
                raise HTTPException(400, "Supported files: PNG, JPEG, WEBP, TIFF, JP2 and PDF.")
            if mode == "structured":
                reason = generated_overlay_reason(original_name=file.filename)
                if reason:
                    raise HTTPException(400, reason)
        job = store.create(title.strip(), chapter, start_page, mode, language, layout, end_page)
        doc = job["document"]
        total = 0
        try:
            for index, file in enumerate(files):
                suffix = Path(file.filename).suffix.lower()
                stored = f"source-{index + 1:03d}{suffix}"
                target = store.root / job["id"] / stored
                with open(target, "wb") as out:
                    while chunk := await file.read(1024 * 1024):
                        total += len(chunk)
                        if total > 500 * 1024 * 1024:
                            raise ValueError("Total upload exceeds 500 MB.")
                        out.write(chunk)
                if not target.stat().st_size:
                    raise ValueError("An uploaded file was empty.")
                if mode == "structured":
                    reason = generated_overlay_reason(target, file.filename)
                    if reason:
                        raise ValueError(reason)
                doc["sources"].append({"name": Path(file.filename.replace("\\", "/")).name,
                                       "stored_name": stored, "sha256": checksum(target), "bytes": target.stat().st_size})
            store.update(job["id"], doc=doc)
        except Exception as exc:
            store.update(job["id"], doc=doc, status="failed", error=str(exc))
            raise HTTPException(400, str(exc))
        finally:
            for file in files:
                await file.close()
        executor.submit(run, job["id"])
        return store.get(job["id"])

    @app.get("/api/jobs/{job_id}")
    def job(job_id: str):
        return get_job(job_id)

    @app.patch("/api/jobs/{job_id}")
    def rename_job(job_id: str, change: RenameJob):
        try:
            return store.rename(job_id, change.title)
        except KeyError:
            raise HTTPException(404, "Job not found")
        except ValueError as exc:
            raise HTTPException(422, str(exc))

    @app.delete("/api/jobs/{job_id}", status_code=204)
    def delete_job(job_id: str):
        try:
            store.delete(job_id)
        except KeyError:
            raise HTTPException(404, "Job not found")
        except Conflict as exc:
            raise HTTPException(409, str(exc))

    @app.get("/api/jobs/{job_id}/pages/{page_index}/image")
    def page_image(job_id: str, page_index: int):
        pages = get_job(job_id)["document"]["pages"]
        if not 0 <= page_index < len(pages):
            raise HTTPException(404, "Page not found")
        return FileResponse(store.root / job_id / pages[page_index]["image"], media_type="image/png")

    @app.get("/api/jobs/{job_id}/pages/{page_index}/montage")
    def montage(job_id: str, page_index: int):
        from PIL import Image, ImageDraw
        pages = get_job(job_id)["document"]["pages"]
        if not 0 <= page_index < len(pages):
            raise HTTPException(404, "Page not found")
        page = pages[page_index]
        if get_job(job_id)["document"].get("mode", "structured") != "structured":
            raise HTTPException(400, "Montage is available for structured OCR jobs only.")
        tokens = [t for t in page["tokens"] if t["status"] == "needs_review"][:100]
        if not tokens:
            raise HTTPException(400, "This page has no flagged tokens.")
        grid = Image.new("RGB", (1000, ((len(tokens) + 4) // 5) * 110), "white")
        draw = ImageDraw.Draw(grid)
        with Image.open(store.root / job_id / page["image"]) as im:
            for i, token in enumerate(tokens):
                x, y = (i % 5) * 200, (i // 5) * 110
                b = token["bbox"]
                crop = im.crop((max(0, b[0] - 8), max(0, b[1] - 8), min(im.width, b[2] + 8), min(im.height, b[3] + 8)))
                crop.thumbnail((184, 65))
                grid.paste(crop.convert("RGB"), (x + 8, y + 28))
                draw.text((x + 8, y + 5), f"#{i} {token['id'][:8]}  grade {token['rank']}", fill="black")
                draw.rectangle((x, y, x + 199, y + 109), outline="#cccccc")
        data = io.BytesIO()
        grid.save(data, format="PNG")
        return Response(data.getvalue(), media_type="image/png")

    @app.patch("/api/jobs/{job_id}/tokens/{token_id}")
    def review(job_id: str, token_id: str, decision: Decision):
        if not decision.reviewer.strip():
            raise HTTPException(422, "Reviewer name is required.")
        try:
            return store.review(job_id, token_id, decision.model_dump(exclude_unset=True))
        except KeyError:
            raise HTTPException(404, "Job or token not found")
        except Conflict as exc:
            raise HTTPException(409, str(exc))
        except ValueError as exc:
            raise HTTPException(422, str(exc))

    @app.post("/api/jobs/{job_id}/bulk-assign")
    def bulk_assign(job_id: str, assignment: BulkAssignment):
        try:
            return store.bulk_assign(job_id, assignment.model_dump(exclude_unset=True))
        except KeyError:
            raise HTTPException(404, "Job not found")
        except Conflict as exc:
            raise HTTPException(409, str(exc))
        except ValueError as exc:
            raise HTTPException(422, str(exc))

    @app.post("/api/jobs/{job_id}/pages/{page_index}/tokens", status_code=201)
    def add_token(job_id: str, page_index: int, data: AddToken):
        try:
            return store.add_token(job_id, page_index, data.model_dump())
        except KeyError:
            raise HTTPException(404, "Job or page not found")
        except Conflict as exc:
            raise HTTPException(409, str(exc))
        except ValueError as exc:
            raise HTTPException(422, str(exc))

    @app.post("/api/jobs/{job_id}/tokens/{token_id}/split", status_code=201)
    def split_token(job_id: str, token_id: str, data: SplitToken):
        try:
            return store.split_token(job_id, token_id, data.model_dump())
        except KeyError:
            raise HTTPException(404, "Job or token not found")
        except Conflict as exc:
            raise HTTPException(409, str(exc))
        except ValueError as exc:
            raise HTTPException(422, str(exc))

    @app.post("/api/jobs/{job_id}/tokens/merge", status_code=201)
    def merge_tokens(job_id: str, data: MergeTokens):
        try:
            return store.merge_tokens(job_id, data.model_dump())
        except KeyError:
            raise HTTPException(404, "Job or token not found")
        except Conflict as exc:
            raise HTTPException(409, str(exc))
        except ValueError as exc:
            raise HTTPException(422, str(exc))

    @app.patch("/api/jobs/{job_id}/pages/{page_index}")
    def review_page(job_id: str, page_index: int, decision: PageDecision):
        if not decision.reviewer.strip():
            raise HTTPException(422, "Reviewer name is required.")
        try:
            return store.review_page(job_id, page_index, decision.model_dump())
        except KeyError:
            raise HTTPException(404, "Job or page not found")
        except Conflict as exc:
            raise HTTPException(409, str(exc))
        except ValueError as exc:
            raise HTTPException(422, str(exc))

    @app.get("/api/jobs/{job_id}/events")
    def events(job_id: str, token_id: str | None = None):
        get_job(job_id)
        return store.events(job_id, token_id)

    @app.get("/api/jobs/{job_id}/export")
    def download(job_id: str, format: Literal["csv", "json", "sqlite3", "sql", "txt", "docx"] = "json",
                 scope: Literal["draft", "reviewed"] = "reviewed"):
        job = get_job(job_id)
        try:
            data, mime = export(job, store.events(job_id), format, scope)
        except ValueError as exc:
            raise HTTPException(409, str(exc))
        return Response(data, media_type=mime, headers={"Content-Disposition": f'attachment; filename="{job_id}-{scope}.{format}"'})

    @app.get("/api/jobs/{job_id}/export-preview")
    def export_preview(job_id: str, format: Literal["csv", "json", "sqlite3", "sql", "txt", "docx"] = "json",
                       scope: Literal["draft", "reviewed"] = "reviewed"):
        job = get_job(job_id)
        plain = job["document"].get("mode") == "plain"
        allowed = ("txt", "docx", "json") if plain else ("json", "csv", "sqlite3", "sql")
        errors = []
        if format not in allowed:
            errors.append(f"{format.upper()} is not available for this OCR mode.")
        if not plain and format in ("sqlite3", "sql") and scope != "reviewed":
            errors.append("SQLite and SQL require Human reviewed scope.")
        if plain:
            rows = [p for p in job["document"]["pages"] if scope == "draft" or p.get("status") == "reviewed"]
            incomplete = sum(p.get("status") != "reviewed" for p in job["document"]["pages"])
        else:
            tokens = [t for p in job["document"]["pages"] for t in p.get("tokens", [])]
            rows = [t for t in tokens if scope == "draft" or t.get("status") == "reviewed"]
            incomplete = sum(t.get("status") == "needs_review" for t in tokens)
            invalid = sum(t.get("status") == "reviewed" and
                          (not t.get("remedy", "").strip() or not t.get("rubric", "").strip() or t.get("rank") not in range(1, 6))
                          for t in tokens)
            if scope == "reviewed" and invalid:
                errors.append(f"{invalid} reviewed rows have invalid remedy, rubric or grade.")
        if not rows:
            errors.append("This combination currently has 0 exportable rows.")
        return {"valid": not errors, "row_count": len(rows), "incomplete_count": incomplete,
                "errors": errors, "allowed_formats": allowed}

    @app.get("/")
    def home():
        return FileResponse(Path(__file__).parent / "static" / "index.html")

    app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")
    return app
