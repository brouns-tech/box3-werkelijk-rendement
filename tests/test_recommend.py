import sqlite3

from wr.db import init_db
from wr.models import Recommendation
from wr.recommend import _results_for_year


def _connection() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_db(conn)
    return conn


def test_init_db_migrates_tax_savings_column():
    conn = sqlite3.connect(":memory:")
    conn.execute(
        """
        CREATE TABLE partner_tax_results (
            tax_year INTEGER NOT NULL,
            partner TEXT NOT NULL,
            PRIMARY KEY (tax_year, partner)
        )
        """
    )

    init_db(conn)

    columns = {row[1] for row in conn.execute("PRAGMA table_info(partner_tax_results)")}
    assert "estimated_tax_savings" in columns


def test_partial_coverage_compares_with_zero_return_assumption():
    conn = _connection()
    conn.execute(
        """
        INSERT INTO yearly_portfolio (
            tax_year, coverage_status, known_combined_actual_return,
            start_balance, end_balance, deposits, withdrawals,
            interest_received, dividends_net, capital_gain,
            source_fact_count, missing_asset_summary
        ) VALUES (2024, 'PARTIAL', 100, 0, 0, 0, 0, 0, 0, 100, 1, 'Missing Bank')
        """
    )
    conn.execute(
        """
        INSERT INTO documents (
            content_sha256, byte_size, imported_at, parse_status
        ) VALUES ('draft', 1, 'now', 'parsed')
        """
    )
    conn.execute(
        """
        INSERT INTO tax_returns (
            document_sha256, tax_year, filer_name, full_year_fiscal_partners,
            partner_a_name, partner_b_name, grondslag, grondslag_a, grondslag_b,
            allocation_a, allocation_b, allocation_status, voordeel_a, voordeel_b
        ) VALUES (
            'draft', 2024, 'Partner A', 0, 'Partner A', 'Partner B',
            100, 60, 40, 0.6, 0.4, 'ok', 999, 999
        )
        """
    )
    conn.execute(
        """
        INSERT INTO documents (
            content_sha256, byte_size, imported_at, parse_status
        ) VALUES ('return', 1, 'now', 'parsed')
        """
    )
    conn.execute(
        """
        INSERT INTO tax_returns (
            document_sha256, tax_year, filer_name, full_year_fiscal_partners,
            partner_a_name, partner_b_name, grondslag, grondslag_a, grondslag_b,
            allocation_a, allocation_b, allocation_status, voordeel_a, voordeel_b
        ) VALUES (
            'return', 2024, 'Partner A', 1, 'Partner A', 'Partner B',
            100, 60, 40, 0.6, 0.4, 'ok', 200, 80
        )
        """
    )

    results = _results_for_year(conn, 2024, {"partner_a": "Partner A"})

    assert [result.recommendation for result in results] == [
        Recommendation.ACTUAL_BETTER.value,
        Recommendation.ACTUAL_BETTER.value,
    ]
    assert results[0].allocated_actual_return == 60.0
    assert results[1].allocated_actual_return == 40.0
    assert results[0].fictitious_return == 200.0
    assert results[1].fictitious_return == 80.0
    assert abs(results[0].estimated_tax_savings - 50.4) < 0.001
    assert abs(results[1].estimated_tax_savings - 14.4) < 0.001
    assert all("assumed 0% return for missing assets" in result.notes for result in results)
    assert all(result.coverage_status == "PARTIAL" for result in results)


def test_single_filer_gets_savings_estimate():
    conn = _connection()
    conn.execute(
        """
        INSERT INTO yearly_portfolio (
            tax_year, coverage_status, known_combined_actual_return,
            start_balance, end_balance, deposits, withdrawals,
            interest_received, dividends_net, capital_gain,
            source_fact_count, missing_asset_summary
        ) VALUES (2022, 'PARTIAL', 0, 0, 0, 0, 0, 0, 0, 0, 0, 'Missing investment')
        """
    )
    conn.execute(
        """
        INSERT INTO documents (
            content_sha256, byte_size, imported_at, parse_status
        ) VALUES ('single', 1, 'now', 'parsed')
        """
    )
    conn.execute(
        """
        INSERT INTO tax_returns (
            document_sha256, tax_year, filer_name, full_year_fiscal_partners,
            partner_a_name, grondslag, grondslag_a, allocation_a,
            allocation_status, voordeel_a, box3_tax_a
        ) VALUES (
            'single', 2022, 'Partner A', 0, 'Partner A',
            28671, 28671, 1, 'ok', 521, 161
        )
        """
    )

    result = _results_for_year(conn, 2022, {"partner_a": "Partner A"})[0]

    assert result.recommendation == Recommendation.ACTUAL_BETTER.value
    assert result.estimated_box3_tax_actual == 0.0
    assert result.estimated_box3_tax_fictitious == 161.0
    assert result.estimated_tax_savings == 161.0
    assert "assumed 0% return for missing assets" in result.notes
