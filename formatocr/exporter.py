"""Evidence-preserving draft exports and relational reviewed exports."""
import csv
import io
import json
import sqlite3
import tempfile
import zipfile
from contextlib import closing
from pathlib import Path
from xml.sax.saxutils import escape


def rows(job, scope):
    result = []
    for page in job["document"]["pages"]:
        for token in page["tokens"]:
            if scope == "reviewed" and token["status"] != "reviewed":
                continue
            result.append({"token_id": token["id"], "book": job["title"],
                           "edition": job["document"]["edition"], "page": page["book_page"],
                           "chapter": token.get("chapter", ""), "rubric": token["rubric"],
                           "remedy": token["remedy"], "grade": token["rank"],
                           "raw": token["raw"], "machine_rank": token["machine"]["rank"],
                           "machine_confidence": token["machine"].get("confidence"),
                           "verification_status": token["status"], "reviewer": token["reviewer"],
                           "reviewed_at": token["reviewed_at"], "version": token["version"],
                           "source_sha256": page["source_sha256"], "bbox": token["bbox"]})
    if not result:
        raise ValueError("There are no tokens in this export scope.")
    return result


def export(job, events, fmt, scope):
    if job["status"] in ("queued", "running"):
        raise ValueError("Wait until processing finishes before exporting.")
    if job["document"].get("mode", "structured") == "plain":
        return export_plain(job, events, fmt, scope)
    data = rows(job, scope)
    selected = {r["token_id"] for r in data}
    events = [e for e in events if e["token_id"] in selected]
    if fmt == "json":
        document = {**job["document"], "pages": [
            {**p, "tokens": [t for t in p["tokens"] if t["id"] in selected]}
            for p in job["document"]["pages"]]}
        doc = {**job, "document": document, "export_scope": scope, "export_rows": data,
               "review_events": events}
        return json.dumps(doc, ensure_ascii=False, indent=2).encode(), "application/json"
    if fmt == "csv":
        stream = io.StringIO(newline="")
        writer = csv.DictWriter(stream, fieldnames=list(data[0]))
        writer.writeheader()
        writer.writerows({**r, "bbox": json.dumps(r["bbox"])} for r in data)
        return stream.getvalue().encode("utf-8-sig"), "text/csv"
    if scope != "reviewed":
        raise ValueError("Relational exports require reviewed tokens.")
    for row in data:
        if not all(row[k].strip() for k in ("rubric", "remedy")) or row["grade"] not in range(1, 6):
            raise ValueError("A reviewed row has invalid identity or grade.")
    with tempfile.TemporaryDirectory() as temp:
        path = Path(temp) / "reviewed.sqlite3"
        with closing(sqlite3.connect(path)) as c:
            c.executescript("""
                PRAGMA foreign_keys=ON;
                CREATE TABLE metadata (key TEXT PRIMARY KEY,value TEXT NOT NULL);
                CREATE TABLE rep_rubric (
                    rubric_id INTEGER PRIMARY KEY, book TEXT NOT NULL, edition TEXT NOT NULL,
                    chapter_name TEXT NOT NULL, rubric_name TEXT NOT NULL,
                    UNIQUE(book,edition,chapter_name,rubric_name));
                CREATE TABLE rep_remedy (remedy_id INTEGER PRIMARY KEY, abbrev TEXT NOT NULL UNIQUE);
                CREATE TABLE rep_link (
                    link_id TEXT PRIMARY KEY, rubric_id INTEGER NOT NULL REFERENCES rep_rubric,
                    remedy_id INTEGER NOT NULL REFERENCES rep_remedy, page_no INTEGER NOT NULL,
                    grade INTEGER NOT NULL CHECK(grade BETWEEN 1 AND 5), machine_rank INTEGER,
                    confidence REAL, verification_status TEXT NOT NULL CHECK(verification_status='reviewed'),
                    reviewer TEXT NOT NULL, reviewed_at TEXT NOT NULL, source_sha256 TEXT NOT NULL,
                    bbox TEXT NOT NULL, raw_text TEXT NOT NULL);
                CREATE TABLE review_events (id INTEGER PRIMARY KEY, token_id TEXT NOT NULL, payload TEXT NOT NULL);
            """)
            c.execute("INSERT INTO metadata VALUES (?,?)", ("manifest", json.dumps({
                "job_id": job["id"], "title": job["title"], "profile": job["document"]["profile"],
                "sources": job["document"]["sources"], "engine": job["document"].get("engine")})))
            for row in data:
                rubric = tuple(row[k] for k in ("book", "edition", "chapter", "rubric"))
                c.execute("INSERT OR IGNORE INTO rep_rubric(book,edition,chapter_name,rubric_name) VALUES (?,?,?,?)", rubric)
                rid = c.execute("SELECT rubric_id FROM rep_rubric WHERE book=? AND edition=? AND chapter_name=? AND rubric_name=?", rubric).fetchone()[0]
                c.execute("INSERT OR IGNORE INTO rep_remedy(abbrev) VALUES (?)", (row["remedy"],))
                mid = c.execute("SELECT remedy_id FROM rep_remedy WHERE abbrev=?", (row["remedy"],)).fetchone()[0]
                c.execute("INSERT INTO rep_link VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                          (row["token_id"], rid, mid, row["page"], row["grade"], row["machine_rank"],
                           row["machine_confidence"], "reviewed", row["reviewer"], row["reviewed_at"],
                           row["source_sha256"], json.dumps(row["bbox"]), row["raw"]))
            for event in events:
                c.execute("INSERT INTO review_events VALUES (?,?,?)", (event["id"], event["token_id"], json.dumps(event)))
            c.commit()
            if fmt == "sql":
                return "\n".join(c.iterdump()).encode("utf-8"), "application/sql"
        return path.read_bytes(), "application/vnd.sqlite3"


