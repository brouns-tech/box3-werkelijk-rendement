"""Package the shared frozen bundle as a portable tarball and an AppImage."""
from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
import subprocess
import tarfile
import urllib.request
from importlib.metadata import version
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def checked_download(spec: dict, destination: Path) -> Path:
    if destination.is_file() and hashlib.sha256(destination.read_bytes()).hexdigest() == spec["sha256"]:
        return destination
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(".download")
    request = urllib.request.Request(spec["url"], headers={"Accept": "application/octet-stream", "User-Agent": "WerkelijkRendement-build"})
    try:
        with urllib.request.urlopen(request, timeout=60) as response, temporary.open("wb") as output:
            shutil.copyfileobj(response, output)
        if hashlib.sha256(temporary.read_bytes()).hexdigest() != spec["sha256"]:
            raise ValueError(f"Checksum mismatch for {destination.name}; no downloaded code was executed")
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)
    return destination


def stage_appdir(bundle: Path, destination: Path) -> Path:
    if not (bundle / "WerkelijkRendement").is_file():
        raise FileNotFoundError("Build packaging/desktop.spec with PyInstaller first")
    if destination.exists():
        raise FileExistsError(f"Remove the previous staging directory before rebuilding: {destination}")
    library = destination / "usr/lib/werkelijk-rendement"
    shutil.copytree(bundle, library)
    binary = destination / "usr/bin"
    binary.mkdir(parents=True)
    (binary / "WerkelijkRendement").symlink_to("../lib/werkelijk-rendement/WerkelijkRendement")
    for filename in ("AppRun", "tech.brouns.WerkelijkRendement.desktop", "tech.brouns.WerkelijkRendement.svg"):
        shutil.copy2(ROOT / "packaging/linux" / filename, destination / filename)
    (destination / "AppRun").chmod(0o755)
    shutil.copytree(ROOT / "docs", destination / "docs")
    guide = (ROOT / "docs/getting-started/linux.md").read_text(encoding="utf-8")
    (destination / "README.md").write_text(
        guide.replace("(../development/", "(docs/development/"), encoding="utf-8"
    )
    shutil.copy2(ROOT / "packaging/requirements.lock", destination / "dependencies.lock")
    notices = destination / "usr/share/doc/werkelijk-rendement"
    notices.mkdir(parents=True)
    shutil.copy2(ROOT / "packaging/linux/RUNTIME-LICENSE.txt", notices / "AppImage-runtime-LICENSE.txt")
    shutil.copy2(ROOT / "packaging/linux/tools.lock.json", notices / "AppImage-tools.lock.json")
    return destination


def build(output: Path | None = None) -> tuple[Path, Path]:
    if platform.system() != "Linux" or platform.machine() != "x86_64":
        raise RuntimeError("This release target requires Linux x86_64")
    output = output or ROOT / "dist"
    if not any((output / "WerkelijkRendement/_internal").rglob("_tkinter*.so")):
        raise RuntimeError("The Linux bundle lacks a dynamic Tk extension. Rebuild with the release CPython interpreter.")
    app_version = version("box3-werkelijk-rendement")
    tag = os.environ.get("GITHUB_REF_TYPE")
    if tag == "tag" and os.environ.get("GITHUB_REF_NAME") != f"v{app_version}":
        raise ValueError("Tag must match pyproject.toml version")
    lock = json.loads((ROOT / "packaging/linux/tools.lock.json").read_text())
    cache = ROOT / "build/appimage-tools"
    tool = checked_download(lock["appimagetool"], cache / "appimagetool.AppImage")
    runtime = checked_download(lock["runtime"], cache / "runtime-x86_64")
    source = checked_download(lock["runtime_source"], cache / "runtime-source.tar.gz")
    tool.chmod(0o755)
    appdir = stage_appdir(output / "WerkelijkRendement", output / "WerkelijkRendement.AppDir")
    notices = appdir / "usr/share/doc/werkelijk-rendement"
    shutil.copy2(source, notices / "AppImage-runtime-source.tar.gz")
    image = output / f"WerkelijkRendement-{app_version}-linux-x86_64.AppImage"
    # An explicit runtime avoids appimagetool fetching a mutable latest runtime.
    environment = {**os.environ, "ARCH": "x86_64", "SOURCE_DATE_EPOCH": os.environ.get("SOURCE_DATE_EPOCH", "0")}
    subprocess.run([str(tool), "--appimage-extract-and-run", "--no-appstream", "--runtime-file", str(runtime),
                    "--comp", "zstd", "--mksquashfs-opt", "-processors", "--mksquashfs-opt", "2",
                    str(appdir), str(image)], env=environment, check=True)
    image.chmod(0o755)
    archive = output / f"WerkelijkRendement-{app_version}-linux-x86_64.tar.gz"
    with tarfile.open(archive, "w:gz") as file:
        file.add(appdir, arcname="WerkelijkRendement")
    for artifact in (image, archive):
        digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
        artifact.with_name(artifact.name + ".sha256").write_text(f"{digest}  {artifact.name}\n", encoding="ascii")
    return image, archive


if __name__ == "__main__":
    for artifact in build():
        print(artifact)
