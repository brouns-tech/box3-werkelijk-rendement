import hashlib
import importlib.util
import io
import os
import subprocess
from pathlib import Path

import pytest

from wr import desktop_platform


def packaging_module():
    file = Path(__file__).resolve().parents[1] / "packaging/package_linux.py"
    spec = importlib.util.spec_from_file_location("linux_packager", file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_external_opener_restores_host_libraries_without_mutating_application(monkeypatch):
    monkeypatch.setattr(desktop_platform.sys, "platform", "linux")
    monkeypatch.setattr(desktop_platform.sys, "frozen", True, raising=False)
    monkeypatch.setenv("LD_LIBRARY_PATH", "/bundle/private")
    monkeypatch.setenv("LD_LIBRARY_PATH_ORIG", "/host/original")
    monkeypatch.setenv("PYTHONPATH", "/bundle/python")
    monkeypatch.setattr(desktop_platform.shutil, "which", lambda _: "/usr/bin/xdg-open")
    calls = []
    monkeypatch.setattr(desktop_platform.subprocess, "Popen", lambda args, **kwargs: calls.append((args, kwargs)))
    desktop_platform.open_external("/selected folder/évidence")
    args, options = calls[0]
    assert args == ["/usr/bin/xdg-open", "/selected folder/évidence"]
    assert options["env"]["LD_LIBRARY_PATH"] == "/host/original"
    assert "PYTHONPATH" not in options["env"]
    assert os.environ["LD_LIBRARY_PATH"] == "/bundle/private"
    monkeypatch.delenv("LD_LIBRARY_PATH_ORIG")
    assert "LD_LIBRARY_PATH" not in desktop_platform.host_environment()


def test_missing_host_opener_is_actionable(monkeypatch):
    monkeypatch.setattr(desktop_platform.sys, "platform", "linux")
    monkeypatch.setattr(desktop_platform.shutil, "which", lambda _: None)
    with pytest.raises(FileNotFoundError, match="xdg-utils"):
        desktop_platform.open_external("http://127.0.0.1:1234")


def test_download_refuses_unverified_tool_and_removes_partial_file(tmp_path, monkeypatch):
    module = packaging_module()
    content = b"synthetic build tool"
    monkeypatch.setattr(module.urllib.request, "urlopen", lambda *args, **kwargs: io.BytesIO(content))
    spec = {"url": "https://example.invalid/tool", "sha256": "0" * 64}
    path = tmp_path / "tool.AppImage"
    with pytest.raises(ValueError, match="Checksum mismatch"):
        module.checked_download(spec, path)
    assert not path.exists() and not path.with_suffix(".download").exists()
    spec["sha256"] = hashlib.sha256(content).hexdigest()
    assert module.checked_download(spec, path).read_bytes() == content
    monkeypatch.setattr(module.urllib.request, "urlopen", lambda *args, **kwargs: pytest.fail("Verified cache should be reused"))
    assert module.checked_download(spec, path) == path


@pytest.mark.skipif(os.name == "nt", reason="AppDir staging is Linux-only")
def test_staged_appdir_preserves_bundle_and_has_relocatable_launch_metadata(tmp_path):
    module = packaging_module()
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    (bundle / "WerkelijkRendement").write_text("synthetic executable")
    (bundle / "_internal").mkdir()
    (bundle / "_internal/resource").write_text("synthetic resource")
    appdir = module.stage_appdir(bundle, tmp_path / "space and é.AppDir")
    assert (appdir / "usr/bin/WerkelijkRendement").read_text() == "synthetic executable"
    assert (appdir / "usr/bin/WerkelijkRendement").is_symlink()
    assert (appdir / "AppRun").stat().st_mode & 0o111
    assert '"$@"' in (appdir / "AppRun").read_text()
    assert (appdir / "README.md").is_file()
    assert "Terminal=false" in (appdir / "tech.brouns.WerkelijkRendement.desktop").read_text()
    executable = appdir / "usr/bin/WerkelijkRendement"
    executable.write_text('#!/bin/sh\nprintf "%s\\n" "$@"\n')
    executable.chmod(0o755)
    arguments = ["space and é", "literal $(not-a-command)"]
    result = subprocess.run([str(appdir / "AppRun"), *arguments], env={"PATH": ""},
                            capture_output=True, text=True, check=True)
    assert result.stdout.splitlines() == arguments
    with pytest.raises(FileExistsError):
        module.stage_appdir(bundle, appdir)


def test_release_packager_rejects_known_static_tk_bundle_before_download(tmp_path, monkeypatch):
    module = packaging_module()
    monkeypatch.setattr(module.platform, "system", lambda: "Linux")
    monkeypatch.setattr(module.platform, "machine", lambda: "x86_64")
    monkeypatch.setattr(module, "checked_download", lambda *args: pytest.fail("No downloads for an unsuitable bundle"))
    with pytest.raises(RuntimeError, match="dynamic Tk extension"):
        module.build(tmp_path)
