"""Local setup wizard. Requires only Python 3.10+; no FastAPI or pip packages."""
import argparse
import hashlib
import json
import os
import secrets
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from formatocr.dependencies import (ROOT, PACKAGES, check_python, local_python, resolve_tesseract,
                                    run_capture, runtime_environment, system_report)


def app_is_running(root=ROOT):
    """The app holds this lock for its lifetime, including manual starts."""
    path = Path(root) / ".folio-app.lock"
    if not path.exists():
        return False
    try:
        with open(path, "r+b") as lock:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                fcntl.flock(lock, fcntl.LOCK_UN)
        return False
    except (OSError, PermissionError):
        return True


def active_app_url(root=ROOT, default_port=8788):
    try:
        port = json.loads((Path(root) / ".folio-runtime.json").read_text(encoding="utf-8"))["port"]
        if not isinstance(port, int) or not 1 <= port <= 65535:
            raise ValueError("Invalid runtime port")
    except (OSError, ValueError, KeyError):
        port = default_port
    return f"http://127.0.0.1:{port}/"


class SetupManager:
    def __init__(self, root=ROOT, app_port=8788, data_dir=None):
        self.root = Path(root)
        self.app_port = app_port
        self.data_dir = data_dir
        self.python = local_python(self.root)
        self.lock = threading.Lock()
        self.cache_lock = threading.Lock()
        self.report = None
        self.report_at = 0
        self.report_source = None
        self.state = {"phase": "idle", "action": None, "message": "Ready to check this computer.", "log": []}
        self.log_path = self.root / "setup-status.log"
        self.app_process = None
        self.app_stop_token = None

    def log(self, message):
        message = str(message).rstrip()[-2000:]
        with self.lock:
            self.state["log"] = (self.state["log"] + [message])[-120:]
        with self.log_path.open("a", encoding="utf-8") as out:
            out.write(message + "\n")

    def _dependency_report(self, running, refresh):
        failure = None
        if running:
            url = active_app_url(self.root, self.app_port) + "api/setup/status"
            try:
                with urllib.request.urlopen(url + ("?refresh=1" if refresh else ""), timeout=75) as response:
                    report = json.load(response)
                if (Path(report["root"]).resolve() != self.root.resolve() or
                        not isinstance(report["checks"], list) or not report.get("python")):
                    raise ValueError("The status response does not belong to this app folder.")
                report["environment_source"] = "running_app"
                report["checks"][0]["name"] = "Python used by running Folio"
                return report
            except (OSError, ValueError, KeyError, TypeError) as exc:
                failure = f"The running app's environment could not be verified. Showing the local .venv instead. Recheck after the app responds. {str(exc)[:200]}"
        report = system_report(self.root, python=self.python)
        report["environment_source"] = "local"
        py_check = report["checks"][0]
        py_check["name"] = "Local app Python environment"
        if not self.python.exists():
            py_check.update(status="warning", detail="The local .venv has not been created. This does not mean Python is missing from the computer. Install / repair packages creates this app's environment.")
            for item in report["checks"][1:1 + len(PACKAGES)]:
                item.update(status="unchecked", detail="Not checked: create the local app environment first. Packages installed in other Python environments are separate.")
            report["ready"] = False
            report["hindi_ready"] = False
        if failure:
            report["environment_warning"] = failure
        return report

    def status(self, refresh=False):
        with self.lock:
            state = {**self.state, "log": list(self.state["log"])}
        installing = state["phase"] == "running" and state["action"] in ("packages", "tesseract", "languages")
        running = not installing and app_is_running(self.root)
        source = (running, active_app_url(self.root, self.app_port) if running else str(self.python))
        # Reprobe when the app starts/stops as well as on explicit refresh.
        with self.cache_lock:
            if self.report is None or refresh or self.report_source != source:
                self.report = self._dependency_report(running, refresh)
                self.report_source = source
                self.report_at = time.time()
            report = self.report.copy()
        return {**report, "task": state, "read_only": False,
                "app_running": running,
                "app_owned": self.app_process is not None and self.app_process.poll() is None,
                "local_environment": {"path": str(self.python), "exists": self.python.is_file()},
                "app_url": active_app_url(self.root, self.app_port) if running else f"http://127.0.0.1:{self.app_port}/"}

    def start(self, action):
        if action not in ("packages", "tesseract", "languages", "launch", "stop"):
            raise ValueError("Choose a supported setup action.")
        with self.lock:
            if self.state["phase"] == "running":
                raise RuntimeError("Another setup action is running. Wait for it to finish.")
            if action == "stop" and (self.app_process is None or self.app_process.poll() is not None):
                raise RuntimeError("This setup window did not start the running app. Close its server window instead.")
            if action != "stop" and app_is_running(self.root):
                raise RuntimeError("Close Folio's server window before changing dependencies or starting another instance.")
            self.state = {"phase": "running", "action": action, "message": "Starting…", "log": []}
        threading.Thread(target=self._worker, args=(action,), daemon=False).start()

    def _command(self, command, timeout=1200):
        self.log("Running: " + subprocess.list2cmdline([str(arg) for arg in command]))
        with self.lock:
            self.state["message"] = "Installation is running. Download and installer details appear in the log below."
        kwargs = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}
        # Write output to a file, not PIPE, so timeouts cannot leave a blocked reader.
        output = self.root / "setup-command.log"
        with output.open("w", encoding="utf-8") as sink:
            process = subprocess.Popen([str(arg) for arg in command], cwd=self.root,
                                       stdout=sink, stderr=subprocess.STDOUT, **kwargs)
            offset, started = 0, time.monotonic()
            while True:
                time.sleep(0.3)
                with output.open(encoding="utf-8", errors="replace") as source:
                    source.seek(offset)
                    chunk = source.read()
                    offset = source.tell()
                if chunk:
                    self.log(chunk)
                code = process.poll()
                if code is not None:
                    break
                if time.monotonic() - started > timeout:
                    process.kill()
                    process.wait()
                    raise RuntimeError("Installation timed out. Check setup-command.log and retry.")
        if code:
            raise RuntimeError(f"Installer exited with code {code}. See the installation log. Check internet access and retry.")

    def _packages(self):
        if check_python(sys.executable)["status"] != "ready":
            raise RuntimeError("Run setup with Python 3.10+ (64-bit).")
        if not self.python.exists():
            self.log("Creating the project-local .venv environment…")
            self._command([sys.executable, "-m", "venv", str(self.root / ".venv")], timeout=120)
        if check_python(self.python)["status"] != "ready":
            raise RuntimeError("The copied .venv is unusable. Rename it and rerun setup; create a fresh environment on each computer.")
        self._command([self.python, "-m", "ensurepip", "--upgrade"], timeout=120)
        requirements = [f"{name}>={minimum},<{maximum}" for name, _, minimum, maximum in PACKAGES]
        self.log("Downloading and repairing app dependencies from PyPI…")
        self._command([self.python, "-m", "pip", "install", "--upgrade", "--force-reinstall", *requirements,
                       "-e", str(self.root)])

    def _tesseract(self):
        winget = shutil.which("winget")
        if os.name != "nt" or not winget:
            raise RuntimeError("Windows App Installer (winget) is unavailable. Use the Tesseract download link, install it, then click Recheck.")
        self.log("Installing Tesseract through Windows Package Manager. Windows may request administrator permission.")
        self._command([winget, "install", "--id", "UB-Mannheim.TesseractOCR", "--exact", "--source", "winget",
                       "--accept-package-agreements", "--accept-source-agreements", "--disable-interactivity"], timeout=900)

    def _languages(self):
        tess = resolve_tesseract()
        if not Path(tess).is_file():
            raise RuntimeError("Install Tesseract before downloading language data.")
        folder = self.root / "tessdata"
        folder.mkdir(exist_ok=True)
        staged = []
        try:
            for lang in ("eng", "hin"):
                url = f"https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/main/{lang}.traineddata"
                target = folder / f"{lang}.traineddata.download"
                staged.append((target, folder / f"{lang}.traineddata"))
                self.log(f"Downloading {lang}.traineddata from the Tesseract project's tessdata_fast repository…")
                digest, received = hashlib.sha256(), 0
                with urllib.request.urlopen(url, timeout=45) as response, target.open("wb") as out:
                    total = int(response.headers.get("Content-Length", 0))
                    while block := response.read(256 * 1024):
                        received += len(block)
                        if received > 50 * 1024 * 1024:
                            raise ValueError("Language pack exceeds the 50 MB limit.")
                        out.write(block)
                        digest.update(block)
                        with self.lock:
                            self.state["message"] = f"Downloading {lang}: {received // 1024} KB" + (f" / {total // 1024} KB" if total else "")
                if received < 1024 or (total and received != total):
                    raise ValueError("Language pack download was incomplete. Retry with a working connection.")
                # Validate the native data format before replacing a working pack.
                # --list-langs lists names only. Use an actual tiny OCR pass below.
                probe = self.root / ".setup-language-probe.pgm"
                probe.write_bytes(b"P5\n100 100\n255\n" + b"\xff" * 10000)
                # Tesseract expects .traineddata: validate each download in its own temporary directory.
                import tempfile
                with tempfile.TemporaryDirectory(dir=folder) as scratch:
                    shutil.copyfile(target, Path(scratch) / f"{lang}.traineddata")
                    checked = run_capture([tess, str(probe), "stdout", "--tessdata-dir", scratch,
                                           "-l", lang, "--psm", "6"], timeout=30)
                if checked.returncode:
                    raise ValueError(f"Tesseract rejected {lang} language data: {checked.stderr[-500:]}")
                self.log(f"Verified {lang}: {received:,} bytes · SHA-256 {digest.hexdigest()}")
            for source, destination in staged:
                source.replace(destination)
            self.log("English and Hindi installed in the local tessdata folder. No Program Files write is needed.")
        finally:
            for source, _ in staged:
                source.unlink(missing_ok=True)
            (self.root / ".setup-language-probe.pgm").unlink(missing_ok=True)

    def _launch(self):
        report = system_report(self.root, python=self.python)
        if not report["ready"]:
            raise RuntimeError("Resolve required dependencies before starting Folio.")
        with socket.socket() as test:
            try:
                test.bind(("127.0.0.1", self.app_port))
            except OSError:
                raise RuntimeError(f"Port {self.app_port} is already in use. Close the older server or choose another port.")
        data = self.data_dir or ("dev-data" if (self.root / "dev-data").is_dir() else "app-data")
        command = [str(self.python), "-B", "-m", "formatocr", "--port", str(self.app_port), "--data-dir", data]
        kwargs = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {"start_new_session": True}
        env = runtime_environment(self.root)
        self.app_stop_token = secrets.token_urlsafe(32)
        env["FOLIO_SETUP_STOP_TOKEN"] = self.app_stop_token
        with (self.root / "folio-server.log").open("a", encoding="utf-8") as output:
            process = subprocess.Popen(command, cwd=self.root, stdout=output, stderr=subprocess.STDOUT,
                                       env=env, **kwargs)
        self.app_process = process
        url = f"http://127.0.0.1:{self.app_port}/"
        for _ in range(60):
            if process.poll() is not None:
                raise RuntimeError("Folio could not start. See folio-server.log for the error.")
            try:
                with urllib.request.urlopen(url + "api/health", timeout=1) as response:
                    if response.status == 200:
                        self.log(f"Folio is running at {url}")
                        return
            except OSError:
                time.sleep(0.5)
        raise RuntimeError("Folio is taking too long to start. Check folio-server.log before retrying.")

    def _stop(self):
        # Ask the actual server to exit, rather than killing the Windows venv shim.
        request = urllib.request.Request(f"http://127.0.0.1:{self.app_port}/api/setup/stop", data=b"{}",
                                         headers={"X-Folio-Setup": self.app_stop_token or ""})
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                if response.status != 204:
                    raise RuntimeError("Folio did not confirm shutdown.")
        except urllib.error.HTTPError as exc:
            try:
                message = json.load(exc).get("detail", "Folio could not be stopped.")
            finally:
                exc.close()
            raise RuntimeError(message)
        self.app_process.wait(timeout=15)
        self.app_process = None
        self.app_stop_token = None
        self.log("Folio stopped. Saved documents were retained.")

    def _worker(self, action):
        try:
            self.log(f"Setup action: {action}")
            if action in ("packages", "tesseract", "languages"):
                from formatocr.__main__ import app_lock
                with app_lock(self.root):
                    getattr(self, "_" + action)()
            else:
                getattr(self, "_" + action)()
            report = self.status(refresh=True)
            if action == "packages" and any(c["status"] != "ready" for c in report["checks"][:10]):
                raise RuntimeError("Packages installed, but verification failed. See the dependency cards; repair and recheck.")
            if action == "tesseract" and next(c for c in report["checks"] if c["id"] == "tesseract")["status"] != "ready":
                raise RuntimeError("Installer completed but Tesseract is not detected. Restart setup or use the manual install instructions.")
            if action == "languages" and not all(c["status"] == "ready" for c in report["checks"] if c["id"] in ("eng", "hin")):
                raise RuntimeError("Language files downloaded, but Tesseract verification failed. Check the cards and retry.")
            with self.lock:
                self.state.update(phase="complete", message="Folio is running. Open Folio below." if action == "launch" else "Completed. Dependency status has been refreshed.")
        except Exception as exc:
            self.log(f"ERROR: {exc}")
            with self.lock:
                self.state.update(phase="failed", message=str(exc))
            with self.cache_lock:
                self.report = None


