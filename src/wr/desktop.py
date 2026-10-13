"""Native supervisor for the local Streamlit process. No tax logic lives here."""
from __future__ import annotations

import hmac
import json
import os
import queue
import secrets
import socket
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from wr.desktop_storage import (app_data_dir, app_version, prepare_workspace, selected_folder,
                                remember_language, remembered_language)
from wr.i18n import LANGUAGES, translator


class InstanceLock:
    def __init__(self, directory: Path):
        self.path = directory / "instance.lock"
        self.file = None

    def acquire(self) -> bool:
        self.file = self.path.open("a+b")
        self.file.seek(0)
        if not self.file.read(1):
            self.file.write(b"0")
            self.file.flush()
        self.file.seek(0)
        try:
            if sys.platform == "win32":
                import msvcrt
                msvcrt.locking(self.file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.file.close()
            self.file = None
            return False
        return True

    def close(self) -> None:
        if self.file:
            self.file.close()
            self.file = None


def control_request(endpoint: str, token: str, action: str, timeout: float = 120):
    request = urllib.request.Request(
        endpoint + "/" + action, data=b"", method="POST",
        headers={"X-WR-Token": token},
    )
    # Bypass environment proxies: local financial operations never go through one.
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request, timeout=timeout) as response:
        return json.load(response)


def desktop_request(action: str):
    return control_request(os.environ["WR_CONTROL_URL"], os.environ["WR_CONTROL_TOKEN"], action)


def make_control_server(token: str, dispatch):
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            if self.headers.get("Origin") or not hmac.compare_digest(self.headers.get("X-WR-Token", ""), token):
                self.send_error(403)
                return
            action = self.path.removeprefix("/")
            if action not in {"status", "folder", "stop"}:
                self.send_error(404)
                return
            try:
                result = dispatch(action)
                data = json.dumps(result).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            except Exception:
                self.send_error(503, "Launcher unavailable")

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    return server


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def child_command(config: Path, port: int) -> list[str]:
    prefix = [sys.executable] if getattr(sys, "frozen", False) else [sys.executable, "-m", "wr.desktop"]
    return [*prefix, "--serve", str(config), str(port)]


def serve(config: Path, port: int) -> None:
    from streamlit.web import bootstrap
    from wr.config import load_config
    from wr.import_pipeline import recompute
    settings = load_config(config)
    if settings.resolved_db_path.exists():
        # Recover derived results after an interrupted import before displaying them.
        recompute(settings.resolved_db_path, partner_config=settings.partners,
                  institution_options=settings.institution_options)
    import importlib.util
    app = Path(importlib.util.find_spec("dashboard").origin).parent / "app.py"
    # bootstrap is an internal API: pinned release dependencies and smoke tests protect it.
    options = {
        "global.developmentMode": False,
        "server.address": "127.0.0.1", "server.port": port,
        "browser.serverAddress": "127.0.0.1", "server.headless": True,
        "server.enableCORS": True, "server.enableXsrfProtection": True,
        "browser.gatherUsageStats": False, "server.fileWatcherType": "none",
        "server.enableStaticServing": False,
        "server.baseUrlPath": os.environ.get("WR_DASHBOARD_PATH", ""),
    }
    bootstrap.load_config_options(options)
    bootstrap.run(str(app), False, ["--config", str(config)], options)


def watch_parent() -> None:
    """Exit the server if the supervisor dies, including Task Manager termination."""
    parent = int(os.environ["WR_PARENT_PID"])
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.WaitForSingleObject.argtypes = (wintypes.HANDLE, wintypes.DWORD)
        kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
        handle = kernel.OpenProcess(0x00100000, False, parent)  # SYNCHRONIZE
        if not handle:
            os._exit(1)
        kernel.WaitForSingleObject(handle, 0xFFFFFFFF)
        kernel.CloseHandle(handle)
    else:
        while os.getppid() == parent:
            time.sleep(1)
    os._exit(0)


