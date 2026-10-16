from __future__ import annotations

import json
import sqlite3

from wr.models.reconciliation import ReconciledFact
from wr.reconciliation.engine import account_key
from wr.models.storage import FactRecord
from wr.storage.adapters import fact_from_row


def source_observations(conn: sqlite3.Connection, year: int | None = None) -> list[FactRecord]:
    rows = conn.execute(
        """SELECT f.*, d.first_seen_path, d.doc_type, d.parse_status, d.processing_profile
           FROM account_year_facts f JOIN documents d ON d.content_sha256 = f.document_sha256
           WHERE d.parse_status = 'parsed' AND d.observations_version = 1
             AND (? IS NULL OR f.tax_year = ?)
           ORDER BY f.issuer, f.tax_year, f.account_key, f.document_sha256, f.id""",
        (year, year),
    ).fetchall()
    return [fact_from_row(row) for row in rows]


def replace_reconciled_facts(conn: sqlite3.Connection, facts: list[ReconciledFact]) -> None:
    keys = {(fact.tax_year, fact.issuer, account_key(fact.account_key)) for fact in facts}
    for row in conn.execute("SELECT id, tax_year, issuer, normalized_account_key FROM reconciled_facts").fetchall():
        if (row[1], row[2], row[3]) not in keys:
            conn.execute("DELETE FROM reconciled_facts WHERE id = ?", (row[0],))
    for fact in facts:
        conn.execute(
            """INSERT INTO reconciled_facts (tax_year, issuer, normalized_account_key, payload)
               VALUES (?, ?, ?, ?) ON CONFLICT(tax_year, issuer, normalized_account_key)
               DO UPDATE SET payload = excluded.payload""",
            (fact.tax_year, fact.issuer, account_key(fact.account_key), fact.model_dump_json(exclude={"id"})),
        )


def reconciled_facts(conn: sqlite3.Connection, year: int) -> list[ReconciledFact]:
    rows = conn.execute(
        "SELECT id, payload FROM reconciled_facts WHERE tax_year = ? ORDER BY issuer, normalized_account_key", (year,),
    ).fetchall()
    return [fact_from_row({**json.loads(row[1]), "id": row[0]}, ReconciledFact) for row in rows]


def reconciled_years(conn: sqlite3.Connection) -> set[int]:
    return {row[0] for row in conn.execute("SELECT DISTINCT tax_year FROM reconciled_facts")}


def invalidate_reconciliation(conn: sqlite3.Connection) -> None:
    conn.execute("DELETE FROM reconciled_facts")
    conn.execute("DELETE FROM yearly_portfolio")
    conn.execute("DELETE FROM taxpayer_tax_results")