def make_handler(manager, token):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def send(self, status, body, content_type="application/json; charset=utf-8"):
            payload = json.dumps(body).encode() if not isinstance(body, bytes) else body
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; frame-ancestors 'self'; base-uri 'none'")
            self.end_headers()
            self.wfile.write(payload)

        def valid_host(self):
            return self.headers.get("Host") in (f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}")

        def do_GET(self):
            if not self.valid_host():
                return self.send(403, {"detail": "Invalid local host."})
            route = self.path.split("?", 1)[0]
            if route == "/api/setup/status":
                return self.send(200, {**manager.status(refresh="refresh=1" in self.path), "token": token})
            files = {"/": ("setup.html", "text/html; charset=utf-8"), "/setup": ("setup.html", "text/html; charset=utf-8"),
                     "/static/setup.js": ("setup.js", "text/javascript; charset=utf-8"),
                     "/static/setup.css": ("setup.css", "text/css; charset=utf-8")}
            if route not in files:
                return self.send(404, {"detail": "Not found"})
            name, kind = files[route]
            return self.send(200, (ROOT / "formatocr/static" / name).read_bytes(), kind)

        def do_POST(self):
            if not self.valid_host():
                return self.send(403, {"detail": "Invalid local host."})
            expected = f"http://{self.headers.get('Host')}"
            if (self.headers.get("Origin") not in (None, expected) or
                    self.headers.get("X-Folio-Setup") != token):
                return self.send(403, {"detail": "Open the local setup page to perform this action."})
            if self.path != "/api/setup/action":
                return self.send(404, {"detail": "Not found"})
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length < 2048:
                    raise ValueError("Invalid request size.")
                body = json.loads(self.rfile.read(length))
                manager.start(body.get("action"))
                self.send(202, {"started": True})
            except (ValueError, AttributeError) as exc:
                self.send(400, {"detail": str(exc)})
            except RuntimeError as exc:
                self.send(409, {"detail": str(exc)})
    return Handler


