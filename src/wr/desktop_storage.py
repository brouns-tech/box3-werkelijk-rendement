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
    from dataclasses import replace
    from wr.config import load_settings, save_settings

    directory = (directory or app_data_dir()).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    settings_path = directory / ".wr-settings.json"
    existing = settings_path.exists()
    fresh = not existing and not (directory / "config.toml").exists()
    settings = load_settings(directory)
    if fresh:
        settings = replace(settings, db_path=Path("wr.sqlite"))
    if not existing:
        # Retired beta preferences migrate once; reset must not resurrect them.
        try:
            raw = json.loads((directory / "preferences.json").read_text(encoding="utf-8"))
            folder = raw.get("selected_folder") if isinstance(raw, dict) else None
        except (OSError, ValueError):
            folder = None
        save_settings(settings, import_root=folder if isinstance(folder, str) else None)
    return directory


def selected_folder(directory: Path) -> str | None:
    from wr.config import load_settings
    folder = load_settings(directory).import_root
    return str(folder) if folder else None


def remember_folder(directory: Path, folder: str) -> None:
    path = Path(folder).resolve(strict=True)
    if not path.is_dir():
        raise ValueError("Select an existing folder")
    from wr.config import load_settings, save_settings
    save_settings(load_settings(directory), import_root=str(path))


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
