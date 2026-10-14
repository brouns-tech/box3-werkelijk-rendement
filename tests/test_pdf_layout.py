import json
import sqlite3
import subprocess
from pathlib import Path

import pytest

from wr.classify import classify, guess_tax_year
from wr.import_pipeline import run_import, pending_reprocessing
from wr.parsers import parse_document
from wr.pdf import extract_text, extraction_profile


from wr.desktop_smoke import synthetic_column_pdf as column_pdf, REVOLUT, SNS


@pytest.mark.parametrize('fragments,issuer,count', [(REVOLUT, 'revolut', 1), (SNS, 'sns', 2)])
def test_layout_preserves_holders_and_columns_without_external_programs(tmp_path, monkeypatch, fragments, issuer, count):
    source = tmp_path / 'statement.pdf'
    column_pdf(source, fragments)
    monkeypatch.setattr(subprocess, 'run', lambda *a, **kw: pytest.fail('Extraction must not run an external tool'))
    text, pages = extract_text(source)
    detected = classify(text)
    assert pages == 1 and detected.issuer == issuer
    result = parse_document(issuer, detected.doc_type, text, guess_tax_year(text, detected.doc_type))
    assert len(result.facts) == count
    assert all(f.holder_names for f in result.facts)
    assert 'Last Email' not in {name for f in result.facts for name in f.holder_names}
    if issuer == 'revolut':
        fact = result.facts[0]
        assert fact.holder_names == ['Alex Example']
        assert (fact.start_balance, fact.end_balance, fact.interest_received) == (1000, 1012.34, 12.34)
    else:
        assert result.facts[0].holder_names == ['A. Example', 'B. Example']
        assert result.facts[1].holder_names == ['C. Example']
        assert result.facts[1].start_balance == 100


def test_reprocess_replaces_old_facts_and_becomes_a_duplicate_again(tmp_path):
    folder = tmp_path / 'documents'
    folder.mkdir()
    column_pdf(folder / 'statement.pdf', REVOLUT)
    database = tmp_path / 'data.sqlite'
    assert run_import(folder, database).parsed == 1
    with sqlite3.connect(database) as conn:
        conn.execute("UPDATE documents SET processing_profile = NULL")
        conn.execute("UPDATE account_year_facts SET holder_names = '[\"Last Email\"]'")
        conn.execute("INSERT INTO tax_returns(document_sha256,tax_year,filer_name) SELECT content_sha256,2024,'Obsolete' FROM documents")
        conn.execute("INSERT INTO account_year_facts(document_sha256,tax_year,issuer,account_key,holder_names) SELECT content_sha256,2023,'revolut','obsolete','[\"Last Email\"]' FROM documents")
        assert pending_reprocessing(conn) == 1
    report = run_import(folder, database)
    assert report.parsed == 1 and report.new == 0 and report.duplicate == 0
    with sqlite3.connect(database) as conn:
        assert pending_reprocessing(conn) == 0
        assert conn.execute('SELECT COUNT(*) FROM account_year_facts').fetchone()[0] == 1
        assert conn.execute('SELECT COUNT(*) FROM tax_returns').fetchone()[0] == 0
        assert json.loads(conn.execute('SELECT holder_names FROM account_year_facts').fetchone()[0]) == ['Alex Example']
        assert conn.execute('SELECT processing_profile FROM documents').fetchone()[0] == extraction_profile()
    assert run_import(folder, database).duplicate == 1


def test_failed_reprocess_removes_stale_data_and_rolls_back_partial_writes(tmp_path, monkeypatch):
    from wr import import_pipeline
    folder = tmp_path / 'documents'
    folder.mkdir()
    column_pdf(folder / 'statement.pdf', REVOLUT)
    database = tmp_path / 'data.sqlite'
    run_import(folder, database)
    with sqlite3.connect(database) as conn:
        conn.execute("UPDATE documents SET processing_profile = 'old'")
    persist = import_pipeline._persist_parse

    def fail(conn, *args):
        persist(conn, *args)
        raise RuntimeError('synthetic persistence failure')

    monkeypatch.setattr(import_pipeline, '_persist_parse', fail)
    assert run_import(folder, database).failed == 1
    with sqlite3.connect(database) as conn:
        assert conn.execute('SELECT COUNT(*) FROM account_year_facts').fetchone()[0] == 0
        assert conn.execute('SELECT parse_status FROM documents').fetchone()[0] == 'failed'
    monkeypatch.setattr(import_pipeline, '_persist_parse', persist)
    assert run_import(folder, database).parsed == 1


def test_tests_cannot_open_the_real_workspace_database():
    with pytest.raises(AssertionError, match='temporary directory'):
        sqlite3.connect(Path.home() / 'financial-workspace' / 'wr.sqlite')


def test_label_numbers_do_not_consume_page_footer_digits():
    from wr.parsers.common import amount_after_label
    assert amount_after_label('Door u ontvangen rente in 2024 12,34\n2\nPage footer', 'Door u ontvangen rente in 2024') == 12.34


def test_missing_taxable_base_does_not_read_next_heading_number():
    result = parse_document('belastingdienst', 'aangifte_ib', 'Naam Alex Example\nGrondslag sparen en beleggen\n3\nOther heading', 2024)
    assert result.tax_return.grondslag is None


def test_revolut_column_stream_cannot_be_misread_as_last_email():
    from wr.parsers.revolut import _holders
    assert _holders('First Name\nLast Name\nEmail\nAlex\nExample') == []


def test_overview_requires_reprocessing_legacy_records(tmp_path, monkeypatch):
    import sys
    from streamlit.testing.v1 import AppTest
    from wr.desktop_storage import prepare_workspace, remember_folder, remember_language
    from wr.config import load_settings
    workspace = prepare_workspace(tmp_path)
    remember_language(tmp_path, 'en')
    folder = tmp_path / 'documents'
    folder.mkdir()
    remember_folder(tmp_path, str(folder))
    column_pdf(folder / 'statement.pdf', REVOLUT)
    db = load_settings(tmp_path).resolved_db_path
    run_import(folder, db)
    with sqlite3.connect(db) as conn:
        conn.execute('UPDATE documents SET processing_profile = NULL')
    monkeypatch.setattr(sys, 'argv', ['app.py', '--workspace', str(workspace)])
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / 'dashboard/app.py')).run()
    assert not app.exception
    assert any('Scan your document folder again' in warning.value for warning in app.warning)
    assert not app.metric
    run_import(folder, db)
    app.run()
    assert not app.exception
    assert app.metric
    assert not any('Scan your document folder again' in warning.value for warning in app.warning)