def main():
    parser = argparse.ArgumentParser(description="Folio dependency setup")
    parser.add_argument("--launch", action="store_true", help="Start Folio directly if the local environment is ready")
    parser.add_argument("--check", action="store_true", help="Print a dependency report and exit")
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--port", type=int, default=8790, help="Setup page port (loopback only)")
    parser.add_argument("--app-port", type=int, default=8788)
    parser.add_argument("--data-dir")
    args = parser.parse_args()
    manager = SetupManager(app_port=args.app_port, data_dir=args.data_dir)
    if args.check:
        report = manager.status()
        print(json.dumps(report, indent=2, ensure_ascii=True))
        return 0 if report["ready"] else 1
    if args.launch and app_is_running(ROOT):
        url = active_app_url(ROOT, args.app_port)
        print(f"Folio is already running at {url}. Close its server before changing the data folder or port.")
        if not args.no_browser:
            webbrowser.open(url)
        return 0
    if args.launch and manager.status()["ready"]:
        # Foreground mode preserves the familiar "close this window to stop" launcher.
        data = args.data_dir or ("dev-data" if (ROOT / "dev-data").is_dir() else "app-data")
        if not args.no_browser:
            webbrowser.open(f"http://127.0.0.1:{args.app_port}/")
        return subprocess.call([str(manager.python), "-B", "-m", "formatocr", "--port", str(args.app_port),
                                "--data-dir", data], cwd=ROOT, env=runtime_environment())
    try:
        server = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(manager, secrets.token_urlsafe(32)))
    except OSError:
        print(f"Setup port {args.port} is busy. Close the previous setup window or use --port with another port.")
        return 1
    url = f"http://127.0.0.1:{server.server_port}/"
    print(f"Folio setup: {url}\nKeep this window open during setup. Press Ctrl+C to stop the setup service.")
    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
