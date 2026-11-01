"""Transactional job documents and append-only review history."""
import json
import shutil
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


def now():
    return datetime.now(timezone.utc).isoformat()


class Conflict(ValueError):
    pass


class Store:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.db = self.root / "workspace.sqlite3"
        with self.connect() as c:
            c.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY, title TEXT NOT NULL, status TEXT NOT NULL,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                    error TEXT, document TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS review_events (
                    id INTEGER PRIMARY KEY, job_id TEXT NOT NULL REFERENCES jobs(id),
                    token_id TEXT NOT NULL, reviewer TEXT NOT NULL, at TEXT NOT NULL,
                    before_json TEXT NOT NULL, after_json TEXT NOT NULL, note TEXT NOT NULL
                );
            """)

    @contextmanager
    def connect(self):
        c = sqlite3.connect(self.db, timeout=30)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA foreign_keys=ON")
        try:
            yield c
            c.commit()
        except BaseException:
            c.rollback()
            raise
        finally:
            c.close()

    def create(self, title, chapter="", start_page=0, mode="structured", language="eng", layout="auto", end_page=None):
        job_id = uuid4().hex
        if mode not in ("structured", "plain"):
            raise ValueError("Unsupported OCR mode.")
        if start_page < 0 or (end_page is not None and end_page < start_page):
            raise ValueError("Page numbers must start at 0 or above, and To must be at least From.")
        title = self.unique_title(title.strip())
        doc = {"schema_version": 4, "mode": mode,
               "profile": "tpb-1891" if mode == "structured" else "plain-book",
               "edition": "1891 Boston" if mode == "structured" else "",
               "chapter": chapter.strip() if mode == "structured" else "",
               "start_page": start_page, "end_page": end_page, "actual_end_page": None,
               "language": language, "layout": layout,
               "sources": [], "pages": [], "diagnostics": []}
        stamp = now()
        with self.connect() as c:
            c.execute("INSERT INTO jobs VALUES (?,?,?,?,?,?,?)",
                      (job_id, title, "queued", stamp, stamp, None, json.dumps(doc)))
        (self.root / job_id).mkdir()
        return self.get(job_id)

    def unique_title(self, title, exclude_id=None):
        base = title.strip() or "Untitled document"
        with self.connect() as c:
            rows = c.execute("SELECT id,title FROM jobs").fetchall()
        used = {r["title"].casefold() for r in rows if r["id"] != exclude_id}
        if base.casefold() not in used:
            return base
        number = 2
        while f"{base} ({number})".casefold() in used:
            number += 1
        return f"{base} ({number})"

    def get(self, job_id):
        with self.connect() as c:
            row = c.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        if row is None:
            raise KeyError(job_id)
        data = dict(row)
        data["document"] = json.loads(data["document"])
        data["stats"] = self.stats(data["document"])
        return data

    @staticmethod
    def stats(doc):
        if doc.get("mode", "structured") == "plain":
            pages = doc["pages"]
            words = sum(p.get("word_count", len(p.get("text", "").split())) for p in pages)
            reviewed = sum(p.get("status") == "reviewed" for p in pages)
            return {"pages": len(pages), "tokens": words, "words": words,
                    "needs_review": sum(p.get("status") == "needs_review" for p in pages),
                    "machine_accepted": sum(p.get("status") == "machine_accepted" for p in pages),
                    "reviewed": reviewed, "excluded": 0,
                    "reviewed_percent": round(reviewed * 100 / len(pages)) if pages else 0,
                    "incomplete_pages": sum(p.get("status") != "reviewed" for p in pages)}
        tokens = [t for p in doc["pages"] for t in p.get("tokens", [])]
        counts = {s: sum(t["status"] == s for t in tokens)
                  for s in ("needs_review", "machine_accepted", "reviewed", "excluded")}
        decided = counts["reviewed"] + counts["excluded"]
        return {"pages": len(doc["pages"]), "tokens": len(tokens), **counts,
                "reviewed_percent": round(decided * 100 / len(tokens)) if tokens else 0,
                "incomplete_pages": sum(any(t["status"] == "needs_review" for t in p.get("tokens", []))
                                        for p in doc["pages"])}

    def list(self):
        with self.connect() as c:
            rows = c.execute("SELECT * FROM jobs ORDER BY created_at DESC").fetchall()
        result = []
        for row in rows:
            item = dict(row)
            document = json.loads(item.pop("document"))
            item["mode"] = document.get("mode", "structured")
            item["language"] = document.get("language", "eng")
            item["stats"] = self.stats(document)
            result.append(item)
        return result

    def rename(self, job_id, title):
        if not title.strip():
            raise ValueError("Document title is required.")
        title = self.unique_title(title, job_id)
        with self.connect() as c:
            c.execute("BEGIN IMMEDIATE")
            if c.execute("SELECT 1 FROM jobs WHERE id=?", (job_id,)).fetchone() is None:
                raise KeyError(job_id)
            c.execute("UPDATE jobs SET title=?,updated_at=? WHERE id=?", (title, now(), job_id))
        return self.get(job_id)

    def delete(self, job_id):
        path = self.root / job_id
        with self.connect() as c:
            c.execute("BEGIN IMMEDIATE")
            row = c.execute("SELECT status FROM jobs WHERE id=?", (job_id,)).fetchone()
            if row is None:
                raise KeyError(job_id)
            if row["status"] in ("running", "queued"):
                raise Conflict("Wait until processing finishes before deleting this document.")
            c.execute("DELETE FROM review_events WHERE job_id=?", (job_id,))
            c.execute("DELETE FROM jobs WHERE id=?", (job_id,))
        if path.exists():
            shutil.rmtree(path)

    def update(self, job_id, *, doc=None, status=None, error=None):
        with self.connect() as c:
            c.execute("BEGIN IMMEDIATE")
            row = c.execute("SELECT document,status FROM jobs WHERE id=?", (job_id,)).fetchone()
            if row is None:
                raise KeyError(job_id)
            c.execute("UPDATE jobs SET document=?,status=?,error=?,updated_at=? WHERE id=?",
                      (json.dumps(doc) if doc is not None else row["document"],
                       status or row["status"], error, now(), job_id))

    def recover_interrupted(self):
        with self.connect() as c:
            c.execute("UPDATE jobs SET status='failed', error=?,updated_at=? "
                      "WHERE status IN ('queued','running')",
                      ("Processing was interrupted. Completed pages remain available; upload again to rerun.", now()))

    def review(self, job_id, token_id, decision):
        with self.connect() as c:
            c.execute("BEGIN IMMEDIATE")
            row = c.execute("SELECT document,status FROM jobs WHERE id=?", (job_id,)).fetchone()
            if row is None:
                raise KeyError(job_id)
            if row["status"] in ("running", "queued"):
                raise Conflict("Wait until processing finishes before reviewing.")
            doc = json.loads(row["document"])
            token = next((t for p in doc["pages"] for t in p["tokens"] if t["id"] == token_id), None)
            if token is None:
                raise KeyError(token_id)
            if token["version"] != decision["expected_version"]:
                raise Conflict("This token changed. Reload it before saving your decision.")
            before = json.dumps(token)
            stamp = now()
            if decision.get("exclude", False):
                token["status"] = "excluded"
            else:
                if decision["rank"] not in range(1, 6):
                    raise ValueError("Grade must be 1 to 5.")
                for key in ("remedy", "rubric"):
                    if not decision.get(key, "").strip():
                        raise ValueError(f"{key.capitalize()} is required for review.")
                token.update({key: decision[key].strip() for key in ("remedy", "rubric")})
                # Keep historical chapter context when the current UI omits it.
                if "chapter" in decision:
                    token["chapter"] = decision["chapter"].strip()
                token.update(rank=decision["rank"], status="reviewed")
            token.update(version=token["version"] + 1, reviewer=decision["reviewer"].strip(), reviewed_at=stamp)
            c.execute("INSERT INTO review_events(job_id,token_id,reviewer,at,before_json,after_json,note) "
                      "VALUES (?,?,?,?,?,?,?)", (job_id, token_id, token["reviewer"], stamp,
                      before, json.dumps(token), decision.get("note", "")))
            c.execute("UPDATE jobs SET document=?,updated_at=? WHERE id=?", (json.dumps(doc), stamp, job_id))
        return token

    @staticmethod
    def _find_token(doc, token_id):
        for page in doc["pages"]:
            for index, token in enumerate(page.get("tokens", [])):
                if token["id"] == token_id:
                    return page, index, token
        raise KeyError(token_id)

    def bulk_assign(self, job_id, assignment):
        with self.connect() as c:
            c.execute("BEGIN IMMEDIATE")
            row = c.execute("SELECT document,status FROM jobs WHERE id=?", (job_id,)).fetchone()
            if row is None:
                raise KeyError(job_id)
            if row["status"] in ("running", "queued"):
                raise Conflict("Wait until processing finishes before batch assignment.")
            doc = json.loads(row["document"])
            if doc.get("mode") != "structured":
                raise ValueError("Batch assignment is available for Format-aware OCR only.")
            token_ids = set(assignment.get("token_ids") or [])
            if not token_ids and not assignment.get("status"):
                return {"changed": 0, "token_ids": []}
            chapter = assignment.get("chapter")
            rubric = assignment.get("rubric")
            if chapter is None and rubric is None:
                raise ValueError("Provide a chapter or rubric to assign.")
            reviewer = assignment["reviewer"].strip()
            if not reviewer:
                raise ValueError("Reviewer name is required.")
            stamp = now()
            changed = []
            for page in doc["pages"]:
                for token in page.get("tokens", []):
                    if token_ids and token["id"] not in token_ids:
                        continue
                    if not token_ids and assignment.get("status") and token["status"] != assignment["status"]:
                        continue
                    before = json.dumps(token)
                    if chapter is not None:
                        token["chapter"] = chapter.strip()
                    if rubric is not None:
                        token["rubric"] = rubric.strip()
                    token.update(version=token.get("version", 0) + 1, reviewer=reviewer, reviewed_at=stamp)
                    c.execute("INSERT INTO review_events(job_id,token_id,reviewer,at,before_json,after_json,note) VALUES (?,?,?,?,?,?,?)",
                              (job_id, token["id"], reviewer, stamp, before, json.dumps(token), assignment.get("note", "Batch assignment")))
                    changed.append(token["id"])
            c.execute("UPDATE jobs SET document=?,updated_at=? WHERE id=?", (json.dumps(doc), stamp, job_id))
        return {"changed": len(changed), "token_ids": changed}

    def add_token(self, job_id, page_index, data):
        with self.connect() as c:
            c.execute("BEGIN IMMEDIATE")
            row = c.execute("SELECT document,status FROM jobs WHERE id=?", (job_id,)).fetchone()
            if row is None:
                raise KeyError(job_id)
            if row["status"] in ("running", "queued"):
                raise Conflict("Wait until processing finishes before adding a token.")
            doc = json.loads(row["document"])
            if doc.get("mode") != "structured" or not 0 <= page_index < len(doc["pages"]):
                raise KeyError(page_index)
            page = doc["pages"][page_index]
            bbox = data["bbox"]
            if len(bbox) != 4 or bbox[2] <= bbox[0] or bbox[3] <= bbox[1]:
                raise ValueError("Draw a valid token box.")
            if bbox[0] < 0 or bbox[1] < 0 or bbox[2] > page["image_size"][0] or bbox[3] > page["image_size"][1]:
                raise ValueError("The token box must stay within the scanned page.")
            if not data["reviewer"].strip():
                raise ValueError("Reviewer name is required.")
            stamp = now()
            token_id = f"manual-{uuid4().hex[:17]}"
            token = {"id": token_id, "version": 1, "raw": data["remedy"].strip(),
                     "remedy": data["remedy"].strip(), "rubric": data["rubric"].strip(),
                     "chapter": data.get("chapter", "").strip(), "rank": data["rank"],
                     "status": "reviewed", "review_reasons": ["manually-added"],
                     "correction": "manual", "bbox": bbox, "boxes": [bbox],
                     "machine": {"rank": None, "confidence": 0, "features": {}, "manual": True},
                     "reviewer": data["reviewer"].strip(), "reviewed_at": stamp}
            if not token["remedy"] or not token["rubric"]:
                raise ValueError("Remedy and rubric are required.")
            page.setdefault("tokens", []).append(token)
            c.execute("INSERT INTO review_events(job_id,token_id,reviewer,at,before_json,after_json,note) VALUES (?,?,?,?,?,?,?)",
                      (job_id, token_id, token["reviewer"], stamp, "null", json.dumps(token), data.get("note", "Manually added token")))
            c.execute("UPDATE jobs SET document=?,updated_at=? WHERE id=?", (json.dumps(doc), stamp, job_id))
        return token

    def split_token(self, job_id, token_id, data):
        with self.connect() as c:
            c.execute("BEGIN IMMEDIATE")
            row = c.execute("SELECT document,status FROM jobs WHERE id=?", (job_id,)).fetchone()
            if row is None:
                raise KeyError(job_id)
            if row["status"] in ("running", "queued"):
                raise Conflict("Wait until processing finishes before splitting a token.")
            doc = json.loads(row["document"])
            if doc.get("mode") != "structured":
                raise ValueError("Token splitting requires Format-aware OCR.")
            page, index, token = self._find_token(doc, token_id)
            if token.get("version", 0) != data["expected_version"]:
                raise Conflict("This token changed. Reload before splitting.")
            parts = [p.strip() for p in data["remedies"] if p.strip()]
            if len(parts) < 2:
                raise ValueError("Enter at least two remedy parts.")
            if any(len(part) > 300 for part in parts):
                raise ValueError("Each remedy must be at most 300 characters.")
            if not data["reviewer"].strip():
                raise ValueError("Reviewer name is required.")
            x, y, x1, y1 = token["bbox"]
            if x1 - x < len(parts):
                raise ValueError("The token box is too narrow for this many parts.")
            width = (x1 - x) / len(parts)
            stamp = now()
            created = []
            for offset, remedy in enumerate(parts):
                bbox = [round(x + width * offset), y, round(x + width * (offset + 1)), y1]
                child = {**token, "id": f"split-{uuid4().hex[:18]}", "version": 1,
                         "raw": remedy, "remedy": remedy, "bbox": bbox, "boxes": [bbox],
                         "status": "reviewed" if token.get("rubric", "").strip() else "needs_review",
                         "review_reasons": ["manually-split"],
                         "machine": {**token.get("machine", {}), "manual_split_from": token_id},
                         "reviewer": data["reviewer"].strip(), "reviewed_at": stamp}
                created.append(child)
                c.execute("INSERT INTO review_events(job_id,token_id,reviewer,at,before_json,after_json,note) VALUES (?,?,?,?,?,?,?)",
                          (job_id, child["id"], child["reviewer"], stamp, "null", json.dumps(child), data.get("note", "Split token")))
            page["tokens"][index:index + 1] = created
            c.execute("INSERT INTO review_events(job_id,token_id,reviewer,at,before_json,after_json,note) VALUES (?,?,?,?,?,?,?)",
                      (job_id, token_id, data["reviewer"].strip(), stamp, json.dumps(token), "null", "Token split into " + str(len(created))))
            c.execute("UPDATE jobs SET document=?,updated_at=? WHERE id=?", (json.dumps(doc), stamp, job_id))
        return created

    def merge_tokens(self, job_id, data):
        with self.connect() as c:
            c.execute("BEGIN IMMEDIATE")
            row = c.execute("SELECT document,status FROM jobs WHERE id=?", (job_id,)).fetchone()
            if row is None:
                raise KeyError(job_id)
            if row["status"] in ("running", "queued"):
                raise Conflict("Wait until processing finishes before merging tokens.")
            doc = json.loads(row["document"])
            if doc.get("mode") != "structured":
                raise ValueError("Token merging requires Format-aware OCR.")
            ids = data["token_ids"]
            if len(ids) < 2:
                raise ValueError("Select at least two tokens to merge.")
            if len(ids) != len(set(ids)):
                raise ValueError("Select distinct tokens to merge.")
            if not data["reviewer"].strip():
                raise ValueError("Reviewer name is required.")
            found = [self._find_token(doc, token_id) for token_id in ids]
            versions = data.get("expected_versions")
            if versions is not None and any(versions.get(token["id"]) != token.get("version", 0) for _, _, token in found):
                raise Conflict("A selected token changed. Reload before merging.")
            if len({page[0]["index"] for page in found}) != 1:
                raise ValueError("Tokens must be on the same page.")
            page = found[0][0]
            tokens = [item[2] for item in found]
            stamp = now()
            x = min(t["bbox"][0] for t in tokens); y = min(t["bbox"][1] for t in tokens)
            x1 = max(t["bbox"][2] for t in tokens); y1 = max(t["bbox"][3] for t in tokens)
            first = tokens[0]
            merged = {**first, "id": f"merge-{uuid4().hex[:18]}", "version": 1,
                      "raw": " ".join(t["raw"] for t in tokens), "remedy": data["remedy"].strip(),
                      "rubric": data.get("rubric", first.get("rubric", "")).strip(),
                      "chapter": data.get("chapter", first.get("chapter", "")).strip(),
                      "rank": data.get("rank", first["rank"]), "bbox": [x, y, x1, y1],
                      "boxes": [b for t in tokens for b in t.get("boxes", [t["bbox"]])],
                      "status": "reviewed", "review_reasons": ["manually-merged"],
                      "machine": {"rank": None, "confidence": 0, "features": {}, "merged_from": ids},
                      "reviewer": data["reviewer"].strip(), "reviewed_at": stamp}
            if not merged["remedy"] or not merged["rubric"]:
                raise ValueError("Remedy and rubric are required.")
            positions = sorted((index for p, index, token in found if p is page), reverse=True)
            for index in positions:
                page["tokens"].pop(index)
            page["tokens"].insert(min(positions), merged)
            for token in tokens:
                c.execute("INSERT INTO review_events(job_id,token_id,reviewer,at,before_json,after_json,note) VALUES (?,?,?,?,?,?,?)",
                          (job_id, token["id"], merged["reviewer"], stamp, json.dumps(token), "null", "Merged into " + merged["id"]))
            c.execute("INSERT INTO review_events(job_id,token_id,reviewer,at,before_json,after_json,note) VALUES (?,?,?,?,?,?,?)",
                      (job_id, merged["id"], merged["reviewer"], stamp, "null", json.dumps(merged), data.get("note", "Merged tokens")))
            c.execute("UPDATE jobs SET document=?,updated_at=? WHERE id=?", (json.dumps(doc), stamp, job_id))
        return merged

    def review_page(self, job_id, page_index, decision):
        with self.connect() as c:
            c.execute("BEGIN IMMEDIATE")
            row = c.execute("SELECT document,status FROM jobs WHERE id=?", (job_id,)).fetchone()
            if row is None:
                raise KeyError(job_id)
            if row["status"] in ("running", "queued"):
                raise Conflict("Wait until processing finishes before reviewing.")
            doc = json.loads(row["document"])
            if doc.get("mode") != "plain" or not 0 <= page_index < len(doc["pages"]):
                raise KeyError(page_index)
            page = doc["pages"][page_index]
            if page.get("version", 0) != decision["expected_version"]:
                raise Conflict("This page changed. Reload it before saving your decision.")
            reviewer = decision["reviewer"].strip()
            if not reviewer:
                raise ValueError("Reviewer name is required.")
            before = json.dumps(page)
            stamp = now()
            page.update(text=decision["text"].strip(), status="reviewed",
                        version=page.get("version", 0) + 1, reviewer=reviewer,
                        reviewed_at=stamp)
            page["word_count"] = len(page["text"].split())
            event_key = f"page:{page_index}"
            c.execute("INSERT INTO review_events(job_id,token_id,reviewer,at,before_json,after_json,note) "
                      "VALUES (?,?,?,?,?,?,?)", (job_id, event_key, reviewer, stamp,
                      before, json.dumps(page), decision.get("note", "")))
            c.execute("UPDATE jobs SET document=?,updated_at=? WHERE id=?", (json.dumps(doc), stamp, job_id))
        return page

    def events(self, job_id, token_id=None):
        self.get(job_id)
        with self.connect() as c:
            rows = c.execute("SELECT * FROM review_events WHERE job_id=? "
                             "AND (? IS NULL OR token_id=?) ORDER BY id", (job_id, token_id, token_id)).fetchall()
        return [{**dict(r), "before_json": json.loads(r["before_json"]),
                 "after_json": json.loads(r["after_json"])} for r in rows]
