from __future__ import annotations

from pathlib import Path
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib  # type: ignore


def load_config(path: str | Path | None = None) -> dict[str, Any]:
    if path is None:
        candidates = [Path.cwd() / "config.toml"]
    else:
        candidates = [Path(path)]

    for candidate in candidates:
        if candidate.is_file():
            with candidate.open("rb") as f:
                cfg = tomllib.load(f)
            cfg["_config_path"] = str(candidate.resolve())
            cfg["_project_root"] = str(candidate.resolve().parent)
            return cfg

    if path is not None:
        raise FileNotFoundError(f"Config file not found: {Path(path)}")

    return {
        "_config_path": None,
        "_project_root": str(Path.cwd().resolve()),
    }


def resolve_db_path(cfg: dict[str, Any]) -> Path:
    db = Path(cfg.get("db_path", "data/wr.sqlite"))
    if not db.is_absolute():
        db = Path(cfg["_project_root"]) / db
    return db
