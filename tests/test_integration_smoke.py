from dataclasses import asdict
import sqlite3

import pytest

from tests.support.pdf import SAMPLES, synthetic_pdf
from wr.calculations.service import recompute
from wr.desktop.storage import prepare_workspace, remember_language, remembered_language
from wr.documents.extraction import extract_text
from wr.export import write_audit_export
from wr.i18n import currency, translator
from wr.importing.classification import classify, guess_tax_year
from wr.importing.pipeline import run_import
from wr.messages import Messages
from wr.parsers import PLUGINS, parse_document
from wr.workspace.settings import load_settings


@pytest.mark.parametrize("issuer,sample", SAMPLES.items())
def test_supported_institution_pdf_round_trips_through_native_extraction(tmp_path, issuer, sample):
    source = tmp_path / "arbitrary-name.PDF"
    synthetic_pdf(source, sample)
    text, pages = extract_text(source)
    identified = classify(text)
    assert pages == 1
    assert identified is not None and identified.issuer == issuer
    year = guess_tax_year(sample, identified.doc_type)
    original = parse_document(issuer, identified.doc_type, sample, year)
    decoded = parse_document(issuer, identified.doc_type, text, year)
    assert original.facts or original.tax_return
    assert asdict(decoded) == asdict(original)


def test_all_institutions_import_recompute_and_export_together(tmp_path):
    config = prepare_workspace(tmp_path)
    documents = tmp_path / "documents"
    documents.mkdir()
    for issuer, sample in SAMPLES.items():
        synthetic_pdf(documents / f"synthetic-{issuer}.PDF", sample)
    assert {plugin.issuer for plugin in PLUGINS} == set(SAMPLES)
    database = load_settings(config).resolved_db_path
    report = run_import(documents, database)
    assert report.parsed == len(SAMPLES)
    assert not report.failed
    recompute(database)
    with sqlite3.connect(database) as conn:
        assert conn.execute("SELECT interest_received FROM account_year_facts WHERE issuer='ing'").fetchone() == (12.34,)
        assert conn.execute("SELECT grondslag FROM tax_returns").fetchone() == (160000,)
        assert conn.execute("SELECT COUNT(*) FROM taxpayer_tax_results WHERE tax_year=2024").fetchone() == (2,)
    assert write_audit_export(database, tmp_path / "audit.zip").is_file()
    assert run_import(documents, database).duplicate == len(SAMPLES)


@pytest.mark.parametrize("language,label,formatted", [
    ("nl", "Map selecteren", "€ 1.234,56"),
    ("en", "Select folder", "€ 1,234.56"),
])
def test_language_preferences_and_currency_formatting(tmp_path, language, label, formatted):
    prepare_workspace(tmp_path)
    remember_language(tmp_path, language)
    assert remembered_language(tmp_path) == language
    assert translator(language)(Messages.SELECT_FOLDER) == label
    assert currency(1234.56, language) == formatted
