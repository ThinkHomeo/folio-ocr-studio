import copy
import io
import json
import sqlite3
import tempfile
import time
import unittest
import zipfile
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from PIL import Image

from formatocr.engine import Engine, generated_overlay_reason, guarded_correct, ingest, triage
from formatocr.exporter import export
from formatocr.server import create_app
from formatocr.store import Conflict, Store


def machine_record():
    return {"text": "Acon.", "raw": "Acon.,", "rank": 2, "rank_name": "Roman",
            "confidence": 0.67, "ocr_confidence": 0.98, "flag": True,
            "scalar_rank": 2, "mlp_rank": 4, "shape_rank": 2,
            "bbox": [10, 10, 60, 30], "features": {"weight": 0.2, "slant": 1, "xheight": 18}}


class FakeEngine(Engine):
    def manifest(self):
        return {"fixture": True}

    def diagnostics(self):
        return {"tesseract_available": True, "fixture": True}

    def process(self, path):
        with Image.open(path) as image:
            size = list(image.size)
        return {"rubrics": [{"rubric": "Anxiety", "remedies": [machine_record()]}],
                "weight_threshold": 0.29, "image_size": size}

    def process_plain(self, path, language="eng", layout="auto"):
        with Image.open(path) as image:
            size = list(image.size)
        return {"text": "A simple book page.\nSecond line.",
                "lines": [{"text": "A simple book page.", "bbox": [5, 5, 100, 20],
                           "confidence": .93}],
                "image_size": size, "word_count": 7, "ocr_confidence": .93,
                "language": language, "layout": layout}


