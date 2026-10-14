"""Synthetic fund summaries: no customer documents or identifiers."""
import json
import re
import sqlite3
from dataclasses import asdict

import pytest

from wr.classify import classify
from wr.db import init_db, insert_facts
from wr.dedupe import canonicalize_facts
from wr.import_pipeline import run_import
from wr.models import AccountYearFact
from wr.parsers.revolut import parse_revolut
from wr.portfolio import _fact_return, _fact_has_actual_return


PORTFOLIO = "00000000-0000-0000-0000-000000000000"
USD_ACCOUNTS = [f"{i:032x}" for i in range(1, 5)]
EUR_ACCOUNTS = [f"{i:032x}" for i in range(5, 7)]


def overview(code, accounts, rows):
    return f"""Flexible Cash Funds Statement
Period Jan 1, 2025 - Dec 31, 2025
Generation date: Oct 14, 2026
ALEX EXAMPLE
Value, {code}{'      Value, EUR' if code != 'EUR' else ''}
Opening Balance {rows[0]}
Total Value purchased {rows[1]}
Total Value sold {rows[2]}
Portfolio Number {PORTFOLIO}
Total Earned Return {rows[3]}
Account Numbers
Total Fees {rows[4]}
{accounts[0]}
Total Withdrawn Return {rows[5]}
{accounts[1]}
Total Reinvested Return {rows[6]}
{' '.join(accounts[2:])}
Closing Balance {rows[7]}
Flexible Cash Funds - {code}
Revolut Securities Europe UAB
"""


USD = overview("USD", USD_ACCOUNTS, [
    "1,000.00 900.00", "520.00 460.00", "-800.00 -700.00",
    "45.1234 40.9876", "-15.1234 -13.9876", "-10.00 -9.00",
    "-20.00 -18.00", "720.00 600.00",
])
EUR = overview("EUR", EUR_ACCOUNTS, [
    "1,000.00", "320.00", "-800.00", "33.1234", "-13.1234",
    "-5.00", "-15.00", "520.00",
])
COMBINED = USD + "\n\f\n" * 47 + EUR


def test_combined_overviews_keep_identity_precision_fees_and_fx_separate():
    classification = classify(COMBINED)
    assert (classification.issuer, classification.doc_type) == ("revolut", "savings_statement")
    result = parse_revolut(COMBINED, None, "savings_statement")
    assert result.tax_year == 2025 and not result.notes
    usd, eur = result.facts
    assert usd.account_key == f"{PORTFOLIO}:fund:usd"
    assert eur.account_key == f"{PORTFOLIO}:fund:eur"
    for fact, accounts in [(usd, USD_ACCOUNTS), (eur, EUR_ACCOUNTS)]:
        assert fact.extra["account_numbers"] == accounts
        assert fact.extra["portfolio_number"] == PORTFOLIO
        assert fact.currency == "EUR"
        assert fact.holder_names == ["ALEX EXAMPLE"]
        assert fact.ownership == "individual"
        assert _fact_has_actual_return(asdict(fact))
    assert usd.extra["earned_return"] == 40.9876
    assert usd.extra["fees"] == -13.9876
    assert usd.extra["net_earned_return"] == 27
    assert usd.extra["fx_gain"] == -60
    assert usd.extra["summary"]["earned"] == [45.1234, 40.9876]
    assert (usd.deposits, usd.withdrawals) == (442, 709)
    assert usd.capital_gain == pytest.approx(-19.0124)
    assert _fact_return(asdict(usd)) == pytest.approx(-19.0124)
    assert eur.capital_gain == pytest.approx(33.1234)
    assert eur.extra["fx_gain"] == 0
    assert (eur.deposits, eur.withdrawals) == (305, 805)


@pytest.mark.parametrize("code", ["USD", "GBP"])
def test_foreign_overview_supports_both_currency_columns(code):
    fact = parse_revolut(USD.replace("USD", code), 2025, "savings_statement").facts[0]
    assert fact.extra["fund_currency"] == code
    assert fact.capital_gain == pytest.approx(-19.0124)


@pytest.mark.parametrize("change", [
    lambda t: t.replace("Total Earned Return 33.1234", "Total Earned Return unavailable"),
    lambda t: t.replace("Total Value sold -800.00", "Total Value sold unavailable"),
    lambda t: t.replace("Total Fees -13.1234", "Total Fees unavailable"),
    lambda t: t.replace("Total Reinvested Return -15.00", ""),
    lambda t: t.replace("Closing Balance 520.00", "Closing Balance 999.00"),
    lambda t: t.replace("Total Fees -13.1234", "Total Fees 13.1234"),
    lambda t: t.replace("Total Earned Return 33.1234", "Total Earned Return 3,,3.1234"),
])
def test_incomplete_or_inconsistent_summaries_never_guess_a_loss(change):
    result = parse_revolut(change(EUR), 2025, "savings_statement")
    fact = result.facts[0]
    assert result.notes
    assert fact.capital_gain is None and fact.gain_method == "unknown"
    assert fact.deposits is None and fact.withdrawals is None
    assert not _fact_has_actual_return(asdict(fact))
    assert _fact_return(asdict(fact)) is None


def test_zero_amount_markers_are_supported():
    text = overview("EUR", EUR_ACCOUNTS, ["1,000.00", "-", "-", "-", "-", "-", "-", "1,000.00"])
    result = parse_revolut(text, 2025, "savings_statement")
    assert not result.notes and result.facts[0].capital_gain == 0


