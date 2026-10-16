import io
import csv
import json
import sqlite3
from zipfile import ZipFile

import pytest

from wr.calculations.coverage import coverage_for_year
from wr.calculations.returns import fact_return
from wr.export import create_audit_export
from wr.models.facts import AccountYearFact, GainMethod, Ownership
from wr.models.metadata import FactMetadata
from wr.models.reconciliation import AttributeField, EvidenceStatus
from wr.models.storage import MoneyField
from wr.parsers.flatex import FlatexMetadata
from wr.reconciliation.service import reconcile_facts
from wr.storage.documents import clear_document_records, upsert_document
from wr.storage.facts import insert_facts
from wr.storage.migrations import init_db
from wr.storage.reconciliation import reconciled_facts, source_observations


@pytest.fixture
def connection():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_db(conn)
    yield conn
    conn.close()


def observe(conn, sha, *, year=2024, issuer="bank", key="account", doc_type="annual_statement", **values):
    upsert_document(conn, content_sha256=sha, byte_size=1, imported_at="now", parse_status="parsed")
    conn.execute("UPDATE documents SET doc_type = ? WHERE content_sha256 = ?", (doc_type, sha))
    insert_facts(conn, sha, [AccountYearFact(year, issuer, key, "Account", **values)])
    conn.commit()


def evidence(fact, field):
    return next(item for item in fact.evidence if item.field == field)


def source_snapshot(conn):
    return [tuple(row) for row in conn.execute("SELECT * FROM account_year_facts ORDER BY id")]


def test_complementary_evidence_and_agreement_without_mutating_sources(connection):
    observe(connection, "balances", key="NL00 BANK", start_balance=100, end_balance=110,
            holder_names=["Alex Example"])
    observe(connection, "income", key="nl00bank", interest_received=10, end_balance=110)
    before = source_snapshot(connection)
    reconcile_facts(connection)
    fact = reconciled_facts(connection, 2024)[0]
    assert fact.start_balance == 100
    assert fact.interest_received == 10
    assert fact_return(fact) == 10
    assert fact.holder_names == ["Alex Example"]
    assert fact.ownership == Ownership.INDIVIDUAL
    assert evidence(fact, MoneyField.END_BALANCE).status == EvidenceStatus.AGREEMENT
    assert evidence(fact, MoneyField.INTEREST_RECEIVED).status == EvidenceStatus.SINGLE_SOURCE
    assert len(fact.source_fact_ids) == 2
    assert coverage_for_year(2024, [fact]).source_fact_count == 1
    assert source_snapshot(connection) == before
    payload = fact.model_dump_json()
    reconcile_facts(connection)
    assert reconciled_facts(connection, 2024)[0].model_dump_json() == payload
    assert source_snapshot(connection) == before


def test_conflicting_values_remain_visible_and_block_financial_inference(connection):
    observe(connection, "first", interest_received=10)
    observe(connection, "second", interest_received=20)
    reconcile_facts(connection)
    fact = reconciled_facts(connection, 2024)[0]
    conflict = evidence(fact, MoneyField.INTEREST_RECEIVED)
    assert conflict.status == EvidenceStatus.CONFLICT
    assert {item.value for item in conflict.sources} == {10, 20}
    assert fact.interest_received is None
    assert fact_return(fact) is None
    coverage = coverage_for_year(2024, [fact])
    assert coverage.coverage_status == "PARTIAL"
    assert "conflicting source evidence" in coverage.missing[0]


@pytest.mark.parametrize("field,first,second", [
    (AttributeField.HOLDERS, {"holder_names": ["Alex Example"]}, {"holder_names": ["Blair Example"]}),
    (AttributeField.OWNERSHIP, {"ownership": "individual"}, {"ownership": "joint"}),
    (AttributeField.CURRENCY, {"currency": "EUR"}, {"currency": "USD"}),
    (AttributeField.BOX3, {"extra": FactMetadata(box3=True)}, {"extra": FactMetadata(box3=False)}),
])
def test_safety_relevant_attribute_conflicts_are_not_arbitrarily_selected(connection, field, first, second):
    observe(connection, "first", interest_received=10, **first)
    observe(connection, "second", interest_received=10, **second)
    reconcile_facts(connection)
    fact = reconciled_facts(connection, 2024)[0]
    assert evidence(fact, field).status == EvidenceStatus.CONFLICT
    assert fact_return(fact) is None
    assert coverage_for_year(2024, [fact]).coverage_status == "PARTIAL"


def test_reported_ownership_conflict_is_not_overridden_by_holder_inference(connection):
    observe(connection, "individual", interest_received=10, holder_names=["Alex Example"], ownership="individual")
    observe(connection, "joint", interest_received=10, holder_names=["Alex Example"], ownership="joint")
    reconcile_facts(connection)
    fact = reconciled_facts(connection, 2024)[0]
    assert evidence(fact, AttributeField.OWNERSHIP).status == EvidenceStatus.CONFLICT
    assert fact.ownership == Ownership.UNKNOWN
    assert fact_return(fact) is None


