"""One-time import of retired TOML settings into UI-owned workspace settings."""
from __future__ import annotations

from pathlib import Path
from typing import Any


def read_legacy_settings(path: Path) -> dict[str, Any]:
    try:
        import tomllib
    except ModuleNotFoundError:  # Python 3.10, only during migration
        import tomli as tomllib

    with path.open("rb") as source:
        return tomllib.load(source)