def test_missing_identity_or_eur_column_does_not_use_year_fallback():
    for text in [EUR.replace(PORTFOLIO, "unknown").replace(EUR_ACCOUNTS[0], "unknown").replace(EUR_ACCOUNTS[1], "unknown"),
                 USD.replace("Value, EUR", "Value, CAD")]:
        result = parse_revolut(text, 2025, "savings_statement")
        assert not result.facts and result.notes


def test_single_legacy_account_uuid_is_supported():
    text = EUR.replace(f"Portfolio Number {PORTFOLIO}\n", "")
    text = text.replace("Account Numbers", f"Account Number {PORTFOLIO}")
    for account in EUR_ACCOUNTS:
        text = text.replace(account, "")
    assert parse_revolut(text, 2025, "savings_statement").facts[0].account_key == f"{PORTFOLIO}:fund:eur"


def test_account_number_order_does_not_change_identity():
    replacements = dict(zip(USD_ACCOUNTS, reversed(USD_ACCOUNTS)))
    reordered = re.sub(r"\b[0-9a-f]{32}\b", lambda m: replacements.get(m[0], m[0]), USD)
    assert reordered != USD
    a = parse_revolut(USD, 2025, "savings_statement").facts[0]
    b = parse_revolut(reordered, 2025, "savings_statement").facts[0]
    assert a.account_key == b.account_key
    assert a.extra["account_numbers"] == b.extra["account_numbers"]


def test_overviews_do_not_mix_portfolios_or_holders():
    other = EUR.replace(PORTFOLIO, "00000000-0000-0000-0000-000000000001")
    other = other.replace("ALEX EXAMPLE", "SAM SAMPLE")
    a, b = parse_revolut(EUR + "\n\f\n" + other, 2025, "savings_statement").facts
    assert a.account_key != b.account_key
    assert a.holder_names == ["ALEX EXAMPLE"] and b.holder_names == ["SAM SAMPLE"]


def test_interim_and_cross_year_statements_are_unsupported():
    for text in [EUR.replace("Jan 1", "Feb 1"), EUR.replace("Dec 31, 2025", "Dec 31, 2026")]:
        assert classify(text) is None
        assert not parse_revolut(text, 2025, "savings_statement").facts
    assert not parse_revolut(EUR, 2024, "savings_statement").facts


def test_reprocessing_replaces_obsolete_fact_and_deduplicates_each_fund(tmp_path, monkeypatch):
    from wr import import_pipeline
    folder = tmp_path / "documents"
    folder.mkdir()
    (folder / "statement.pdf").write_bytes(b"synthetic statement placeholder")
    monkeypatch.setattr(import_pipeline, "extract_text", lambda path: (COMBINED, 90))
    database = tmp_path / "funds.sqlite"
    assert run_import(folder, database).parsed == 1
    with sqlite3.connect(database) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("DELETE FROM account_year_facts")
        conn.execute("INSERT INTO account_year_facts(document_sha256,tax_year,issuer,account_key,capital_gain,gain_method) SELECT content_sha256,2025,'revolut','revolut-savings-2025',-9999,'balance_flow' FROM documents")
        conn.execute("UPDATE documents SET processing_profile = 'pdfium-layout-v2/parsers-v3/old'")
    assert run_import(folder, database).parsed == 1
    with sqlite3.connect(database) as conn:
        conn.row_factory = sqlite3.Row
        facts = conn.execute("SELECT * FROM account_year_facts ORDER BY account_key").fetchall()
        assert len(facts) == 2 and all(f["is_canonical"] for f in facts)
        assert all(f["ownership"] == "individual" for f in facts)
        assert all(json.loads(f["holder_names"]) == ["ALEX EXAMPLE"] for f in facts)
        # Duplicate evidence stays one canonical fact per portfolio and fund,
        # rather than one per underlying account number.
        conn.execute("INSERT INTO documents(content_sha256,byte_size,imported_at,parse_status,doc_type) VALUES('duplicate',1,'now','parsed','savings_statement')")
        duplicate = parse_revolut(COMBINED, 2025, "savings_statement").facts
        insert_facts(conn, "duplicate", [asdict(f) for f in duplicate])
        canonicalize_facts(conn)
        assert conn.execute("SELECT COUNT(*) FROM account_year_facts WHERE is_canonical=1").fetchone()[0] == 2
        from wr.portfolio import _coverage_for_year
        assert _coverage_for_year(conn, 2025).known_combined_actual_return == 14.11
    assert run_import(folder, database).duplicate == 1


def test_issuer_names_do_not_prove_joint_ownership():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_db(conn)
    conn.execute("INSERT INTO documents(content_sha256,byte_size,imported_at,parse_status,doc_type) VALUES('test',1,'now','parsed','savings_statement')")
    facts = [
        AccountYearFact(2025, "bank", "one", "One", holder_names=["ALEX EXAMPLE"]),
        AccountYearFact(2025, "bank", "two", "Two", holder_names=["Alex Example"]),
        AccountYearFact(2025, "bank", "unknown", "Unknown"),
    ]
    insert_facts(conn, "test", [asdict(f) for f in facts])
    canonicalize_facts(conn)
    unknown = conn.execute("SELECT * FROM account_year_facts WHERE account_key='unknown'").fetchone()
    assert unknown["ownership"] == "unknown" and json.loads(unknown["holder_names"]) == []
    insert_facts(conn, "test", [asdict(f) for f in [
        AccountYearFact(2025, "bank", "joint", "Joint", holder_names=["ALEX EXAMPLE", "SAM SAMPLE"]),
        AccountYearFact(2025, "bank", "joint:deposit", "Joint deposit"),
    ]])
    canonicalize_facts(conn)
    joint = conn.execute("SELECT * FROM account_year_facts WHERE account_key='joint:deposit'").fetchone()
    assert joint["ownership"] == "joint"
