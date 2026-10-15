"""One-time import of retired TOML settings into UI-owned workspace settings."""
from __future__ import annotations

from pathlib import Path
from pydantic import JsonValue, TypeAdapter


def read_legacy_settings(path: Path) -> dict[str, JsonValue]:
    try:
        import tomllib
    except ModuleNotFoundError:  # Python 3.10, only during migration
        import tomli as tomllib

    with path.open("rb") as source:
        return TypeAdapter(dict[str, JsonValue]).validate_python(tomllib.load(source))
