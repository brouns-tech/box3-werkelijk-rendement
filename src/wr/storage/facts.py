from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict
from typing import Iterable
import json
import sqlite3

from wr.models import AccountYearFact
from wr.models.storage import FactRecord, FactWriteRecord
from wr.storage.adapters import fact_from_row
from wr.storage.reconciliation import invalidate_reconciliation


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
                logical_group, extra
            ) VALUES (
                :document_sha256, :tax_year, :issuer, :account_key, :account_label,
                :holder_names, :ownership, :currency, :start_balance, :end_balance,
                :deposits, :withdrawals, :interest_received, :interest_paid,
                :dividends_gross, :withholding_tax, :capital_gain, :gain_method,
                :logical_group, :extra
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
        invalidate_reconciliation(conn)
