"""Writable desktop state, deliberately independent of CLI workspace defaults."""
from __future__ import annotations

import json
import os
import sys
import tempfile
from importlib.metadata import version
from pathlib import Path


def app_data_dir() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ["LOCALAPPDATA"])
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share"))
    return base / "WerkelijkRendement"


def prepare_workspace(directory: Path | None = None) -> Path:
    directory = directory or app_data_dir()
    directory.mkdir(parents=True, exist_ok=True)
    config = directory / "config.toml"
    if not config.exists():
        config.write_text('db_path = "wr.sqlite"\n', encoding="utf-8")
    return config


def selected_folder(directory: Path) -> str | None:
    try:
        value = json.loads((directory / "preferences.json").read_text(encoding="utf-8"))
        return value.get("selected_folder")
    except (OSError, ValueError):
        return None


def remember_folder(directory: Path, folder: str) -> None:
    path = Path(folder).resolve(strict=True)
    if not path.is_dir():
        raise ValueError("Select an existing folder")
    temporary = directory / "preferences.tmp"
    temporary.write_text(json.dumps({"selected_folder": str(path)}), encoding="utf-8")
    temporary.replace(directory / "preferences.json")


def app_version() -> str:
    return version("box3-werkelijk-rendement")


def remembered_language(directory: Path, default: str = "nl") -> str:
    try:
        value = json.loads((directory / "language.json").read_text(encoding="utf-8"))
        language = value.get("language") if isinstance(value, dict) else None
        return language if isinstance(language, str) and language in {"nl", "en"} else default
    except (OSError, ValueError):
        return default


def remember_language(directory: Path, language: str) -> None:
    if language not in {"nl", "en"}:
        raise ValueError(f"Unsupported language: {language}")
    directory.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=directory,
                                         prefix="language-", suffix=".tmp", delete=False) as file:
            temporary = Path(file.name)
            json.dump({"language": language}, file)
        temporary.replace(directory / "language.json")
    finally:
        if temporary:
            temporary.unlink(missing_ok=True)