def test_repeated_identical_pdf_does_not_duplicate_evidence_or_return(connection):
    observe(connection, "same-hash", interest_received=10)
    observe(connection, "same-hash", interest_received=10)
    reconcile_facts(connection)
    fact = reconciled_facts(connection, 2024)[0]
    item = evidence(fact, MoneyField.INTEREST_RECEIVED)
    assert item.status == EvidenceStatus.SINGLE_SOURCE
    assert len(item.sources) == 1
    assert fact_return(fact) == 10


def test_distinct_documents_agree_but_do_not_add_the_same_interest_twice(connection):
    observe(connection, "original", interest_received=10)
    observe(connection, "another-document", interest_received=10)
    reconcile_facts(connection)
    fact = reconciled_facts(connection, 2024)[0]
    assert evidence(fact, MoneyField.INTEREST_RECEIVED).status == EvidenceStatus.AGREEMENT
    assert fact_return(fact) == 10


def test_money_comparison_uses_cents_but_preserves_original_source_values(connection):
    observe(connection, "first", interest_received=10.001)
    observe(connection, "second", interest_received=10.004)
    reconcile_facts(connection)
    fact = reconciled_facts(connection, 2024)[0]
    support = evidence(fact, MoneyField.INTEREST_RECEIVED)
    assert support.status == EvidenceStatus.AGREEMENT
    assert {source.value for source in support.sources} == {10.001, 10.004}
    assert fact.interest_received == 10


def test_missing_fields_do_not_claim_single_source_support(connection):
    observe(connection, "statement", interest_received=10)
    reconcile_facts(connection)
    support = evidence(reconciled_facts(connection, 2024)[0], MoneyField.DEPOSITS)
    assert support.status == EvidenceStatus.MISSING
    assert support.sources == []


def test_derive_capital_gain_from_complementary_inputs(connection):
    observe(connection, "valuation", start_balance=100, end_balance=110)
    observe(connection, "flows", deposits=0, withdrawals=0, dividends_gross=5, withholding_tax=1)
    reconcile_facts(connection)
    fact = reconciled_facts(connection, 2024)[0]
    assert fact.capital_gain == 6
    assert fact.gain_method == GainMethod.BALANCE_FLOW
    assert fact_return(fact) == 15
    item = evidence(fact, MoneyField.CAPITAL_GAIN)
    assert item.status == EvidenceStatus.DERIVED
    assert {source.document_sha256 for source in item.sources} == {"valuation", "flows"}


def test_explicit_market_gain_and_complementary_interest_are_both_counted(connection):
    observe(connection, "market", capital_gain=20, gain_method=GainMethod.EXPLICIT)
    observe(connection, "income", interest_received=5, capital_gain=5, gain_method=GainMethod.INTEREST_ONLY)
    reconcile_facts(connection)
    fact = reconciled_facts(connection, 2024)[0]
    assert fact_return(fact) == 25
    assert evidence(fact, AttributeField.GAIN_METHOD).rule == "explicit_market_gain_with_separate_interest"


def test_holder_inference_does_not_leak_between_accounts_or_years(connection):
    observe(connection, "other", key="another-account", holder_names=["Alex Example"])
    observe(connection, "prior", year=2023, holder_names=["Blair Example"])
    observe(connection, "current", interest_received=10)
    reconcile_facts(connection)
    fact = next(fact for fact in reconciled_facts(connection, 2024) if fact.account_key == "account")
    assert fact.holder_names == []
    assert fact.ownership == Ownership.UNKNOWN


def test_removing_document_invalidates_results_and_removes_old_support(connection):
    observe(connection, "first", interest_received=10)
    observe(connection, "second", interest_received=10)
    reconcile_facts(connection)
    clear_document_records(connection, "second")
    connection.commit()
    assert reconciled_facts(connection, 2024) == []
    reconcile_facts(connection)
    assert evidence(reconciled_facts(connection, 2024)[0], MoneyField.INTEREST_RECEIVED).status == EvidenceStatus.SINGLE_SOURCE
    clear_document_records(connection, "first")
    connection.commit()
    reconcile_facts(connection)
    assert reconciled_facts(connection, 2024) == []


def test_reconciliation_replacement_is_atomic(connection, monkeypatch):
    observe(connection, "source", interest_received=10)
    reconcile_facts(connection)
    before = reconciled_facts(connection, 2024)

    def fail(conn, facts):
        conn.execute("DELETE FROM reconciled_facts")
        raise RuntimeError("write failed")

    monkeypatch.setattr("wr.reconciliation.service.replace_reconciled_facts", fail)
    with pytest.raises(RuntimeError, match="write failed"):
        reconcile_facts(connection)
    assert reconciled_facts(connection, 2024) == before


