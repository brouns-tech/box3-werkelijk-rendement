import json
from pathlib import Path
import sqlite3
from zipfile import ZipFile

import pytest

from wr.desktop.selfcheck import run_selfcheck
from wr.workspace.settings import load_settings


def test_selfcheck_is_repeatable_and_creates_release_verification_artifacts(tmp_path):
    run_selfcheck(tmp_path)
    run_selfcheck(tmp_path)
    result = json.loads((tmp_path / "smoke-result.json").read_text())
    assert result["pdf_backend"] == "pdfium"
    assert Path(result["config"]) == tmp_path
    with ZipFile(tmp_path / "audit.zip") as bundle:
        assert bundle.testzip() is None
        assert {"manifest.json", "source_facts.csv", "yearly_summary.csv"} <= set(bundle.namelist())
    with sqlite3.connect(load_settings(tmp_path).resolved_db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM documents").fetchone() == (1,)


def test_selfcheck_removes_stale_success_when_extraction_fails(tmp_path, monkeypatch):
    run_selfcheck(tmp_path)
    monkeypatch.setattr("wr.documents.extraction.extract_text", lambda source: ("", 0))
    with pytest.raises(RuntimeError, match="PDFium could not extract"):
        run_selfcheck(tmp_path)
    assert not (tmp_path / "smoke-result.json").exists()


def test_selfcheck_rejects_an_incorrect_calculation(tmp_path, monkeypatch):
    from wr.calculations import service

    recompute = service.recompute

    def incorrect_calculation(database):
        recompute(database)
        with sqlite3.connect(database) as conn:
            conn.execute("UPDATE yearly_portfolio SET known_combined_actual_return=999")

    monkeypatch.setattr(service, "recompute", incorrect_calculation)
    with pytest.raises(RuntimeError, match="portfolio calculation"):
        run_selfcheck(tmp_path)
    assert not (tmp_path / "smoke-result.json").exists()


def test_selfcheck_rejects_an_incomplete_audit_export(tmp_path, monkeypatch):
    def incomplete_export(database, destination):
        with ZipFile(destination, "w") as bundle:
            bundle.writestr("manifest.json", "{}")
        return destination

    monkeypatch.setattr("wr.export.write_audit_export", incomplete_export)
    with pytest.raises(RuntimeError, match="audit export is incomplete"):
        run_selfcheck(tmp_path)
    assert not (tmp_path / "smoke-result.json").exists()
