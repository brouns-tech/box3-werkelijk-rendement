"""Validate the exact desktop downloads before allowing release publication."""
from __future__ import annotations

import argparse
import hashlib
import re
import shutil
from pathlib import Path


def release_metadata(version: str, tag: str | None = None) -> dict[str, str]:
    match = re.fullmatch(r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)((?:a|b|rc)\d+|\.dev\d+)?", version)
    if match is None:
        raise ValueError("Release version must be X.Y.Z, optionally followed by aN, bN, rcN, or .devN")
    expected = f"v{version}"
    if tag is not None and tag != expected:
        raise ValueError(f"Tag must match pyproject.toml version: expected {expected}")
    return {
        "version": version,
        "tag": expected,
        "prerelease": str(match[1] == "0" or bool(match[4])).lower(),
    }


def prepare_release(version: str, artifacts: Path, notes: Path, output: Path) -> list[Path]:
    release_metadata(version)
    prefix = f"WerkelijkRendement-{version}"
    names = [f"{prefix}-windows-x64.zip", f"{prefix}-linux-x86_64.AppImage", f"{prefix}-linux-x86_64.tar.gz"]
    files = []
    # Check the entire payload before writing any files to the publication folder.
    for name in names:
        asset = artifacts / name
        checksum = artifacts / f"{name}.sha256"
        if not asset.is_file() or asset.is_symlink() or asset.stat().st_size == 0:
            raise ValueError(f"Missing, empty, or symlinked release asset: {name}")
        if not checksum.is_file() or checksum.is_symlink():
            raise ValueError(f"Missing checksum: {checksum.name}")
        line = checksum.read_text(encoding="ascii").strip()
        match = re.fullmatch(r"([a-fA-F0-9]{64})[ \t]+\*?" + re.escape(name), line)
        if match is None:
            raise ValueError(f"Invalid checksum or filename: {checksum.name}")
        digest = hashlib.sha256()
        with asset.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
        if digest.hexdigest() != match[1].lower():
            raise ValueError(f"Checksum mismatch: {name}")
        files.extend([asset, checksum])
    if not notes.is_file() or not notes.read_text(encoding="utf-8").strip():
        raise ValueError(f"Missing or empty release notes: {notes}")
    if output.exists():
        raise ValueError("Release output directory already exists; use a fresh directory")
    output.mkdir(parents=True)
    for file in files:
        shutil.copy2(file, output / file.name)
    shutil.copy2(notes, output / "RELEASE-NOTES.md")
    return [output / file.name for file in files] + [output / "RELEASE-NOTES.md"]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True)
    parser.add_argument("--artifacts", type=Path, required=True)
    parser.add_argument("--notes", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    for file in prepare_release(args.version, args.artifacts, args.notes, args.output):
        print(file)
