import json
import sqlite3

import pytest
from pydantic import ValidationError

from wr.calculations.coverage import coverage_for_year
from tests.support.pdf import SAMPLES
from wr.export import _asset_and_fact_rows
from wr.importing.classification import classify
from wr.models import AccountYearFact, ParseResult
from wr.models.metadata import FactMetadata
from wr.models.storage import FactRecord
from wr.parsers import parse_document
from wr.storage.adapters import fact_from_row
from wr.storage.documents import upsert_document
from wr.storage.facts import insert_facts
from wr.storage.migrations import init_db


@pytest.mark.parametrize("box3", [True, False])
@pytest.mark.parametrize("key,label", [
    ("account", "Ordinary account"),
    ("account-pensioen", "DEGIRO Pensioen"),
    ("PENSIOEN-FUND", "Savings for pensioen"),
])
def test_box3_treatment_is_independent_of_account_key_and_label(box3, key, label):
    fact = FactRecord(
        account_key=key, account_label=label, interest_received=5,
        extra=FactMetadata(box3=box3),
    )
    assert fact.extra.box3 is box3
    coverage = coverage_for_year(2024, [fact])
    assert coverage.source_fact_count == (1 if box3 else 0)
    assert coverage.known_combined_actual_return == (5 if box3 else None)


@pytest.mark.parametrize("value", [None, 0, 1, "true", "false", "yes", []])
def test_box3_treatment_rejects_non_booleans(value):
    with pytest.raises(ValidationError, match="box3"):
        FactMetadata(box3=value)


def test_parser_must_explicitly_set_box3_treatment():
    fact = AccountYearFact(2024, "bank", "account", "Account")
    with pytest.raises(ValueError, match="must explicitly classify Box 3"):
        ParseResult("bank", "annual_statement", 2024, facts=[fact])


@pytest.mark.parametrize("box3", [True, False])
def test_parser_can_explicitly_include_or_exclude_a_fact(box3):
    fact = AccountYearFact(2024, "bank", "account", "Account", extra=FactMetadata(box3=box3))
    result = ParseResult("bank", "annual_statement", 2024, facts=[fact])
    assert result.facts[0].extra.box3 is box3


@pytest.mark.parametrize("issuer,text", SAMPLES.items())
def test_supported_document_parsers_emit_explicit_box3_treatment(issuer, text):
    classification = classify(text)
    assert classification is not None
    result = parse_document(issuer, classification.doc_type, text, 2024)
    assert result.facts or result.tax_return
    for fact in result.facts:
        assert "box3" in fact.extra.model_fields_set
        assert type(fact.extra.box3) is bool
        assert fact.extra.model_dump(exclude_unset=True)["box3"] is fact.extra.box3


@pytest.mark.parametrize("box3", [True, False])
def test_box3_treatment_survives_storage_and_controls_audit_inclusion(box3):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_db(conn)
    upsert_document(conn, content_sha256="synthetic", byte_size=1, imported_at="2026-01-01", parse_status="parsed")
    fact = AccountYearFact(
        2024, "bank", "account-pensioen", "Savings for pensioen",
        interest_received=5, extra=FactMetadata(box3=box3),
    )
    insert_facts(conn, "synthetic", [fact])
    conn.execute("UPDATE account_year_facts SET is_canonical=1")
    row = conn.execute("SELECT * FROM account_year_facts").fetchone()
    assert json.loads(row["extra"])["box3"] is box3
    assert fact_from_row(row).extra.box3 is box3
    assets, sources = _asset_and_fact_rows(conn, 2024)
    assert len(assets) == (1 if box3 else 0)
    assert sources[0].included_in_year_total is box3
    assert sources[0].exclusion_reason == (None if box3 else "excluded from Box 3")
