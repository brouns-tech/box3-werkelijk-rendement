from __future__ import annotations

import sqlite3

from wr.models.tax import TaxpayerTaxResult


def save_recommendation(conn: sqlite3.Connection, result: TaxpayerTaxResult) -> None:
    conn.execute(
        """
        INSERT INTO taxpayer_tax_results (
            tax_year, taxpayer_position, taxpayer_name, allocation_ratio,
            allocated_actual_return, fictitious_return,
            estimated_box3_tax_actual, estimated_box3_tax_fictitious,
            estimated_tax_savings, recommendation, coverage_status, notes
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            result.tax_year,
            result.taxpayer_position.value,
            result.taxpayer_name,
            result.allocation_ratio,
            result.allocated_actual_return,
            result.fictitious_return,
            result.estimated_box3_tax_actual,
            result.estimated_box3_tax_fictitious,
            result.estimated_tax_savings,
            result.recommendation,
            result.coverage_status,
            result.notes,
        ),
    )


def comparison_years(conn: sqlite3.Connection) -> set[int]:
    return {row[0] for row in conn.execute(
        "SELECT tax_year FROM tax_returns UNION SELECT tax_year FROM yearly_portfolio"
    ) if row[0] is not None}


def clear_recommendations(conn: sqlite3.Connection) -> None:
    conn.execute("DELETE FROM taxpayer_tax_results")
