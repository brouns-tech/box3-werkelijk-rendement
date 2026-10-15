from dataclasses import asdict
import sqlite3
import io
import csv
import json
import zipfile

import pytest

from wr.db import init_db, insert_facts, insert_period_facts
from wr.dedupe import canonicalize_facts
from wr.models import AccountPeriodFact, AccountYearFact
from wr.portfolio import _coverage_for_year, rebuild_portfolio
from wr.export import create_audit_export
from wr.config import PartnerSettings
from wr.recommend import _individual_portfolio


@pytest.fixture
def conn():
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    init_db(connection)
    yield connection
    connection.close()


def period(start, end, **kwargs):
    return AccountPeriodFact(tax_year=2024, issuer="example", account_key="example-account",
                             account_label="Example investment", period_start=start,
                             period_end=end, **kwargs)


def store(conn, sha, facts):
    conn.execute("INSERT OR IGNORE INTO documents (content_sha256, byte_size, imported_at, parse_status) VALUES (?, 1, 'now', 'parsed')", (sha,))
    for fact in facts:
        fact.compute_capital_gain()
    insert_period_facts(conn, sha, facts)


def annual(conn):
    canonicalize_facts(conn)
    return conn.execute("SELECT * FROM account_year_facts WHERE is_canonical = 1").fetchone()


def test_full_year_from_mixed_monthly_daily_and_quarterly_periods(conn):
    # No cadence-specific aggregation: a day, remainder of month, two months,
    # then quarters, all in one source document.
    ranges = [("2024-01-01", "2024-01-01"), ("2024-01-02", "2024-01-31"),
              ("2024-02-01", "2024-03-31"), ("2024-04-01", "2024-06-30"),
              ("2024-07-01", "2024-09-30"), ("2024-10-01", "2024-12-31")]
    store(conn, "mixed", [period(start, end, start_balance=100 + i * 15,
                                 end_balance=115 + i * 15, deposits=10, withdrawals=0)
                           for i, (start, end) in enumerate(ranges)])
    fact = annual(conn)
    assert (fact["start_balance"], fact["end_balance"], fact["deposits"]) == (100, 190, 60)
    assert fact["capital_gain"] == 30
    assert _coverage_for_year(conn, 2024).coverage_status == "COMPLETE"
    assert conn.execute("SELECT COUNT(*) FROM account_period_facts").fetchone()[0] == 6
    again = annual(conn)
    assert again["capital_gain"] == fact["capital_gain"]
    assert conn.execute("SELECT COUNT(*) FROM account_year_facts").fetchone()[0] == 1


def test_duplicate_period_reports_count_once(conn):
    fact = period("2024-01-01", "2024-12-31", capital_gain=12, gain_method="earned_return")
    store(conn, "copy-one", [fact])
    store(conn, "copy-two", [fact])
    assert annual(conn)["capital_gain"] == 12
    assert _coverage_for_year(conn, 2024).coverage_status == "COMPLETE"


def test_overlaps_never_double_count_and_remain_partial(conn):
    store(conn, "q1", [period("2024-01-01", "2024-03-31", capital_gain=5, gain_method="earned_return")])
    store(conn, "h1", [period("2024-01-01", "2024-06-30", capital_gain=10, gain_method="earned_return")])
    store(conn, "h2", [period("2024-07-01", "2024-12-31", capital_gain=20, gain_method="earned_return")])
    assert annual(conn)["capital_gain"] == 30
    result = _coverage_for_year(conn, 2024)
    assert result.coverage_status == "PARTIAL"
    assert "overlapping period" in str(result.missing)


def test_missing_middle_and_balance_discontinuity_are_partial(conn):
    store(conn, "gap", [period("2024-01-01", "2024-03-31", start_balance=0, end_balance=10, capital_gain=10, gain_method="earned_return"),
                        period("2024-07-01", "2024-09-30", start_balance=20, end_balance=30, capital_gain=10, gain_method="earned_return"),
                        period("2024-10-01", "2024-12-31", start_balance=40, end_balance=50, capital_gain=10, gain_method="earned_return")])
    assert annual(conn)["capital_gain"] == 30
    result = _coverage_for_year(conn, 2024)
    assert result.coverage_status == "PARTIAL"
    assert "2024-04-01/2024-06-30" in str(result.missing)
    assert "balance discontinuity" in str(result.missing)


