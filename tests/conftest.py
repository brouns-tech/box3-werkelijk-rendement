"""Tests must never read or write a maintainer's financial workspace."""
from pathlib import Path
import sqlite3
import tempfile
from urllib.parse import unquote, urlparse

import pytest


@pytest.fixture(autouse=True)
def isolate_sqlite_connections(monkeypatch, tmp_path):
    # Missing --workspace arguments must default to a temporary workspace too.
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "app-data"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "app-data"))
    connect = sqlite3.connect
    temporary = Path(tempfile.gettempdir()).resolve()

    def guarded(database, *args, **kwargs):
        name = str(database)
        if name == ":memory:" or (name.startswith("file:") and ("mode=memory" in name or ":memory:" in name)):
            return connect(database, *args, **kwargs)
        if name.startswith("file:"):
            name = unquote(urlparse(name).path)
            # Windows file URIs use /C:/..., while Path expects C:/....
            if len(name) > 2 and name[0] == "/" and name[2] == ":":
                name = name[1:]
        path = Path(name).resolve()
        if not path.is_relative_to(temporary):
            raise AssertionError("Tests may open SQLite files only inside the system temporary directory")
        return connect(database, *args, **kwargs)

    monkeypatch.setattr(sqlite3, "connect", guarded)
