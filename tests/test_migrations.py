import sqlite3

from wr.db import SCHEMA_VERSION, init_db


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
        row[1] for row in conn.execute("PRAGMA table_info(partner_tax_results)")
    }
    portfolio_columns = {
        row[1] for row in conn.execute("PRAGMA table_info(yearly_portfolio)")
    }
    assert "estimated_tax_savings" in result_columns
    assert {"dividends_gross", "withholding_tax"} <= portfolio_columns
