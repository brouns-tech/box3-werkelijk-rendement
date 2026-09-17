import sqlite3

from wr.db import init_db
from wr.portfolio import _coverage_for_year


def test_derives_inventory_from_canonical_statements_without_filed_assets():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_db(conn)
    conn.execute(
        """
        INSERT INTO documents (
            content_sha256, byte_size, imported_at, parse_status
        ) VALUES ('statement', 1, '2026-01-01T00:00:00+00:00', 'parsed')
        """
    )
    conn.execute(
        """
        INSERT INTO account_year_facts (
            document_sha256, tax_year, issuer, account_key, account_label,
            interest_received, capital_gain, gain_method, is_canonical
        ) VALUES (?, 2024, ?, ?, ?, ?, ?, 'interest_only', 1)
        """,
        (
            "statement",
            "rabobank",
            "NL00RABO0000000002",
            "Rabobank Rabo SpaarRekening",
            2007.58,
            2007.58,
        ),
    )
    conn.commit()

    result = _coverage_for_year(conn, 2024)

    assert result.coverage_status == "COMPLETE"
    assert result.known_combined_actual_return == 2007.58
    assert result.source_fact_count == 1
    assert result.missing == []


def test_excludes_degiro_pension_fact_from_box3_rollup():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_db(conn)
    conn.execute(
        """
        INSERT INTO documents (
            content_sha256, byte_size, imported_at, parse_status
        ) VALUES ('pension-statement', 1, '2026-01-01T00:00:00+00:00', 'parsed')
        """
    )
    conn.execute(
        """
        INSERT INTO account_year_facts (
            document_sha256, tax_year, issuer, account_key, account_label,
            capital_gain, gain_method, extra, is_canonical
        ) VALUES (?, 2023, 'degiro', 'example-pensioen', 'DEGIRO Pensioen',
                  9999.0, 'explicit', '{"box3": false}', 1)
        """,
        ("pension-statement",),
    )
    conn.commit()

    result = _coverage_for_year(conn, 2023)

    assert result.coverage_status == "UNKNOWN"
    assert result.known_combined_actual_return is None
    assert result.source_fact_count == 0