def test_native_annual_evidence_takes_precedence(conn):
    store(conn, "source", [period("2024-01-01", "2024-03-31", capital_gain=5, gain_method="earned_return")])
    store(conn, "annual", [])
    fact = AccountYearFact(tax_year=2024, issuer="example", account_key="example-account", account_label="Annual", capital_gain=40, gain_method="earned_return")
    insert_facts(conn, "annual", [asdict(fact)])
    assert annual(conn)["capital_gain"] == 40
    assert _coverage_for_year(conn, 2024).coverage_status == "COMPLETE"


def test_unknown_period_return_is_not_zero_or_complete(conn):
    store(conn, "unknown", [period("2024-01-01", "2024-12-31", start_balance=100, end_balance=200)])
    assert annual(conn)["capital_gain"] is None
    assert _coverage_for_year(conn, 2024).coverage_status == "PARTIAL"


def test_account_identity_uses_same_normalization_as_annual_dedupe(conn):
    first = period("2024-01-01", "2024-06-30", capital_gain=5, gain_method="earned_return")
    second = period("2024-07-01", "2024-12-31", capital_gain=10, gain_method="earned_return")
    second.account_key = "EXAMPLE -ACCOUNT"
    store(conn, "source", [first, second])
    assert annual(conn)["capital_gain"] == 15
    assert _coverage_for_year(conn, 2024).coverage_status == "COMPLETE"


def test_annual_income_and_capital_are_counted_once(conn):
    store(conn, "income", [period("2024-01-01", "2024-12-31", start_balance=100,
                                  end_balance=125, deposits=10, withdrawals=0,
                                  interest_received=2, dividends_gross=3)])
    assert annual(conn)["capital_gain"] == 15
    assert _coverage_for_year(conn, 2024).known_combined_actual_return == 15


def test_individual_coverage_cannot_treat_quarter_as_full_year(conn):
    store(conn, "partial", [period("2024-01-01", "2024-03-31", holder_names=["A. Example"],
                                   capital_gain=5, gain_method="earned_return")])
    annual(conn)
    result = _individual_portfolio(conn, 2024, "A. Example", PartnerSettings(partner_a="A. Example"))
    assert result[0] == 5
    assert result[1] == "PARTIAL"


def test_audit_export_includes_all_native_periods_and_sources(conn):
    for sha, start, end in [("first", "2024-01-01", "2024-06-30"), ("second", "2024-07-01", "2024-12-31")]:
        store(conn, sha, [period(start, end, capital_gain=5, gain_method="earned_return")])
    annual(conn)
    rebuild_portfolio(conn)
    with zipfile.ZipFile(io.BytesIO(create_audit_export(conn))) as bundle:
        records = list(csv.DictReader(io.StringIO(bundle.read("source_period_facts.csv").decode("utf-8-sig"))))
        assert {row["document_sha256"] for row in records} == {"first", "second"}
        assets = list(csv.DictReader(io.StringIO(bundle.read("assets.csv").decode("utf-8-sig"))))
        assert assets[0]["source_document_sha256s"] == "first;second"
        assert "source_period_facts.csv" in json.loads(bundle.read("manifest.json"))["files"]


def test_removed_or_failed_sources_remove_derived_summaries(conn):
    store(conn, "source", [period("2024-01-01", "2024-12-31", capital_gain=5, gain_method="earned_return")])
    annual(conn)
    rebuild_portfolio(conn)
    conn.execute("UPDATE documents SET parse_status = 'failed'")
    annual(conn)
    rebuild_portfolio(conn)
    assert conn.execute("SELECT COUNT(*) FROM account_year_facts").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM yearly_portfolio").fetchone()[0] == 0


@pytest.mark.parametrize("start,end", [("2023-12-31", "2024-03-31"), ("2024-10-01", "2025-01-01"), ("2024-04-01", "2024-03-31")])
def test_rejects_cross_year_and_reversed_periods(start, end):
    with pytest.raises(ValueError, match="Period dates"):
        period(start, end)
