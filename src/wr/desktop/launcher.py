from __future__ import annotations

from pathlib import Path
import os
import queue
import secrets
import subprocess
import sys
import threading
import time
import urllib.request

from wr.desktop.control import control_request, free_port, make_control_server
from wr.desktop.lock import InstanceLock
from wr.desktop.platform import open_external
from wr.desktop.process import child_command, watch_parent
from wr.desktop.server import serve
from wr.desktop.storage import app_data_dir, prepare_workspace, selected_folder, remembered_language
from wr.i18n import translator
from wr.messages import Messages
from wr.models.desktop import DataResponse, FolderResponse, InstanceMetadata, StatusResponse, StopResponse


def main() -> int:
    if len(sys.argv) == 4 and sys.argv[1] == "--serve":
        if os.environ.get("WR_PARENT_PID"):
            threading.Thread(target=watch_parent, daemon=True).start()
        # PyInstaller windowed executables have no standard streams.
        log_path = Path(sys.argv[2]) / "server.log"
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
        directory = Path(sys.argv[2])
        directory.mkdir(parents=True, exist_ok=True)
        try:
            from wr.desktop.smoke import smoke_test
            smoke_test(directory)
        except Exception:
            import traceback
            with (directory / "smoke-error.log").open("w", encoding="utf-8") as log:
                traceback.print_exc(file=log)
            return 1
        return 0

    import tkinter as tk
    from tkinter import filedialog, messagebox
    # CI exercises the real launcher lifecycle without starting host applications
    # that can retain a browser profile inside its isolated LOCALAPPDATA directory.
    launch_external = (lambda _target: None) if sys.argv[1:] == ["--verify-launcher"] else open_external

    window = tk.Tk()
    # Keep Tk alive for on-demand native dialogs without mapping a launcher window.
    window.withdraw()
    window.title("Werkelijk Rendement")
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
                    instance = InstanceMetadata.model_validate_json(metadata.read_text())
                    status = control_request(instance.endpoint, instance.token, "status", 1)
                    if status.ready:
                        launch_external(status.url)
                        window.destroy()
                        return 0
                except (OSError, ValueError, KeyError):
                    pass
                time.sleep(0.2)
            raise RuntimeError(t.instance_starting_log(log=directory / "server.log"))

        url = ""
        token = secrets.token_urlsafe(32)
        dashboard_path = secrets.token_urlsafe(24)

        def dispatch(action):
            if action == "status":
                return StatusResponse(ready=ready, url=url, pid=os.getpid())
            response = queue.Queue(maxsize=1)
            events.put((action, response))
            return response.get(timeout=120)

        server = make_control_server(token, dispatch)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        endpoint = f"http://127.0.0.1:{server.server_port}"
        metadata.write_text(InstanceMetadata(endpoint=endpoint, token=token).model_dump_json(), encoding="utf-8")
        environment = {**os.environ, "WR_CONTROL_URL": endpoint, "WR_CONTROL_TOKEN": token,
                       "WR_PARENT_PID": str(os.getpid())}
        environment["WR_DASHBOARD_PATH"] = dashboard_path
        # Do not inherit a repository's Streamlit configuration.
        def open_target(target):
            try:
                launch_external(str(target))
            except OSError as exc:
                messagebox.showerror("Werkelijk Rendement", t.could_not_open(target=target, error=exc), parent=window)

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
            nonlocal ready, language, t
            try:
                saved_language = remembered_language(directory)
                if saved_language != language:
                    language = saved_language
                    t = translator(language)
                if child.poll() is not None:
                    if not ready and attempts < 3:
                        start_child()
                    else:
                        raise RuntimeError(t.dashboard_stopped(log=directory / "server.log"))
                if not ready:
                    try:
                        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
                        with opener.open(url + "/_stcore/health", timeout=0.2) as response:
                            healthy = response.read() == b"ok"
                        if healthy and child.poll() is None:
                            ready = True
                            open_target(url)
                    except OSError:
                        pass
                    if not ready and time.monotonic() > deadline:
                        raise RuntimeError(t.startup_timeout(log=directory / "server.log"))
                while not events.empty():
                    action, response = events.get_nowait()
                    if action == "folder":
                        folder = filedialog.askdirectory(parent=window, title=t(Messages.SELECT_FOLDER), initialdir=selected_folder(directory) or str(Path.home()), mustexist=True)
                        response.put(FolderResponse(folder=folder or None))
                    elif action == "data":
                        open_target(directory)
                        response.put(DataResponse(opened=True))
                    else:
                        response.put(StopResponse(stopping=True))
                        window.after(100, shutdown)
                window.after(200, tick)
            except Exception as exc:
                record_launcher_error(directory)
                messagebox.showerror("Werkelijk Rendement", str(exc), parent=window)
                shutdown()

        start_child()
        window.after(200, tick)
        window.mainloop()
        return 0
    except Exception as exc:
        record_launcher_error(directory)
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


def record_launcher_error(directory: Path) -> None:
    import traceback
    try:
        with (directory / "launcher.log").open("a", encoding="utf-8") as log:
            traceback.print_exc(file=log)
    except OSError:
        pass
