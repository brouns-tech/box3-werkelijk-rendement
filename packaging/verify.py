"""Exercise the actual frozen binary from an unrelated directory without Python in PATH."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from wr.desktop import control_request, free_port


def await_status(directory, process):
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"Launcher exited early: {process.returncode}")
        try:
            instance = json.loads((directory / "instance.json").read_text())
            status = control_request(instance["endpoint"], instance["token"], "status", 1)
            if status["ready"]:
                return instance, status
        except (OSError, ValueError):
            pass
        time.sleep(0.2)
    raise TimeoutError("Frozen launcher did not become ready")


def main():
    executable = Path(sys.argv[1]).resolve()
    with tempfile.TemporaryDirectory(prefix="wr-frozen-") as temporary:
        directory = Path(temporary)
        env = {**os.environ, "LOCALAPPDATA": str(directory), "XDG_DATA_HOME": str(directory),
               "PATH": os.path.join(os.environ.get("SystemRoot", ""), "System32") if os.name == "nt" else ""}
        smoke = subprocess.Popen([str(executable), "--smoke-test", str(directory / "smoke")], cwd=directory, env=env)
        assert smoke.wait(timeout=60) == 0
        assert json.loads((directory / "smoke/smoke-result.json").read_text())["pdf_backend"] == "pypdf"
        assert (directory / "smoke/audit.zip").exists()
        if os.name != "nt":
            # Linux verifies the frozen server without requiring a graphical desktop.
            import urllib.request
            port = free_port()
            child = subprocess.Popen([str(executable), "--serve", str(directory / "smoke/config.toml"), str(port)], cwd=directory, env=env)
            try:
                deadline = time.monotonic() + 60
                while time.monotonic() < deadline:
                    assert child.poll() is None
                    try:
                        with urllib.request.urlopen(f"http://127.0.0.1:{port}/_stcore/health", timeout=1) as response:
                            assert response.read() == b"ok"
                            return
                    except OSError:
                        time.sleep(0.2)
                raise TimeoutError("Frozen server did not become ready")
            finally:
                child.terminate()
                child.wait(timeout=10)
        else:
            from urllib.parse import urlparse
            import socket
            workspace = directory / "WerkelijkRendement"
            launcher = subprocess.Popen([str(executable)], cwd=directory, env=env)
            try:
                instance, status = await_status(workspace, launcher)
                second = subprocess.Popen([str(executable)], cwd=directory, env=env)
                assert second.wait(timeout=60) == 0
                control_request(instance["endpoint"], instance["token"], "stop", 5)
                assert launcher.wait(timeout=15) == 0
                assert (workspace / "config.toml").exists()
                # Abnormal supervisor termination must also stop the server.
                launcher = subprocess.Popen([str(executable)], cwd=directory, env=env)
                _, status = await_status(workspace, launcher)
                launcher.kill()
                launcher.wait(timeout=10)
                port = urlparse(status["url"]).port
                deadline = time.monotonic() + 10
                while time.monotonic() < deadline:
                    with socket.socket() as sock:
                        sock.settimeout(0.5)
                        if sock.connect_ex(("127.0.0.1", port)) != 0:
                            break
                    time.sleep(0.2)
                else:
                    raise AssertionError("Orphaned server after supervisor termination")
            finally:
                if launcher.poll() is None:
                    launcher.kill()
                    launcher.wait(timeout=10)


if __name__ == "__main__":
    main()