def main() -> int:
    if len(sys.argv) == 4 and sys.argv[1] == "--serve":
        if os.environ.get("WR_PARENT_PID"):
            threading.Thread(target=watch_parent, daemon=True).start()
        # PyInstaller windowed executables have no standard streams.
        log_path = Path(sys.argv[2]).parent / "server.log"
        if log_path.exists() and log_path.stat().st_size > 2 * 1024 * 1024:
            log_path.replace(log_path.with_suffix(".previous.log"))
        original_stdout, original_stderr = sys.stdout, sys.stderr
        with log_path.open("a", encoding="utf-8") as log:
            sys.stdout = sys.stderr = log
            try:
                serve(Path(sys.argv[2]), int(sys.argv[3]))
            except Exception:
                import traceback
                traceback.print_exc(file=log)
                return 1
            finally:
                sys.stdout, sys.stderr = original_stdout, original_stderr
        return 0
    if len(sys.argv) == 3 and sys.argv[1] == "--smoke-test":
        from wr.desktop_smoke import smoke_test
        smoke_test(Path(sys.argv[2]))
        return 0

    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk

    window = tk.Tk()
    window.title(f"Werkelijk Rendement {app_version()}")
    window.geometry("560x310")
    directory = app_data_dir()
    language = remembered_language(directory)
    t = translator(language)
    child = None
    server = None
    lock = None
    metadata = directory / "instance.json"
    events = queue.Queue()
    ready = False
    stopping = False

    def shutdown():
        nonlocal stopping
        if stopping:
            return
        stopping = True
        if child and child.poll() is None:
            child.terminate()
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait(timeout=5)
        if server:
            server.shutdown()
            server.server_close()
        metadata.unlink(missing_ok=True)
        if lock:
            lock.close()
        window.destroy()

    try:
        config = prepare_workspace(directory)
        lock = InstanceLock(directory)
        if not lock.acquire():
            # First launch may still be starting; wait for its authenticated endpoint.
            deadline = time.monotonic() + 40
            while time.monotonic() < deadline:
                try:
                    instance = json.loads(metadata.read_text())
                    status = control_request(instance["endpoint"], instance["token"], "status", 1)
                    if status["ready"]:
                        webbrowser.open(status["url"])
                        window.destroy()
                        return 0
                except (OSError, ValueError, KeyError):
                    pass
                time.sleep(0.2)
            raise RuntimeError(t("Another instance is still starting. Close it through its launcher and try again."))

        url = ""
        token = secrets.token_urlsafe(32)
        dashboard_path = secrets.token_urlsafe(24)

        def dispatch(action):
            if action == "status":
                return {"ready": ready, "url": url}
            response = queue.Queue(maxsize=1)
            events.put((action, response))
            return response.get(timeout=120)

        server = make_control_server(token, dispatch)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        endpoint = f"http://127.0.0.1:{server.server_port}"
        metadata.write_text(json.dumps({"endpoint": endpoint, "token": token}), encoding="utf-8")
        environment = {**os.environ, "WR_CONTROL_URL": endpoint, "WR_CONTROL_TOKEN": token,
                       "WR_PARENT_PID": str(os.getpid())}
        environment["WR_DASHBOARD_PATH"] = dashboard_path
        # Do not inherit a repository's Streamlit configuration.
        language_frame = tk.Frame(window)
        language_frame.pack(pady=8)
        tk.Label(language_frame, text="Language / Taal").pack(side="left", padx=8)
        language_choice = tk.StringVar(value=LANGUAGES[language])
        language_selector = ttk.Combobox(language_frame, textvariable=language_choice,
                                         values=list(LANGUAGES.values()), state="readonly", width=16)
        language_selector.pack(side="left")
        language_hint = tk.Label(window, text=t("Refresh the dashboard after changing language here."))
        language_hint.pack()
        status_label = tk.Label(window, text=t("Starting dashboard…"), wraplength=520)
        status_label.pack(pady=15)
        open_button = tk.Button(window, text=t("Open dashboard"), command=lambda: ready and webbrowser.open(url))
        open_button.pack()
        data_button = tk.Button(window, text=t("Open local data"), command=lambda: os.startfile(directory) if sys.platform == "win32" else None)
        data_button.pack(pady=5)
        exit_button = tk.Button(window, text=t("Exit"), command=shutdown)
        exit_button.pack()

        def update_language(value):
            nonlocal language, t
            language = value
            t = translator(language)
            language_choice.set(LANGUAGES[language])
            language_hint.config(text=t("Refresh the dashboard after changing language here."))
            status_label.config(text=t("Dashboard running. Close this window to exit.") if ready else t("Starting dashboard…"))
            open_button.config(text=t("Open dashboard"))
            data_button.config(text=t("Open local data"))
            exit_button.config(text=t("Exit"))

        def choose_language(_event):
            value = next(code for code, label in LANGUAGES.items() if label == language_choice.get())
            try:
                remember_language(directory, value)
                update_language(value)
            except OSError as exc:
                messagebox.showerror("Werkelijk Rendement", t("Could not save language preference: {error}", error=exc), parent=window)

        language_selector.bind("<<ComboboxSelected>>", choose_language)
        window.protocol("WM_DELETE_WINDOW", shutdown)
        attempts = 0
        deadline = 0.0

        def start_child():
            nonlocal child, attempts, deadline, url
            attempts += 1
            port = free_port()
            url = f"http://127.0.0.1:{port}/{dashboard_path}"
            child = subprocess.Popen(child_command(config, port), cwd=directory, env=environment,
                                     creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0)
            deadline = time.monotonic() + 40

        def tick():
            nonlocal ready
            try:
                saved_language = remembered_language(directory)
                if saved_language != language:
                    update_language(saved_language)
                if child.poll() is not None:
                    if not ready and attempts < 3:
                        start_child()
                    else:
                        raise RuntimeError(t("Dashboard stopped. See {log}.", log=directory / "server.log"))
                if not ready:
                    try:
                        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
                        with opener.open(url + "/_stcore/health", timeout=0.2) as response:
                            healthy = response.read() == b"ok"
                        if healthy and child.poll() is None:
                            ready = True
                            status_label.config(text=t("Dashboard running. Close this window to exit."))
                            webbrowser.open(url)
                    except OSError:
                        pass
                    if not ready and time.monotonic() > deadline:
                        raise RuntimeError(t("Startup is taking too long. See {log}.", log=directory / "server.log"))
                while not events.empty():
                    action, response = events.get_nowait()
                    if action == "folder":
                        folder = filedialog.askdirectory(parent=window, title=t("Select folder"), initialdir=selected_folder(directory) or str(Path.home()), mustexist=True)
                        response.put({"folder": folder or None})
                    else:
                        response.put({"stopping": True})
                        window.after(100, shutdown)
                window.after(200, tick)
            except Exception as exc:
                messagebox.showerror("Werkelijk Rendement", str(exc), parent=window)
                shutdown()

        start_child()
        window.after(200, tick)
        window.mainloop()
        return 0
    except Exception as exc:
        messagebox.showerror("Werkelijk Rendement", str(exc), parent=window)
        # A failed second instance must never delete the first instance's metadata.
        if lock and lock.file:
            shutdown()
        else:
            window.destroy()
        return 1
    finally:
        if lock and lock.file:
            shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
