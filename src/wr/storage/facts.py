from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict
from typing import Iterable
import json
import sqlite3

from wr.models import AccountYearFact
from wr.models.storage import FactRecord, FactWriteRecord
from wr.storage.adapters import fact_from_row


def insert_facts(
    conn: sqlite3.Connection,
    document_sha: str,
    facts: Iterable[AccountYearFact | FactRecord | Mapping[str, object]],
) -> None:
    for fact in facts:
        if isinstance(fact, AccountYearFact):
            source = asdict(fact)
        elif isinstance(fact, FactRecord):
            source = fact.model_dump()
        else:
            source = dict(fact)
        record = fact_from_row(source, FactWriteRecord)
        payload = record.model_dump(mode="json")
        payload["document_sha256"] = document_sha
        payload["holder_names"] = json.dumps(record.holder_names)
        payload["extra"] = record.extra.model_dump_json(exclude_unset=True)
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
            payload,
        )


def clear_canonical_flags(conn: sqlite3.Connection, tax_year: int | None = None) -> None:
    if tax_year is None:
        conn.execute("UPDATE account_year_facts SET is_canonical = 0")
    else:
        conn.execute("UPDATE account_year_facts SET is_canonical = 0 WHERE tax_year = ?", (tax_year,))


def canonical_facts(conn: sqlite3.Connection, year: int) -> list[FactRecord]:
    rows = conn.execute(
        "SELECT * FROM account_year_facts WHERE tax_year = ? AND is_canonical = 1", (year,)
    ).fetchall()
    return [fact_from_row(row) for row in rows]


def canonical_years(conn: sqlite3.Connection) -> set[int]:
    return {row[0] for row in conn.execute(
        "SELECT DISTINCT tax_year FROM account_year_facts WHERE is_canonical = 1"
    ) if row[0] is not None}


def canonical_facts_with_documents(conn: sqlite3.Connection, year: int) -> list[FactRecord]:
    rows = conn.execute(
        """
        SELECT f.*, d.first_seen_path, d.doc_type, d.parse_status, d.processing_profile
        FROM account_year_facts AS f
        JOIN documents AS d ON d.content_sha256 = f.document_sha256
        WHERE f.tax_year = ? AND f.is_canonical = 1
        ORDER BY f.id
        """,
        (year,),
    ).fetchall()
    return [fact_from_row(row) for row in rows]
