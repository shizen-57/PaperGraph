"""Run the DocLens backend and frontend together on Windows: python start_app.py."""

import importlib.util
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import sys
import time


def main() -> int:
    app = Path(__file__).resolve().parent / "doclens"
    frontend = app / "frontend"
    next_cli = frontend / "node_modules" / "next" / "dist" / "bin" / "next"
    node = shutil.which("node")
    if not node:
        print("Node.js is missing. Install Node.js, then run this script again.", file=sys.stderr)
        return 1
    if not next_cli.is_file():
        print(f'Frontend dependencies are missing. Run npm install in "{frontend}".', file=sys.stderr)
        return 1
    if importlib.util.find_spec("uvicorn") is None:
        print(f'Backend dependencies are missing. Run: python -m pip install -r "{app / "requirements.txt"}"', file=sys.stderr)
        return 1

    for port in (8000, 3000):
        with socket.socket() as probe:
            try:
                probe.bind(("127.0.0.1", port))
            except OSError:
                print(f"Port {port} is unavailable. Stop the existing service, then try again.", file=sys.stderr)
                return 1

    services = [
        ("Backend", [sys.executable, "-u", "-m", "uvicorn", "backend.app:app", "--host", "127.0.0.1", "--port", "8000"], app),
        ("Frontend", [node, str(next_cli), "dev", "--hostname", "127.0.0.1", "--port", "3000"], frontend),
    ]
    processes: list[tuple[str, subprocess.Popen]] = []
    try:
        for name, command, directory in services:
            process = subprocess.Popen(command, cwd=directory, creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
            processes.append((name, process))
            print(f"Starting {name.lower()}...", flush=True)
        print("\nApp: http://127.0.0.1:3000\nAPI docs: http://127.0.0.1:8000/swagger\nPress Ctrl+C to stop both services.\n", flush=True)
        while True:
            for name, process in processes:
                code = process.poll()
                if code is not None:
                    print(f"\n{name} exited (code {code}). Stopping the app.", file=sys.stderr)
                    return code or 1
            time.sleep(0.25)
    except KeyboardInterrupt:
        print("\nStopping both services...", flush=True)
        return 0
    except OSError as error:
        print(f"Could not start DocLens: {error}", file=sys.stderr)
        return 1
    finally:
        # A second Ctrl+C must not interrupt cleanup and leave a server running.
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        for _, process in processes:
            if process.poll() is None:
                try:
                    process.send_signal(signal.CTRL_BREAK_EVENT)
                except OSError:
                    pass
        for _, process in processes:
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
                process.wait()


if __name__ == "__main__":
    raise SystemExit(main())