def export_plain(job, events, fmt, scope):
    pages = [page for page in job["document"]["pages"]
             if scope == "draft" or page.get("status") == "reviewed"]
    if not pages:
        raise ValueError("There are no pages in this export scope.")
    selected = {f"page:{page['index']}" for page in pages}
    events = [event for event in events if event["token_id"] in selected]
    if fmt == "json":
        document = {**job["document"], "pages": pages}
        payload = {**job, "document": document, "export_scope": scope,
                   "review_events": events}
        return json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8"), "application/json"
    if fmt == "txt":
        text = "\n\n\f\n\n".join(page.get("text", "") for page in pages)
        return text.encode("utf-8-sig"), "text/plain; charset=utf-8"
    if fmt == "docx":
        return make_docx(job["title"], pages), (
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )
    raise ValueError("Normal book OCR exports support TXT, DOCX and JSON.")


def make_docx(title, pages):
    """Create a small standards-compliant DOCX without an additional dependency."""
    paragraphs = []
    for page_number, page in enumerate(pages):
        for line in page.get("text", "").splitlines() or [""]:
            if line:
                paragraphs.append(
                    '<w:p><w:r><w:t xml:space="preserve">'
                    f"{escape(line)}</w:t></w:r></w:p>"
                )
            else:
                paragraphs.append("<w:p/>")
        if page_number < len(pages) - 1:
            paragraphs.append('<w:p><w:r><w:br w:type="page"/></w:r></w:p>')
    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        '<w:body>' + "".join(paragraphs) +
        '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/>'
        '<w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440"/>'
        '</w:sectPr></w:body></w:document>'
    )
    content_types = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/word/document.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
        '<Override PartName="/docProps/core.xml" '
        'ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>'
        '</Types>'
    )
    relationships = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
        'Target="word/document.xml"/>'
        '<Relationship Id="rId2" '
        'Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" '
        'Target="docProps/core.xml"/></Relationships>'
    )
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("_rels/.rels", relationships)
        archive.writestr("word/document.xml", document)
        archive.writestr("docProps/core.xml", (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
            'xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>'
            f"{escape(title)}</dc:title></cp:coreProperties>"
        ))
    return output.getvalue()