def test_flatex_period_deduplication_and_cross_year_provenance(connection):
    observe(connection, "inventory-2023", issuer="flatex", year=2023,
            doc_type="financial_instruments_statement", end_balance=100, extra=FlatexMetadata())
    observe(connection, "inventory-2024", issuer="flatex",
            doc_type="financial_instruments_statement", end_balance=120, extra=FlatexMetadata())
    for sha in ("statement", "statement-copy"):
        observe(connection, sha, issuer="flatex", doc_type="account_statement",
                deposits=10, withdrawals=5, extra=FlatexMetadata(statement_number=1))
    before = source_snapshot(connection)
    reconcile_facts(connection)
    fact = reconciled_facts(connection, 2024)[0]
    assert fact.deposits == 10
    assert fact.withdrawals == 5
    assert fact_return(fact) == 15
    assert evidence(fact, MoneyField.START_BALANCE).sources[0].document_sha256 == "inventory-2023"
    assert source_snapshot(connection) == before
    assert len(source_observations(connection, 2024)) == 3
    with ZipFile(io.BytesIO(create_audit_export(connection, [2024]))) as bundle:
        exported = json.loads(bundle.read("reconciled_facts.json"))[0]
        assert exported["capital_gain"] == 15
        assert "inventory-2023" in bundle.read("source_facts.csv").decode()
        assert json.loads(bundle.read("manifest.json"))["version"] == 3
    with ZipFile(io.BytesIO(create_audit_export(connection, [2023, 2024]))) as bundle:
        assets = list(csv.DictReader(io.StringIO(bundle.read("assets.csv").decode("utf-8-sig"))))
        sources = list(csv.DictReader(io.StringIO(bundle.read("source_facts.csv").decode("utf-8-sig"))))
        prior = next(row for row in sources if row["document_sha256"] == "inventory-2023")
        assert set(prior["matched_asset_ids"].split(";")) == {row["asset_id"] for row in assets}
        assert len({row["fact_id"] for row in sources}) == len(sources)


def test_flatex_conflicting_copies_of_same_period_are_not_summed(connection):
    observe(connection, "inventory-2023", issuer="flatex", year=2023,
            doc_type="financial_instruments_statement", end_balance=100, extra=FlatexMetadata())
    observe(connection, "inventory-2024", issuer="flatex",
            doc_type="financial_instruments_statement", end_balance=120, extra=FlatexMetadata())
    for sha, deposit in (("first", 10), ("conflicting-copy", 20)):
        observe(connection, sha, issuer="flatex", doc_type="account_statement",
                deposits=deposit, withdrawals=0, extra=FlatexMetadata(statement_number=1))
    reconcile_facts(connection)
    fact = reconciled_facts(connection, 2024)[0]
    assert evidence(fact, MoneyField.DEPOSITS).status == EvidenceStatus.CONFLICT
    assert fact.deposits is None
    assert fact_return(fact) is None


def test_cross_year_inventory_currencies_must_agree(connection):
    observe(connection, "prior", issuer="flatex", year=2023, currency="USD",
            doc_type="financial_instruments_statement", end_balance=100, extra=FlatexMetadata())
    observe(connection, "current", issuer="flatex", doc_type="financial_instruments_statement",
            end_balance=120, extra=FlatexMetadata())
    observe(connection, "flows", issuer="flatex", doc_type="account_statement",
            deposits=0, withdrawals=0, extra=FlatexMetadata(statement_number=1))
    reconcile_facts(connection)
    fact = reconciled_facts(connection, 2024)[0]
    assert evidence(fact, MoneyField.START_BALANCE).status == EvidenceStatus.CONFLICT
    assert fact.start_balance is None
    assert fact_return(fact) is None


def test_detectable_statement_sequence_gaps_leave_annual_flows_unresolved(connection):
    observe(connection, "prior", issuer="flatex", year=2023,
            doc_type="financial_instruments_statement", end_balance=100, extra=FlatexMetadata())
    observe(connection, "current", issuer="flatex", doc_type="financial_instruments_statement",
            end_balance=120, extra=FlatexMetadata())
    for number in (1, 3):
        observe(connection, f"statement-{number}", issuer="flatex", doc_type="account_statement",
                deposits=10, withdrawals=0, extra=FlatexMetadata(statement_number=number))
    reconcile_facts(connection)
    fact = reconciled_facts(connection, 2024)[0]
    assert evidence(fact, MoneyField.DEPOSITS).status == EvidenceStatus.MISSING
    assert evidence(fact, MoneyField.DEPOSITS).rule == "missing_statement_periods"
    assert fact.deposits is None
    assert fact_return(fact) is None


def test_legacy_document_is_reparsed_even_when_extraction_profile_matches(tmp_path):
    from tests.support.pdf import synthetic_pdf
    from wr.documents.extraction import extraction_profile
    from wr.documents.hashing import sha256_file
    from wr.importing.pipeline import run_import
    from wr.storage.connection import connect

    documents = tmp_path / "documents"
    documents.mkdir()
    source = documents / "statement.pdf"
    synthetic_pdf(source)
    database = tmp_path / "results.sqlite"
    with connect(database) as conn:
        init_db(conn)
        observe(conn, sha256_file(source), interest_received=999)
        conn.execute("UPDATE documents SET processing_profile = ?, observations_version = 0", (extraction_profile(),))
    report = run_import(documents, database)
    assert report.parsed == 1
    assert report.duplicate == 0
    with connect(database) as conn:
        assert len(source_observations(conn)) == 1
        assert source_observations(conn)[0].interest_received == 12.34
        assert fact_return(reconciled_facts(conn, 2024)[0]) == 12.34
