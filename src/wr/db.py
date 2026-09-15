from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Iterable

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

CREATE TABLE IF NOT EXISTS declared_box3_assets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tax_year INTEGER NOT NULL,
    category TEXT NOT NULL,
    institution TEXT,
    account_id TEXT NOT NULL,
    label TEXT,
    balance_0101 REAL,
    balance_3112 REAL,
    coverage_status TEXT DEFAULT 'UNKNOWN',
    matched_fact_ids TEXT,
    source_document_sha256 TEXT,
    UNIQUE(tax_year, account_id, category)
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


def connect(db_path: str | Path) -> sqlite3.Connection:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    columns = {
        row[1] for row in conn.execute("PRAGMA table_info(partner_tax_results)").fetchall()
    }
    if "estimated_tax_savings" not in columns:
        conn.execute("ALTER TABLE partner_tax_results ADD COLUMN estimated_tax_savings REAL")
    portfolio_columns = {
        row[1] for row in conn.execute("PRAGMA table_info(yearly_portfolio)").fetchall()
    }
    if "dividends_gross" not in portfolio_columns:
        conn.execute("ALTER TABLE yearly_portfolio ADD COLUMN dividends_gross REAL")
    if "withholding_tax" not in portfolio_columns:
        conn.execute("ALTER TABLE yearly_portfolio ADD COLUMN withholding_tax REAL")
    conn.commit()


def upsert_document(conn: sqlite3.Connection, **kwargs: Any) -> bool:
    """Insert document if new. Returns True if inserted, False if already present."""
    cur = conn.execute(
        "SELECT 1 FROM documents WHERE content_sha256 = ?",
        (kwargs["content_sha256"],),
    )
    if cur.fetchone():
        return False
    conn.execute(
        """
        INSERT INTO documents (
            content_sha256, byte_size, page_count, first_seen_path, imported_at,
            issuer, doc_type, tax_year, raw_text_excerpt, parse_status
        ) VALUES (
            :content_sha256, :byte_size, :page_count, :first_seen_path, :imported_at,
            :issuer, :doc_type, :tax_year, :raw_text_excerpt, :parse_status
        )
        """,
        kwargs,
    )
    return True


def update_document(conn: sqlite3.Connection, sha: str, **kwargs: Any) -> None:
    cols = ", ".join(f"{k} = :{k}" for k in kwargs)
    params = dict(kwargs)
    params["content_sha256"] = sha
    conn.execute(f"UPDATE documents SET {cols} WHERE content_sha256 = :content_sha256", params)


def insert_facts(conn: sqlite3.Connection, document_sha: str, facts: Iterable[dict[str, Any]]) -> None:
    for fact in facts:
        payload = dict(fact)
        payload["document_sha256"] = document_sha
        if isinstance(payload.get("holder_names"), list):
            payload["holder_names"] = json.dumps(payload["holder_names"])
        if isinstance(payload.get("extra"), dict):
            payload["extra"] = json.dumps(payload["extra"])
        conn.execute(
            """
            INSERT INTO account_year_facts (
                document_sha256, tax_year, issuer, account_key, account_label,
                holder_names, ownership, currency, start_balance, end_balance,
                deposits, withdrawals, interest_received, interest_paid,
                dividends_gross, withholding_tax, capital_gain, gain_method,
                logical_group, is_canonical, extra
            ) VALUES (
                :document_sha256, :tax_year, :issuer, :account_key, :account_label,
                :holder_names, :ownership, :currency, :start_balance, :end_balance,
                :deposits, :withdrawals, :interest_received, :interest_paid,
                :dividends_gross, :withholding_tax, :capital_gain, :gain_method,
                :logical_group, :is_canonical, :extra
            )
            ON CONFLICT(document_sha256, account_key, tax_year) DO UPDATE SET
                account_label=excluded.account_label,
                holder_names=excluded.holder_names,
                ownership=excluded.ownership,
                start_balance=excluded.start_balance,
                end_balance=excluded.end_balance,
                deposits=excluded.deposits,
                withdrawals=excluded.withdrawals,
                interest_received=excluded.interest_received,
                interest_paid=excluded.interest_paid,
                dividends_gross=excluded.dividends_gross,
                withholding_tax=excluded.withholding_tax,
                capital_gain=excluded.capital_gain,
                gain_method=excluded.gain_method,
                logical_group=excluded.logical_group,
                extra=excluded.extra
            """,
            {
                "document_sha256": payload["document_sha256"],
                "tax_year": payload["tax_year"],
                "issuer": payload["issuer"],
                "account_key": payload["account_key"],
                "account_label": payload.get("account_label"),
                "holder_names": payload.get("holder_names"),
                "ownership": payload.get("ownership", "unknown"),
                "currency": payload.get("currency", "EUR"),
                "start_balance": payload.get("start_balance"),
                "end_balance": payload.get("end_balance"),
                "deposits": payload.get("deposits"),
                "withdrawals": payload.get("withdrawals"),
                "interest_received": payload.get("interest_received"),
                "interest_paid": payload.get("interest_paid"),
                "dividends_gross": payload.get("dividends_gross"),
                "withholding_tax": payload.get("withholding_tax"),
                "capital_gain": payload.get("capital_gain"),
                "gain_method": payload.get("gain_method", "unknown"),
                "logical_group": payload.get("logical_group"),
                "is_canonical": payload.get("is_canonical", 0),
                "extra": payload.get("extra"),
            },
        )


def clear_canonical_flags(conn: sqlite3.Connection, tax_year: int | None = None) -> None:
    if tax_year is None:
        conn.execute("UPDATE account_year_facts SET is_canonical = 0")
    else:
        conn.execute("UPDATE account_year_facts SET is_canonical = 0 WHERE tax_year = ?", (tax_year,))
