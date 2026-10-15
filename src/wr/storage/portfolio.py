from __future__ import annotations

import sqlite3

from wr.models.calculations import CoverageResult
from wr.models.storage import PortfolioRecord


def save_coverage(conn: sqlite3.Connection, result: CoverageResult) -> None:
    conn.execute(
        """
        INSERT INTO yearly_portfolio (
            tax_year, coverage_status, known_combined_actual_return,
            start_balance, end_balance, deposits, withdrawals,
            interest_received, dividends_net, capital_gain,
            source_fact_count, missing_asset_summary
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(tax_year) DO UPDATE SET
            coverage_status=excluded.coverage_status,
            known_combined_actual_return=excluded.known_combined_actual_return,
            start_balance=excluded.start_balance,
            end_balance=excluded.end_balance,
            deposits=excluded.deposits,
            withdrawals=excluded.withdrawals,
            interest_received=excluded.interest_received,
            dividends_net=excluded.dividends_net,
            capital_gain=excluded.capital_gain,
            source_fact_count=excluded.source_fact_count,
            missing_asset_summary=excluded.missing_asset_summary
        """,
        (
            result.tax_year,
            result.coverage_status,
            result.known_combined_actual_return,
            result.start_balance,
            result.end_balance,
            result.deposits,
            result.withdrawals,
            result.interest_received,
            result.dividends_net,
            result.capital_gain,
            result.source_fact_count,
            "; ".join(result.missing) if result.missing else None,
        ),
    )


def portfolio_for_year(conn: sqlite3.Connection, year: int) -> PortfolioRecord | None:
    row = conn.execute("SELECT * FROM yearly_portfolio WHERE tax_year = ?", (year,)).fetchone()
    return PortfolioRecord.model_validate(dict(row)) if row is not None else None
