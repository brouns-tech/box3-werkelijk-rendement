"""Exercise the actual frozen binary from an unrelated directory without Python in PATH."""
from __future__ import annotations

import json
import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
from contextlib import contextmanager
from pathlib import Path

from wr.desktop import control_request, free_port
from wr.desktop_models import InstanceMetadata


def await_status(directory, process):
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"Launcher exited early: {process.returncode}")
        try:
            instance = InstanceMetadata.model_validate_json((directory / "instance.json").read_text())
            status = control_request(instance.endpoint, instance.token, "status", 1)
            if status.ready:
                return instance, status
        except (OSError, ValueError):
            pass
        time.sleep(0.2)
    raise TimeoutError("Frozen launcher did not become ready")


def capture_verification_failure(directory: Path, diagnostics: Path) -> None:
    diagnostics.mkdir(parents=True, exist_ok=True)
    failure = traceback.format_exc()
    details = [failure]
    (diagnostics / "verification.log").write_text(failure, encoding="utf-8")
    for log in directory.rglob("*.log"):
        if log.name not in {"server.log", "launcher.log", "smoke-error.log"}:
            continue
        destination = diagnostics / log.relative_to(directory)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(log, destination)
        content = log.read_text(encoding="utf-8")[-16000:]
        details.append(f"{log.relative_to(directory)}:\n{content}")
        print(f"Diagnostic {log.relative_to(directory)}:\n{content}", flush=True)
    print(f"Verification diagnostics saved to {diagnostics.resolve()}", flush=True)
    if os.environ.get("GITHUB_ACTIONS") == "true":
        # This workspace is entirely synthetic; expose the trace in public
        # check annotations as well as authenticated job logs/artifacts.
        message = "\n".join(details)[-12000:].replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
        print(f"::error title=Frozen verification failed::{message}", flush=True)


@contextmanager
def verification_workspace(diagnostics: Path):
    workspace = tempfile.TemporaryDirectory(prefix="wr-frozen-")
    directory = Path(workspace.name)
    captured = None
    try:
        with workspace:
            try:
                yield directory
            except Exception as exc:
                capture_verification_failure(directory, diagnostics)
                captured = exc
                raise
    except Exception as exc:
        if exc is not captured:
            capture_verification_failure(directory, diagnostics)
        raise


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("executable", type=Path)
    parser.add_argument("--desktop", action="store_true")
    parser.add_argument("--diagnostics", type=Path, default=Path("build/verification-logs"))
    args = parser.parse_args()
    executable = args.executable.resolve()
    with verification_workspace(args.diagnostics) as directory:
        env = {**os.environ, "LOCALAPPDATA": str(directory), "XDG_DATA_HOME": str(directory),
               "PATH": os.path.join(os.environ.get("SystemRoot", ""), "System32") if os.name == "nt" else ""}
        if executable.suffix == ".AppImage":
            env["APPIMAGE_EXTRACT_AND_RUN"] = "1"
        if os.name != "nt" and args.desktop:
            # A stand-in for the host opener avoids opening browsers during GUI tests.
            host_bin = directory / "host-bin"
            host_bin.mkdir()
            opener = host_bin / "xdg-open"
            opener.write_text("#!/bin/sh\nexit 0\n")
            opener.chmod(0o755)
            env["PATH"] = str(host_bin)
        print("Verifying frozen PDF import and audit export", flush=True)
        smoke = subprocess.Popen([str(executable), "--smoke-test", str(directory / "smoke")], cwd=directory, env=env)
        try:
            result = smoke.wait(timeout=60)
            if result != 0:
                raise RuntimeError(f"Frozen PDF/import smoke test exited with code {result}")
        finally:
            if smoke.poll() is None:
                smoke.kill()
                smoke.wait(timeout=10)
        assert json.loads((directory / "smoke/smoke-result.json").read_text())["pdf_backend"] == "pdfium"
        assert (directory / "smoke/audit.zip").exists()
        if os.name != "nt" and not args.desktop:
            # Linux verifies the frozen server without requiring a graphical desktop.
            import urllib.request
            port = free_port()
            child = subprocess.Popen([str(executable), "--serve", str(directory / "smoke"), str(port)], cwd=directory, env=env)
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
            print("Verifying native launcher startup", flush=True)
            launcher_command = [str(executable), "--verify-launcher"]
            launcher = subprocess.Popen(launcher_command, cwd=directory, env=env)
            try:
                instance, status = await_status(workspace, launcher)
                print("Verifying second-instance reuse", flush=True)
                second = subprocess.Popen(launcher_command, cwd=directory, env=env)
                try:
                    assert second.wait(timeout=60) == 0
                finally:
                    if second.poll() is None:
                        second.kill()
                        second.wait(timeout=10)
                print("Verifying clean shutdown", flush=True)
                control_request(instance.endpoint, instance.token, "stop", 5)
                assert launcher.wait(timeout=15) == 0
                assert (workspace / ".wr-settings.json").exists()
                # Abnormal supervisor termination must also stop the server.
                launcher = subprocess.Popen(launcher_command, cwd=directory, env=env)
                print("Verifying server cleanup after supervisor termination", flush=True)
                _, status = await_status(workspace, launcher)
                if os.name == "nt":
                    launcher.kill()
                else:
                    # AppImage extraction can introduce a runtime wrapper process.
                    os.kill(status.pid, 9)
                launcher.wait(timeout=10)
                port = urlparse(status.url).port
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
