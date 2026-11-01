import argparse
import os
from contextlib import contextmanager

from .dependencies import ROOT, runtime_environment, system_report


@contextmanager
def app_lock(root=ROOT):
    """Prevent setup from replacing packages while an app instance is using them."""
    with (root / ".folio-app.lock").open("a+b") as lock:
        if lock.tell() == 0:
            lock.write(b"0")
            lock.flush()
        lock.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise RuntimeError("Folio is already running in this folder. Close its server before starting another instance.")
        try:
            yield
        finally:
            lock.seek(0)
            if os.name == "nt":
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(lock, fcntl.LOCK_UN)


def main():
    parser = argparse.ArgumentParser(description="Folio local scan transcription and format-aware OCR review")
    parser.add_argument("--port", type=int, default=8788)
    parser.add_argument("--data-dir", default=None)
    parser.add_argument("--tess", default=None)
    parser.add_argument("--models", default=None, help="Directory containing trusted mlp_model.pkl and shape_model.pkl")
    parser.add_argument("--check-dependencies", action="store_true", help="Check this runtime without importing the app")
    args = parser.parse_args()
    if args.tess:
        os.environ["TESSERACT_CMD"] = args.tess
    if args.models:
        os.environ["FORMAT_OCR_MODELS"] = args.models
    os.environ.update(runtime_environment())
    if args.check_dependencies:
        import json
        report = system_report()
        print(json.dumps(report, indent=2, ensure_ascii=True))
        return 0 if report["ready"] else 1
    with app_lock():
        try:
            from .server import create_app
            import uvicorn
        except (ImportError, OSError) as exc:
            print(f"Folio dependency error: {exc}\nOpen setup_folio.bat to install/repair this environment.")
            return 1
        import json
        runtime_file = ROOT / ".folio-runtime.json"
        runtime_file.write_text(json.dumps({"port": args.port, "pid": os.getpid()}), encoding="utf-8")
        try:
            app = create_app(args.data_dir)
            server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=args.port))
            app.state.setup_stop = lambda: setattr(server, "should_exit", True)
            server.run()
        finally:
            runtime_file.unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
