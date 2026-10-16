"""Writable desktop state, deliberately independent of CLI workspace defaults."""
from __future__ import annotations

from importlib.metadata import version
from pathlib import Path
import os
import sys
import tempfile

from wr.config import (
    APP_DATA_DIRECTORY,
    DEFAULT_DESKTOP_DATABASE,
    DISTRIBUTION_NAME,
    LANGUAGE_FILENAME,
    LEGACY_PREFERENCES_FILENAME,
    SETTINGS_FILENAME,
)
from wr.models.desktop import LanguagePreference, LegacyPreferences


def app_data_dir() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ["LOCALAPPDATA"])
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share"))
    return base / APP_DATA_DIRECTORY


def prepare_workspace(directory: Path | None = None) -> Path:
    from dataclasses import replace
    from wr.workspace.settings import load_settings, save_settings

    directory = (directory or app_data_dir()).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    settings_path = directory / SETTINGS_FILENAME
    existing = settings_path.exists()
    settings = load_settings(directory)
    if not existing:
        settings = replace(settings, db_path=DEFAULT_DESKTOP_DATABASE)
        # Retired beta preferences migrate once; reset must not resurrect them.
        try:
            preferences = LegacyPreferences.model_validate_json((directory / LEGACY_PREFERENCES_FILENAME).read_text(encoding="utf-8"))
            folder = preferences.selected_folder
        except (OSError, ValueError):
            folder = None
        save_settings(settings, import_root=folder if isinstance(folder, str) else None)
    return directory


def selected_folder(directory: Path) -> str | None:
    from wr.workspace.settings import load_settings
    folder = load_settings(directory).import_root
    return str(folder) if folder else None


def remember_folder(directory: Path, folder: str) -> None:
    path = Path(folder).resolve(strict=True)
    if not path.is_dir():
        raise ValueError("Select an existing folder")
    from wr.workspace.settings import load_settings, save_settings
    save_settings(load_settings(directory), import_root=str(path))


def app_version() -> str:
    return version(DISTRIBUTION_NAME)


def remembered_language(directory: Path, default: str = "nl") -> str:
    try:
        return LanguagePreference.model_validate_json((directory / LANGUAGE_FILENAME).read_text(encoding="utf-8")).language
    except (OSError, ValueError):
        return default


def remember_language(directory: Path, language: str) -> None:
    if language not in {"nl", "en"}:
        raise ValueError(f"Unsupported language: {language}")
    directory.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=directory,
                                         prefix=f"{Path(LANGUAGE_FILENAME).stem}-", suffix=".tmp", delete=False) as file:
            temporary = Path(file.name)
            file.write(LanguagePreference(language=language).model_dump_json())
        temporary.replace(directory / LANGUAGE_FILENAME)
    finally:
        if temporary:
            temporary.unlink(missing_ok=True)