class ApplicationTests(unittest.TestCase):
    def test_setup_can_stop_only_its_owned_idle_server(self):
        with tempfile.TemporaryDirectory() as scratch, patch.dict('os.environ', {'FOLIO_SETUP_STOP_TOKEN':'owned-secret'}):
            app = create_app(scratch, FakeEngine())
            app.state.setup_stop = unittest.mock.Mock()
            with TestClient(app) as client:
                self.assertEqual(client.post('/api/setup/stop').status_code, 403)
                self.assertEqual(client.post('/api/setup/stop', headers={'X-Folio-Setup':'owned-secret'}).status_code, 204)
                app.state.setup_stop.assert_called_once()
                app.state.store.create('Processing test', '', 0)
                self.assertEqual(client.post('/api/setup/stop', headers={'X-Folio-Setup':'owned-secret'}).status_code, 409)

    def test_dependency_page_checks_current_runtime_and_caches_report(self):
        with tempfile.TemporaryDirectory() as scratch, TestClient(create_app(scratch, FakeEngine())) as client:
            self.assertEqual(client.get('/setup').status_code, 200)
            self.assertIn('System setup', client.get('/setup').text)
            with patch('formatocr.server.system_report', return_value={'ready':True,'checks':[]}) as probe:
                report = client.get('/api/setup/status').json()
                self.assertTrue(report['read_only'])
                self.assertTrue(report['app_running'])
                client.get('/api/setup/status')
                self.assertEqual(probe.call_count, 1)
                client.get('/api/setup/status?refresh=1')
                self.assertEqual(probe.call_count, 2)
            self.assertEqual(client.post('/api/setup/action', json={'action':'packages'}).status_code, 404)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.store = Store(self.root / "workspace")
        self.engine = FakeEngine()

    def tearDown(self):
        self.temp.cleanup()

    def job(self):
        job = self.store.create("TPB", "Mind", 17)
        doc = job["document"]
        page = self.engine.page(self.engine.process(self.image()), source_hash="abc", page_index=0,
                                book_page=17, chapter="Mind", image="page-0001.png")
        doc["pages"] = [page]
        self.store.update(job["id"], doc=doc, status="ready")
        return self.store.get(job["id"])

    def image(self):
        path = self.root / "scan.png"
        Image.new("RGB", (120, 160), "white").save(path)
        return path

    def decision(self, version=0, chapter="Mind"):
        return {"expected_version": version, "rank": 4, "remedy": "Acon.",
                "rubric": "Anxiety", "chapter": chapter, "reviewer": "Test reviewer", "note": "fixture"}

    def test_review_preserves_machine_and_rejects_stale_write(self):
        job = self.job()
        token = job["document"]["pages"][0]["tokens"][0]
        reviewed = self.store.review(job["id"], token["id"], self.decision())
        self.assertEqual(reviewed["rank"], 4)
        self.assertEqual(reviewed["machine"]["rank"], 2)
        self.assertEqual(reviewed["machine"]["confidence"], 0.67)
        with self.assertRaises(Conflict):
            self.store.review(job["id"], token["id"], self.decision())
        self.assertEqual(len(self.store.events(job["id"])), 1)
        self.assertEqual(Store(self.store.root).get(job["id"])["stats"]["reviewed"], 1)

    def test_document_management_unique_names_rename_and_delete(self):
        first = self.store.create("My scan")
        second = self.store.create("My scan")
        third = self.store.create("My scan")
        self.assertEqual([first["title"], second["title"], third["title"]],
                         ["My scan", "My scan (2)", "My scan (3)"])
        self.store.update(second["id"], status="ready")
        renamed = self.store.rename(third["id"], "My scan")
        self.assertEqual(renamed["title"], "My scan (3)")
        self.store.delete(second["id"])
        with self.assertRaises(KeyError):
            self.store.get(second["id"])
        self.assertFalse((self.store.root / second["id"]).exists())

    def test_batch_add_split_merge_and_progress(self):
        job = self.job()
        doc = job["document"]
        original = doc["pages"][0]["tokens"][0]
        doc["pages"][0]["tokens"].append({**copy.deepcopy(original), "id": "second",
                                            "bbox": [65, 10, 105, 30]})
        self.store.update(job["id"], doc=doc)
        result = self.store.bulk_assign(job["id"], {"token_ids": [], "status": "needs_review",
            "chapter": "Mind", "rubric": "Fear", "reviewer": "Batch reviewer"})
        self.assertEqual(result["changed"], 2)
        job = self.store.get(job["id"])
        self.assertEqual({t["rubric"] for t in job["document"]["pages"][0]["tokens"]}, {"Fear"})
        added = self.store.add_token(job["id"], 0, {"bbox": [5, 40, 55, 62], "remedy": "Bell.",
            "rubric": "Fear", "chapter": "Mind", "rank": 3, "reviewer": "Editor"})
        self.assertEqual(added["status"], "reviewed")
        split = self.store.split_token(job["id"], original["id"], {"expected_version": 1,
            "remedies": ["Acon.", "Arn."], "reviewer": "Editor"})
        self.assertEqual(len(split), 2)
        job = self.store.get(job["id"])
        merged = self.store.merge_tokens(job["id"], {"token_ids": [split[0]["id"], split[1]["id"]],
            "remedy": "Acon. Arn.", "rubric": "Fear", "chapter": "Mind", "rank": 2,
            "reviewer": "Editor"})
        self.assertEqual(merged["machine"]["merged_from"], [split[0]["id"], split[1]["id"]])
        stats = self.store.get(job["id"])["stats"]
        self.assertGreater(stats["reviewed_percent"], 0)
        self.assertIn("incomplete_pages", stats)

    def test_required_review_context_and_exclusion(self):
        job = self.job()
        token = job["document"]["pages"][0]["tokens"][0]
        with self.assertRaises(ValueError):
            self.store.review(job["id"], token["id"], {**self.decision(), "rubric": ""})
        self.store.review(job["id"], token["id"], {**self.decision(), "exclude": True})
        self.assertEqual(self.store.get(job["id"])["stats"]["excluded"], 1)
        with self.assertRaises(ValueError):
            export(self.store.get(job["id"]), [], "csv", "reviewed")

    def test_empty_batch_and_duplicate_merge_cannot_change_unrelated_tokens(self):
        job = self.job()
        original = job["document"]["pages"][0]["tokens"][0]
        unchanged = copy.deepcopy(job["document"])
        result = self.store.bulk_assign(job["id"], {"token_ids": [], "rubric": "Fear", "reviewer": "QA"})
        self.assertEqual(result["changed"], 0)
        with self.assertRaises(ValueError):
            self.store.merge_tokens(job["id"], {"token_ids": [original["id"], original["id"]],
                "remedy": "Acon.", "rubric": "Fear", "rank": 2, "reviewer": "QA"})
        self.assertEqual(self.store.get(job["id"])["document"], unchanged)
        self.assertEqual(self.store.events(job["id"]), [])

    def test_token_corrections_reject_running_jobs_invalid_boxes_and_stale_merges(self):
        job = self.job()
        token = job["document"]["pages"][0]["tokens"][0]
        add = {"bbox": [5, 40, 55, 62], "remedy": "Bell.", "rubric": "Fear", "rank": 3, "reviewer": "QA"}
        split = {"expected_version": 0, "remedies": ["Acon.", "Arn."], "reviewer": "QA"}
        merge = {"token_ids": [token["id"], "other"], "remedy": "Acon.", "rubric": "Fear", "rank": 2, "reviewer": "QA"}
        self.store.update(job["id"], status="running")
        for operation in (lambda: self.store.add_token(job["id"], 0, add),
                          lambda: self.store.split_token(job["id"], token["id"], split),
                          lambda: self.store.merge_tokens(job["id"], merge)):
            with self.assertRaises(Conflict): operation()
        self.store.update(job["id"], status="ready")
        for bbox in ([-1, 0, 20, 20], [1, 1, 500, 500], [10, 10, 10, 20]):
            with self.assertRaises(ValueError):
                self.store.add_token(job["id"], 0, {**add, "bbox": bbox})
        with self.assertRaises(ValueError):
            self.store.add_token(job["id"], 0, {**add, "reviewer": "  "})
        parts = self.store.split_token(job["id"], token["id"], split)
        versions = {part["id"]: part["version"] for part in parts}
        self.store.bulk_assign(job["id"], {"token_ids": [parts[0]["id"]], "rubric": "Updated", "reviewer": "QA"})
        with self.assertRaises(Conflict):
            self.store.merge_tokens(job["id"], {**merge, "token_ids": list(versions), "expected_versions": versions})
        self.assertEqual(len(self.store.get(job["id"])["document"]["pages"][0]["tokens"]), 2)

    def test_split_without_rubric_remains_incomplete(self):
        job = self.job()
        token = job["document"]["pages"][0]["tokens"][0]
        token["rubric"] = ""
        self.store.update(job["id"], doc=job["document"])
        parts = self.store.split_token(job["id"], token["id"],
            {"expected_version": 0, "remedies": ["Acon.", "Arn."], "reviewer": "QA"})
        self.assertTrue(all(part["status"] == "needs_review" for part in parts))
        self.assertEqual(self.store.get(job["id"])["stats"]["reviewed_percent"], 0)

    def test_missing_vote_noise_and_suffix_abstain(self):
        rem = machine_record()
        rem.update(flag=False, confidence=0.99, mlp_rank=None, shape_rank=None)
        self.assertIn("missing-classifier-vote", triage(rem, .29, False, "Mind", "Anxiety"))
        self.assertTrue(guarded_correct("Acon$.", {"acon": "Acon."})[1])
        self.assertEqual(guarded_correct("Nux x.", {"nux v": "Nux v."})[2], "suffix-identity-change")
        self.assertTrue(guarded_correct("Ant.", {"act": "Act."})[1])
        self.assertEqual(guarded_correct("Mere.", {"merc": "Merc."})[0], "Merc.")

    def test_reviewed_export_filters_and_relational_context(self):
        job = self.job()
        doc = job["document"]
        original = doc["pages"][0]["tokens"][0]
        doc["pages"][0]["tokens"] += [{**copy.deepcopy(original), "id": "second"},
                                      {**copy.deepcopy(original), "id": "unreviewed"}]
        self.store.update(job["id"], doc=doc)
        self.store.review(job["id"], original["id"], self.decision())
        self.store.review(job["id"], "second", self.decision(chapter="Sleep"))
        job = self.store.get(job["id"])
        output, _ = export(job, self.store.events(job["id"]), "json", "reviewed")
        data = json.loads(output)
        self.assertEqual(len(data["export_rows"]), 2)
        self.assertEqual(len(data["document"]["pages"][0]["tokens"]), 2)
        self.assertNotIn('"unreviewed"', output.decode())
        binary, _ = export(job, [], "sqlite3", "reviewed")
        db = self.root / "export.sqlite3"
        db.write_bytes(binary)
        with closing(sqlite3.connect(db)) as c:
            self.assertEqual(c.execute("SELECT COUNT(*) FROM rep_rubric").fetchone()[0], 2)
            self.assertEqual(c.execute("SELECT COUNT(*) FROM rep_link JOIN rep_rubric USING(rubric_id)").fetchone()[0], 2)
            self.assertEqual(c.execute("PRAGMA foreign_key_check").fetchall(), [])
            self.assertEqual(c.execute("SELECT confidence FROM rep_link LIMIT 1").fetchone()[0], 0.67)
        sql, _ = export(job, [], "sql", "reviewed")
        with closing(sqlite3.connect(":memory:")) as c:
            c.executescript(sql.decode())
            self.assertEqual(c.execute("SELECT COUNT(*) FROM rep_link").fetchone()[0], 2)
        with self.assertRaises(ValueError):
            export(job, [], "sqlite3", "draft")

    def test_reviewed_exports_filter_audit_events_and_keep_selected_history(self):
        job = self.job()
        doc = job["document"]
        token = doc["pages"][0]["tokens"][0]
        doc["pages"][0]["tokens"] += [{**copy.deepcopy(token), "id": "excluded"},
                                      {**copy.deepcopy(token), "id": "unreviewed"}]
        self.store.update(job["id"], doc=doc)
        self.store.review(job["id"], token["id"], self.decision())
        self.store.review(job["id"], token["id"], self.decision(version=1))
        self.store.review(job["id"], "excluded", {**self.decision(), "exclude": True})
        job = self.store.get(job["id"])
        events = self.store.events(job["id"])
        selected_ids = [event["id"] for event in events if event["token_id"] == token["id"]]
        for fmt in ("json", "sqlite3", "sql"):
            with self.subTest(format=fmt):
                output, _ = export(job, events, fmt, "reviewed")
                if fmt == "json":
                    exported_events = json.loads(output)["review_events"]
                    actual = [(e["id"], e["token_id"]) for e in exported_events]
                else:
                    if fmt == "sqlite3":
                        path = self.root / "scoped-events.sqlite3"
                        path.write_bytes(output)
                        connection = sqlite3.connect(path)
                    else:
                        connection = sqlite3.connect(":memory:")
                    with closing(connection) as c:
                        if fmt == "sql":
                            c.executescript(output.decode("utf-8"))
                        actual = c.execute("SELECT id,token_id FROM review_events ORDER BY id").fetchall()
                        self.assertEqual(c.execute("SELECT COUNT(*) FROM rep_link").fetchone()[0], 1)
                self.assertEqual(actual, [(event_id, token["id"]) for event_id in selected_ids])
        self.assertEqual(len(self.store.events(job["id"])), 3)
        draft, _ = export(job, events, "json", "draft")
        self.assertEqual(len(json.loads(draft)["review_events"]), 3)

    def test_lossless_tiff_and_pdf_multipage(self):
        image = Image.new("RGB", (120, 160), "white")
        output = self.root / "pages"
        output.mkdir()
        tiff = self.root / "two.tiff"
        image.save(tiff, save_all=True, append_images=[image])
        pages = list(ingest(tiff, output))
        self.assertEqual(len(pages), 2)
        with Image.open(pages[0]) as rendered:
            self.assertEqual(rendered.size, image.size)
        pdf = self.root / "two.pdf"
        image.save(pdf, save_all=True, append_images=[image], resolution=72)
        self.assertEqual(len(list(ingest(pdf, output, 2))), 2)

    def test_api_upload_review_and_restart_persistence(self):
        with TestClient(create_app(self.root / "api", self.engine)) as client:
            blob = io.BytesIO()
            Image.new("RGB", (120, 160), "white").save(blob, format="PNG")
            response = client.post("/api/jobs", data={"mode": "structured", "chapter": "Mind", "start_page": "17"},
                                   files=[("files", ("scan.png", blob.getvalue(), "image/png"))])
            self.assertEqual(response.status_code, 202, response.text)
            jid = response.json()["id"]
            for _ in range(100):
                job = client.get(f"/api/jobs/{jid}").json()
                if job["status"] not in ("running", "queued"):
                    break
                time.sleep(.01)
            self.assertEqual(job["status"], "ready", job.get("error"))
            token = job["document"]["pages"][0]["tokens"][0]
            route = f"/api/jobs/{jid}/tokens/{token['id']}"
            self.assertEqual(client.patch(route, json=self.decision()).status_code, 200)
            self.assertEqual(client.patch(route, json=self.decision()).status_code, 409)
            self.assertEqual(client.patch(route, json={**self.decision(1), "rank": 8}).status_code, 422)
            self.assertEqual(client.patch(route, json=self.decision(1), headers={"Origin": "https://example.org"}).status_code, 403)
            self.assertEqual(client.get(f"/api/jobs/{jid}/pages/0/image").status_code, 200)
            self.assertEqual(client.get(f"/api/jobs/{jid}/pages/-1/image").status_code, 404)
            self.assertEqual(client.get(f"/api/jobs/{jid}/export?format=sqlite3").status_code, 200)
            self.assertEqual(client.get("/api/health", headers={"Host": "evil.example"}).status_code, 400)
        with TestClient(create_app(self.root / "api", self.engine)) as restarted:
            self.assertEqual(restarted.get(f"/api/jobs/{jid}").json()["stats"]["reviewed"], 1)

    def test_plain_book_upload_page_review_and_exports(self):
        with TestClient(create_app(self.root / "plain-api", self.engine)) as client:
            blob = io.BytesIO()
            Image.new("RGB", (120, 160), "white").save(blob, format="PNG")
            response = client.post("/api/jobs", data={"mode": "plain", "title": "Ordinary Book",
                                   "language": "eng", "layout": "single-column", "start_page": "5"},
                                   files=[("files", ("page.png", blob.getvalue(), "image/png"))])
            self.assertEqual(response.status_code, 202, response.text)
            jid = response.json()["id"]
            for _ in range(100):
                job = client.get(f"/api/jobs/{jid}").json()
                if job["status"] not in ("running", "queued"):
                    break
                time.sleep(.01)
            self.assertEqual(job["status"], "ready", job.get("error"))
            self.assertEqual(job["document"]["mode"], "plain")
            self.assertEqual(job["document"]["pages"][0]["book_page"], 5)
            self.assertEqual(job["stats"]["words"], 7)
            decision = {"expected_version": 0, "text": "Corrected ordinary book text.",
                        "reviewer": "Proof reader", "note": "fixed OCR"}
            reviewed = client.patch(f"/api/jobs/{jid}/pages/0", json=decision)
            self.assertEqual(reviewed.status_code, 200, reviewed.text)
            self.assertEqual(reviewed.json()["status"], "reviewed")
            self.assertEqual(client.patch(f"/api/jobs/{jid}/pages/0", json=decision).status_code, 409)
            text = client.get(f"/api/jobs/{jid}/export?format=txt&scope=reviewed")
            self.assertEqual(text.status_code, 200, text.text)
            self.assertIn("Corrected ordinary book text.", text.content.decode("utf-8-sig"))
            docx = client.get(f"/api/jobs/{jid}/export?format=docx&scope=reviewed")
            self.assertEqual(docx.status_code, 200, docx.text)
            with zipfile.ZipFile(io.BytesIO(docx.content)) as archive:
                document = archive.read("word/document.xml").decode("utf-8")
                self.assertIn("Corrected ordinary book text.", document)
            exported = client.get(f"/api/jobs/{jid}/export?format=json&scope=reviewed").json()
            self.assertEqual(len(exported["document"]["pages"]), 1)
            self.assertEqual(exported["review_events"][0]["token_id"], "page:0")

    def test_chapterless_review_exports_and_legacy_context(self):
        job = self.job()
        token = job["document"]["pages"][0]["tokens"][0]
        decision = self.decision()
        del decision["chapter"]
        with TestClient(create_app(self.store.root, self.engine)) as client:
            saved = client.patch(f"/api/jobs/{job['id']}/tokens/{token['id']}", json=decision)
            self.assertEqual(saved.status_code, 200, saved.text)
            self.assertEqual(saved.json()["chapter"], "Mind")
            # A legacy record retains its context, while a new review can omit it.
            saved = client.patch(f"/api/jobs/{job['id']}/tokens/{token['id']}",
                                 json={**decision, "expected_version": 1, "chapter": ""})
            self.assertEqual(saved.status_code, 200, saved.text)
            for fmt in ("json", "csv", "sqlite3", "sql"):
                response = client.get(f"/api/jobs/{job['id']}/export?format={fmt}&scope=reviewed")
                self.assertEqual(response.status_code, 200, response.text[:100])
            blob = client.get(f"/api/jobs/{job['id']}/export?format=sqlite3").content
            path = self.root / "chapterless.sqlite3"
            path.write_bytes(blob)
            with closing(sqlite3.connect(path)) as c:
                self.assertEqual(c.execute("SELECT chapter_name FROM rep_rubric").fetchone()[0], "")
                self.assertEqual(c.execute("PRAGMA foreign_key_check").fetchall(), [])
        self.assertNotIn("chapter-required", triage(machine_record(), .29, False, "", "Anxiety"))

    def test_page_zero_range_multipage_and_mismatch(self):
        image = Image.new("RGB", (120, 160), "white")
        blob = io.BytesIO()
        image.save(blob, format="TIFF", save_all=True, append_images=[image])
        with TestClient(create_app(self.root / "range-api", self.engine)) as client:
            for mode in ("plain", "structured"):
                for end in (None, 1, 5):
                    with self.subTest(mode=mode, end=end):
                        data = {"mode": mode, "start_page": "0"}
                        if end is not None:
                            data["end_page"] = str(end)
                        response = client.post("/api/jobs", data=data,
                            files=[("files", ("pages.tiff", blob.getvalue(), "image/tiff"))])
                        self.assertEqual(response.status_code, 202, response.text)
                        jid = response.json()["id"]
                        for _ in range(100):
                            job = client.get(f"/api/jobs/{jid}").json()
                            if job["status"] not in ("queued", "running"):
                                break
                            time.sleep(.01)
                        self.assertEqual(job["status"], "ready", job.get("error"))
                        doc = job["document"]
                        self.assertEqual([p["book_page"] for p in doc["pages"]], [0, 1])
                        self.assertEqual(doc["actual_end_page"], 1)
                        self.assertEqual(bool(doc["diagnostics"]), end == 5)
            for data in ({"start_page": "-1"}, {"start_page": "4", "end_page": "3"}):
                response = client.post("/api/jobs", data=data,
                    files=[("files", ("pages.tiff", blob.getvalue(), "image/tiff"))])
                self.assertEqual(response.status_code, 400, response.text)
            response = client.post("/api/jobs",
                files=[("files", ("pages.tiff", blob.getvalue(), "image/tiff"))])
            self.assertEqual(response.status_code, 202, response.text)
            self.assertEqual(response.json()["document"]["mode"], "plain")
            # Wait for the worker before the temporary directory is cleaned up.
            for _ in range(100):
                job = client.get(f"/api/jobs/{response.json()['id']}").json()
                if job["status"] not in ("queued", "running"):
                    break
                time.sleep(.01)
            self.assertEqual(job["status"], "ready", job.get("error"))

    def test_structured_upload_rejects_generated_overlay_images(self):
        self.assertIn("original scan", generated_overlay_reason(original_name="p029_overlay.png"))
        clean = self.root / "clean.png"
        Image.new("RGB", (200, 200), "white").save(clean)
        self.assertIsNone(generated_overlay_reason(clean, "page.png"))
        annotated = self.root / "renamed.png"
        image = Image.new("RGB", (300, 180), "white")
        from PIL import ImageDraw
        draw = ImageDraw.Draw(image)
        for index, color in enumerate(((198, 40, 40), (216, 120, 0), (26, 122, 60))):
            draw.rectangle((10 + index * 90, 20, 75 + index * 90, 150), outline=color, width=8)
        image.save(annotated)
        self.assertIn("rank-box overlay", generated_overlay_reason(annotated, "renamed.png"))
        with TestClient(create_app(self.root / "overlay-api", self.engine)) as client:
            response = client.post("/api/jobs", data={"mode": "structured", "title": "Bad input"},
                                   files=[("files", ("p029_overlay.png", annotated.read_bytes(), "image/png"))])
            self.assertEqual(response.status_code, 400, response.text)
            self.assertIn("original scan", response.json()["detail"])

    def test_management_correction_and_export_preview_api(self):
        with TestClient(create_app(self.root / "management-api", self.engine)) as client:
            blob = io.BytesIO()
            Image.new("RGB", (120, 160), "white").save(blob, format="PNG")
            response = client.post("/api/jobs", data={"mode": "structured", "title": "Managed"},
                                   files=[("files", ("scan.png", blob.getvalue(), "image/png"))])
            self.assertEqual(response.status_code, 202, response.text)
            jid = response.json()["id"]
            for _ in range(100):
                job = client.get(f"/api/jobs/{jid}").json()
                if job["status"] not in ("running", "queued"):
                    break
                time.sleep(.01)
            token = job["document"]["pages"][0]["tokens"][0]
            preview = client.get(f"/api/jobs/{jid}/export-preview?format=sqlite3&scope=draft").json()
            self.assertFalse(preview["valid"])
            self.assertEqual(preview["row_count"], 1)
            renamed = client.patch(f"/api/jobs/{jid}", json={"title": "Managed"})
            self.assertEqual(renamed.status_code, 200, renamed.text)
            batch = client.post(f"/api/jobs/{jid}/bulk-assign", json={
                "status": "needs_review", "chapter": "Mind", "rubric": "Anxiety", "reviewer": "QA"})
            self.assertEqual(batch.status_code, 200, batch.text)
            added = client.post(f"/api/jobs/{jid}/pages/0/tokens", json={
                "bbox": [3, 35, 45, 55], "remedy": "Bell.", "rubric": "Anxiety",
                "rank": 3, "reviewer": "QA"})
            self.assertEqual(added.status_code, 201, added.text)
            split = client.post(f"/api/jobs/{jid}/tokens/{token['id']}/split", json={
                "expected_version": 1, "remedies": ["Acon.", "Arn."], "reviewer": "QA"})
            self.assertEqual(split.status_code, 201, split.text)
            parts = split.json()
            merge = client.post(f"/api/jobs/{jid}/tokens/merge", json={
                "token_ids": [parts[0]["id"], parts[1]["id"]], "remedy": "Acon. Arn.",
                "rubric": "Anxiety", "rank": 2, "reviewer": "QA"})
            self.assertEqual(merge.status_code, 201, merge.text)
            deleted = client.delete(f"/api/jobs/{jid}")
            self.assertEqual(deleted.status_code, 204, deleted.text)
            self.assertEqual(client.get(f"/api/jobs/{jid}").status_code, 404)

    def test_management_api_reports_validation_and_processing_conflicts(self):
        app = create_app(self.root / "conflict-api", self.engine)
        with TestClient(app) as client:
            job = app.state.store.create("Processing")
            jid = job["id"]
            self.assertEqual(client.patch(f"/api/jobs/{jid}", json={"title": "  "}).status_code, 422)
            self.assertEqual(client.delete(f"/api/jobs/{jid}").status_code, 409)
            self.assertEqual(client.get(f"/api/jobs/{jid}").status_code, 200)

    def test_pipeline_requires_three_votes_and_records_ocr_confidence(self):
        from tpbocr import pipeline
        import numpy as np
        part = {"x": 10, "y": 10, "w": 50, "h": 20, "conf": 96}
        toks = [{"is_heading": True, "rubric": "Anxiety"},
                {"is_heading": False, "text": "Acon.,", "parts": [part]}]
        with patch.object(pipeline, "load_gray", return_value=np.full((100, 100), 255, np.uint8)), \
             patch.object(pipeline.segment, "tokens", return_value=toks), \
             patch.object(pipeline.features, "measure", return_value=machine_record()["features"]):
            doc, _ = pipeline.process("fixture.png")
        rem = doc["rubrics"][0]["remedies"][0]
        self.assertFalse(rem["agree"])
        self.assertTrue(rem["flag"])
        self.assertEqual(rem["ocr_confidence"], .96)
        with self.assertRaises(FileNotFoundError):
            pipeline.process("fixture.png", mlp_model_path=str(self.root / "missing.pkl"))


if __name__ == "__main__":
    unittest.main()
