from __future__ import annotations

from pathlib import Path


def scan_pdfs(root: Path, limit: int | None = None) -> list[Path]:
    paths = sorted(path for path in root.rglob("*") if path.is_file() and path.suffix.lower() == ".pdf")
    return paths if limit is None else paths[:limit]
