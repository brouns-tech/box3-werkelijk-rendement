from __future__ import annotations

import sqlite3


SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    content_sha256 TEXT PRIMARY KEY,
    byte_size INTEGER NOT NULL,
    page_count INTEGER,
    first_seen_path TEXT,
    imported_at TEXT NOT NULL,
    issuer TEXT,
    doc_type TEXT,
    tax_year INTEGER,
    raw_text_excerpt TEXT,
    parse_status TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS account_year_facts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_sha256 TEXT NOT NULL REFERENCES documents(content_sha256),
    tax_year INTEGER NOT NULL,
    issuer TEXT NOT NULL,
    account_key TEXT NOT NULL,
    account_label TEXT,
    holder_names TEXT,
    ownership TEXT,
    currency TEXT DEFAULT 'EUR',
    start_balance REAL,
    end_balance REAL,
    deposits REAL,
    withdrawals REAL,
    interest_received REAL,
    interest_paid REAL,
    dividends_gross REAL,
    withholding_tax REAL,
    capital_gain REAL,
    gain_method TEXT,
    logical_group TEXT,
    is_canonical INTEGER DEFAULT 0,
    extra TEXT,
    UNIQUE(document_sha256, account_key, tax_year)
);

CREATE TABLE IF NOT EXISTS tax_returns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_sha256 TEXT NOT NULL REFERENCES documents(content_sha256),
    tax_year INTEGER NOT NULL,
    filer_name TEXT,
    full_year_fiscal_partners INTEGER NOT NULL DEFAULT 0,
    partner_a_name TEXT,
    partner_b_name TEXT,
    bezittingen_0101 REAL,
    bezittingen_3112 REAL,
    schulden_0101 REAL,
    schulden_3112 REAL,
    heffingsvrij_vermogen REAL,
    grondslag REAL,
    grondslag_a REAL,
    grondslag_b REAL,
    allocation_a REAL,
    allocation_b REAL,
    allocation_status TEXT,
    voordeel_a REAL,
    voordeel_b REAL,
    box3_tax_a REAL,
    box3_tax_b REAL,
    UNIQUE(document_sha256, tax_year)
);

CREATE TABLE IF NOT EXISTS yearly_portfolio (
    tax_year INTEGER PRIMARY KEY,
    coverage_status TEXT NOT NULL,
    known_combined_actual_return REAL,
    start_balance REAL,
    end_balance REAL,
    deposits REAL,
    withdrawals REAL,
    interest_received REAL,
    dividends_net REAL,
    dividends_gross REAL,
    withholding_tax REAL,
    capital_gain REAL,
    source_fact_count INTEGER,
    missing_asset_summary TEXT
);

CREATE TABLE IF NOT EXISTS partner_tax_results (
    tax_year INTEGER NOT NULL,
    partner TEXT NOT NULL,
    partner_name TEXT,
    allocation_ratio REAL,
    allocated_actual_return REAL,
    fictitious_return REAL,
    estimated_box3_tax_actual REAL,
    estimated_box3_tax_fictitious REAL,
    estimated_tax_savings REAL,
    recommendation TEXT NOT NULL,
    coverage_status TEXT NOT NULL,
    notes TEXT,
    PRIMARY KEY (tax_year, partner)
);
"""

SCHEMA_VERSION = 3


def init_db(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    applied = {
        row[0] for row in conn.execute("SELECT version FROM schema_migrations")
    }
    for version, migration in ((1, _migration_1), (2, _migration_2), (3, _migration_3)):
        if version in applied:
            continue
        with conn:
            migration(conn)
            conn.execute(
                "INSERT INTO schema_migrations (version) VALUES (?)", (version,)
            )


def _migration_1(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)


def _migration_2(conn: sqlite3.Connection) -> None:
    _add_column_if_missing(
        conn, "partner_tax_results", "estimated_tax_savings", "REAL"
    )
    _add_column_if_missing(conn, "yearly_portfolio", "dividends_gross", "REAL")
    _add_column_if_missing(conn, "yearly_portfolio", "withholding_tax", "REAL")


def _migration_3(conn: sqlite3.Connection) -> None:
    _add_column_if_missing(conn, "documents", "processing_profile", "TEXT")


def _add_column_if_missing(
    conn: sqlite3.Connection, table: str, column: str, definition: str
) -> None:
    columns = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
    if column not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
