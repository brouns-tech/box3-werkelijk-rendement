import sqlite3

import pytest

from wr.storage.migrations import SCHEMA, SCHEMA_VERSION, init_db


def test_database_migrations_are_versioned_and_idempotent():
    conn = sqlite3.connect(":memory:")

    init_db(conn)
    init_db(conn)

    versions = [row[0] for row in conn.execute("SELECT version FROM schema_migrations")]
    assert versions == list(range(1, SCHEMA_VERSION + 1))


def test_legacy_schema_receives_missing_columns():
    conn = sqlite3.connect(":memory:")
    conn.executescript(
        """
        CREATE TABLE partner_tax_results (tax_year INTEGER, partner TEXT);
        CREATE TABLE yearly_portfolio (tax_year INTEGER);
        """
    )

    init_db(conn)

    result_columns = {
        row[1] for row in conn.execute("PRAGMA table_info(taxpayer_tax_results)")
    }
    portfolio_columns = {
        row[1] for row in conn.execute("PRAGMA table_info(yearly_portfolio)")
    }
    assert "estimated_tax_savings" in result_columns
    assert {"dividends_gross", "withholding_tax"} <= portfolio_columns


def legacy_database():
    conn = sqlite3.connect(":memory:")
    conn.executescript(SCHEMA)
    conn.execute("CREATE TABLE schema_migrations (version INTEGER PRIMARY KEY)")
    conn.executemany("INSERT INTO schema_migrations VALUES (?)", [(1,), (2,), (3,)])
    conn.commit()
    return conn


def test_taxpayer_migration_preserves_results_and_rejects_legacy_codes():
    conn = legacy_database()
    conn.executemany(
        """INSERT INTO partner_tax_results
           (tax_year, partner, partner_name, allocated_actual_return, estimated_tax_savings,
            recommendation, coverage_status, notes)
           VALUES (2024, ?, ?, ?, ?, 'ACTUAL_BETTER', 'COMPLETE', 'Original evidence')""",
        [("a", "Alex Example", 100, 32), ("b", "Blair Example", 200, 64)],
    )
    conn.commit()
    init_db(conn)
    init_db(conn)
    assert conn.execute(
        """SELECT taxpayer_position, taxpayer_name, allocated_actual_return,
                  estimated_tax_savings, notes
           FROM taxpayer_tax_results ORDER BY taxpayer_position"""
    ).fetchall() == [
        ("primary", "Alex Example", 100, 32, "Original evidence"),
        ("secondary", "Blair Example", 200, 64, "Original evidence"),
    ]
    assert conn.execute("SELECT name FROM sqlite_master WHERE name='partner_tax_results'").fetchone() is None
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO taxpayer_tax_results (tax_year, taxpayer_position) VALUES (2025, 'a')")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO taxpayer_tax_results (tax_year, taxpayer_position) VALUES (2025, 'child')")


def test_failed_taxpayer_migration_rolls_back_schema_and_results():
    conn = legacy_database()
    conn.execute(
        """INSERT INTO partner_tax_results (tax_year, partner, recommendation, coverage_status)
           VALUES (2024, 'unexpected', 'EQUAL', 'UNKNOWN')"""
    )
    conn.commit()
    with pytest.raises(sqlite3.IntegrityError):
        init_db(conn)
    assert conn.execute("SELECT partner FROM partner_tax_results").fetchall() == [("unexpected",)]
    assert conn.execute("SELECT name FROM sqlite_master WHERE name='taxpayer_tax_results'").fetchone() is None
    assert conn.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0] == 3
