"""Setup regression tests run without third-party packages or network access."""
import io
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from formatocr import dependencies as deps
from formatocr.__main__ import app_lock
from setup_folio import SetupManager, active_app_url, app_is_running, make_handler


def ready_checks():
    return [{"id": name, "name": name, "required": name == "eng", "status": "ready"}
            for name in ("python", "numpy", "tesseract", "eng", "hin")]


class DependencyTests(unittest.TestCase):
    def test_checker_runs_with_only_standard_library(self):
        command = [sys.executable, "-I", "-S", "-c",
                   "import sys;sys.path.insert(0,sys.argv[1]);from formatocr.dependencies import check_python;"
                   "assert check_python(sys.executable)['status']=='ready';import setup_folio",
                   str(deps.ROOT)]
        self.assertEqual(subprocess.run(command, capture_output=True).returncode, 0)

    def test_missing_python_is_a_report_not_a_crash(self):
        with tempfile.TemporaryDirectory() as scratch:
            report = deps.system_report(scratch, python=Path(scratch) / "no-python", tess="missing-tesseract")
        self.assertFalse(report["ready"])
        self.assertEqual(report["checks"][0]["status"], "error")
        self.assertEqual(len(report["checks"]), 15)

    def test_old_or_32bit_python_is_rejected(self):
        for version, bits in (([3, 9, 9], 64), ([3, 12, 0], 32)):
            with self.subTest(version=version, bits=bits), patch.object(deps, "run_capture", return_value=SimpleNamespace(returncode=0, stdout=json.dumps({"version":version,"bits":bits}))):
                self.assertEqual(deps.check_python("python")["status"], "error")

    def test_native_probe_errors_become_actionable_cards(self):
        with patch.object(deps, "run_capture", side_effect=subprocess.TimeoutExpired("python", 60)):
            cards = deps.check_packages("python")
        self.assertEqual(len(cards), 9)
        self.assertTrue(all(c["status"] == "error" for c in cards))

    def test_tesseract_v_prefix_and_languages_are_verified(self):
        calls = []
        def fake(command, **kwargs):
            calls.append(command)
            text = "tesseract v5.4.0.20240606\nleptonica" if "--version" in command else "List of available languages (2):\neng\nhin\n" if "--list-langs" in command else ""
            return SimpleNamespace(returncode=0, stdout=text, stderr="")
        with patch.object(deps, "run_capture", side_effect=fake):
            cards = deps.check_tesseract("tesseract")
        self.assertTrue(all(c["status"] == "ready" for c in cards))
        self.assertEqual(len(calls), 4)  # Two actual native language-load tests.

    def test_corrupt_language_is_not_reported_ready(self):
        def fake(command, **kwargs):
            if "--version" in command:
                return SimpleNamespace(returncode=0, stdout="tesseract 5.4", stderr="")
            if "--list-langs" in command:
                return SimpleNamespace(returncode=0, stdout="eng\nhin\n", stderr="")
            return SimpleNamespace(returncode=1 if "hin" in command else 0, stdout="", stderr="Failed to load language")
        with patch.object(deps, "run_capture", side_effect=fake):
            cards = deps.check_tesseract("tesseract")
        self.assertEqual(cards[1]["status"], "ready")
        self.assertEqual(cards[2]["status"], "warning")
        self.assertIn("unreadable", cards[2]["detail"])

    def test_local_languages_do_not_hide_system_data_until_complete(self):
        with tempfile.TemporaryDirectory() as scratch, patch.dict(os.environ, {"TESSDATA_PREFIX":"system-data"}):
            folder = Path(scratch) / "tessdata"; folder.mkdir()
            (folder / "eng.traineddata").write_bytes(b"eng")
            self.assertEqual(deps.tessdata_path(scratch), "system-data")
            (folder / "hin.traineddata").write_bytes(b"hin")
            self.assertEqual(deps.tessdata_path(scratch), str(folder))

    def test_optional_models_do_not_block_text_ocr(self):
        with tempfile.TemporaryDirectory() as scratch, patch.object(deps, "check_python", return_value={"id":"python","required":True,"status":"ready"}), patch.object(deps, "check_packages", return_value=[]), patch.object(deps, "check_tesseract", return_value=ready_checks()[2:]):
            report = deps.system_report(scratch)
        self.assertTrue(report["ready"])
        self.assertFalse(report["models_present"])
        self.assertTrue(report["hindi_ready"])

    def test_package_requirements_match_project(self):
        # Python 3.10 may not have tomllib; compare the declared dependency strings.
        project = (deps.ROOT / "pyproject.toml").read_text()
        for name, _, minimum, maximum in deps.PACKAGES:
            self.assertIn(f'"{name}>={minimum},<{maximum}"', project)


class SetupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.manager = SetupManager(self.root)

    def tearDown(self):
        self.temp.cleanup()

    def test_installer_cannot_run_while_app_holds_lock(self):
        self.assertFalse(app_is_running(self.root))
        with app_lock(self.root):
            self.assertTrue(app_is_running(self.root))
            with self.assertRaisesRegex(RuntimeError, "Close Folio"):
                self.manager.start("packages")
        self.assertFalse(app_is_running(self.root))

    def test_unknown_actions_and_concurrent_actions_rejected(self):
        with self.assertRaises(ValueError): self.manager.start("execute-shell")
        self.manager.state["phase"] = "running"
        with self.assertRaises(RuntimeError): self.manager.start("packages")
        with self.assertRaises(RuntimeError): self.manager.start("stop")

    def test_failure_has_log_and_can_be_retried(self):
        self.manager.state["phase"] = "running"
        with patch.object(self.manager, "_packages", side_effect=RuntimeError("network unavailable")):
            self.manager._worker("packages")
        self.assertEqual(self.manager.state["phase"], "failed")
        self.assertIn("network unavailable", self.manager.log_path.read_text())
        with patch.object(self.manager, "_packages"), patch.object(self.manager, "status", return_value={"checks":ready_checks()}):
            self.manager._worker("packages")
        self.assertEqual(self.manager.state["phase"], "complete")

    def test_status_polling_does_not_repeat_expensive_imports(self):
        with patch("setup_folio.system_report", return_value={"checks":ready_checks(),"ready":True}) as probe:
            self.manager.status(); self.manager.status(); self.manager.status(refresh=True)
        self.assertEqual(probe.call_count, 2)

    def test_running_app_dependencies_are_not_marked_missing_when_local_venv_is_absent(self):
        report = {"root":str(self.root), "python":"existing-environment/python.exe", "checks":ready_checks(), "ready":True}
        with patch('setup_folio.app_is_running', return_value=True), patch('setup_folio.urllib.request.urlopen', return_value=io.BytesIO(json.dumps(report).encode())), patch('setup_folio.system_report') as local_probe:
            actual = self.manager.status()
        self.assertTrue(actual['ready'])
        self.assertEqual(actual['environment_source'], 'running_app')
        self.assertFalse(actual['local_environment']['exists'])
        self.assertTrue(all(c['status'] == 'ready' for c in actual['checks']))
        local_probe.assert_not_called()

    def test_uncreated_local_environment_has_unchecked_packages_not_missing_packages(self):
        report = self.manager.status()
        self.assertEqual(report['environment_source'], 'local')
        self.assertEqual(report['checks'][0]['status'], 'warning')
        self.assertTrue(all(c['status'] == 'unchecked' for c in report['checks'][1:10]))
        self.assertFalse(report['ready'])

    def test_active_environment_report_rejects_another_project(self):
        report = {"root":str(self.root.parent), "python":"another-project/python.exe", "checks":ready_checks(), "ready":True}
        with patch('setup_folio.app_is_running', return_value=True), patch('setup_folio.urllib.request.urlopen', return_value=io.BytesIO(json.dumps(report).encode())):
            actual = self.manager.status()
        self.assertEqual(actual['environment_source'], 'local')
        self.assertIn('could not be verified', actual['environment_warning'])
        self.assertFalse(actual['ready'])

    def test_status_changes_back_to_local_environment_when_app_stops(self):
        report = {"root":str(self.root), "python":"existing/python.exe", "checks":ready_checks(), "ready":True}
        with patch('setup_folio.app_is_running', side_effect=[True, False]), patch('setup_folio.urllib.request.urlopen', return_value=io.BytesIO(json.dumps(report).encode())):
            self.assertTrue(self.manager.status()['ready'])
            self.assertEqual(self.manager.status()['environment_source'], 'local')

    def test_existing_app_link_uses_its_actual_port(self):
        (self.root / '.folio-runtime.json').write_text(json.dumps({'port':8791}))
        self.assertEqual(active_app_url(self.root), 'http://127.0.0.1:8791/')
        (self.root / '.folio-runtime.json').write_text(json.dumps({'port':'https://evil.example'}))
        self.assertEqual(active_app_url(self.root), 'http://127.0.0.1:8788/')

    def test_language_download_is_validated_and_keeps_working_files_on_failure(self):
        folder = self.root / "tessdata"; folder.mkdir()
        (folder / "eng.traineddata").write_bytes(b"old english")
        (folder / "hin.traineddata").write_bytes(b"old hindi")
        executable = self.root / "tesseract.exe"; executable.touch()
        response = io.BytesIO(b"x" * 2048); response.headers = {"Content-Length":"2048"}
        with patch("setup_folio.resolve_tesseract", return_value=str(executable)), patch("setup_folio.urllib.request.urlopen", side_effect=[response, OSError("connection lost")]), patch("setup_folio.run_capture", return_value=SimpleNamespace(returncode=0, stderr="")):
            with self.assertRaises(OSError): self.manager._languages()
        self.assertEqual((folder / "eng.traineddata").read_bytes(), b"old english")
        self.assertEqual((folder / "hin.traineddata").read_bytes(), b"old hindi")
        self.assertFalse(list(folder.glob("*.download")))

    def test_language_download_success_and_native_rejection(self):
        executable = self.root / "tesseract.exe"; executable.touch()
        def download(*args, **kwargs):
            response = io.BytesIO(b"x" * 2048); response.headers = {"Content-Length":"2048"}; return response
        with patch("setup_folio.resolve_tesseract", return_value=str(executable)), patch("setup_folio.urllib.request.urlopen", side_effect=download), patch("setup_folio.run_capture", return_value=SimpleNamespace(returncode=0, stderr="")):
            self.manager._languages()
        self.assertTrue((self.root / "tessdata/eng.traineddata").is_file())
        with patch("setup_folio.resolve_tesseract", return_value=str(executable)), patch("setup_folio.urllib.request.urlopen", side_effect=download), patch("setup_folio.run_capture", return_value=SimpleNamespace(returncode=1, stderr="bad data")):
            with self.assertRaisesRegex(ValueError, "rejected"): self.manager._languages()
        self.assertEqual((self.root / "tessdata/eng.traineddata").stat().st_size, 2048)

    def test_http_requires_local_host_and_action_token(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(self.manager, "test-token"))
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        url = f"http://127.0.0.1:{server.server_port}"
        def post(headers, payload=None):
            request = urllib.request.Request(url + "/api/setup/action", data=json.dumps(payload or {"action":"packages"}).encode(), headers=headers)
            try:
                return urllib.request.urlopen(request).status
            except urllib.error.HTTPError as exc:
                code = exc.code
                exc.close()
                return code
        try:
            self.assertEqual(post({}), 403)
            self.assertEqual(post({"X-Folio-Setup":"test-token","Origin":"https://evil.example"}), 403)
            self.assertEqual(post({"X-Folio-Setup":"test-token","Host":"evil.example"}), 403)
            with patch.object(self.manager, "start") as start:
                self.assertEqual(post({"X-Folio-Setup":"test-token","Origin":url}), 202)
                start.assert_called_once_with("packages")
            with urllib.request.urlopen(url + "/static/setup.js?v=1") as result:
                self.assertEqual(result.status, 200)
            try:
                urllib.request.urlopen(url + "/../pyproject.toml")
                self.fail('Unexpected directory traversal access')
            except urllib.error.HTTPError as exc:
                self.assertEqual(exc.code, 404)
                exc.close()
        finally:
            server.shutdown(); server.server_close(); thread.join()


if __name__ == "__main__":
    unittest.main()
