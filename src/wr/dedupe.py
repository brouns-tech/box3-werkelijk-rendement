from __future__ import annotations

import json
import sqlite3
from collections import defaultdict

from wr.parsers import canonical_priority, postprocess_facts
from wr.parsers.base import InstitutionOptions


def canonicalize_facts(
    conn: sqlite3.Connection,
    institution_options: InstitutionOptions | None = None,
) -> None:
    """Mark one canonical fact per issuer, normalized account key, and tax year."""
    _enrich_fact_holders(conn)
    conn.execute("UPDATE account_year_facts SET is_canonical = 0")

    rows = conn.execute(
        """
        SELECT f.id, f.tax_year, f.issuer, f.account_key, f.logical_group,
               f.start_balance, f.end_balance, f.deposits, f.withdrawals,
               f.interest_received, f.dividends_gross, f.capital_gain, f.gain_method,
               d.doc_type
        FROM account_year_facts f
        JOIN documents d ON d.content_sha256 = f.document_sha256
        WHERE d.parse_status = 'parsed'
        """
    ).fetchall()

    groups: dict[tuple[int, str], list] = defaultdict(list)
    for r in rows:
        key = _logical_key(r["tax_year"], r["issuer"], r["account_key"], r["logical_group"])
        groups[key].append(r)

    canonical_ids: list[int] = []
    for _key, items in groups.items():
        best = max(items, key=lambda r: _score(r))
        canonical_ids.append(best["id"])

    for fid in canonical_ids:
        conn.execute("UPDATE account_year_facts SET is_canonical = 1 WHERE id = ?", (fid,))
    postprocess_facts(conn, institution_options)
    conn.commit()


def _enrich_fact_holders(conn: sqlite3.Connection) -> None:
    rows = conn.execute(
        "SELECT id, issuer, account_key, holder_names, ownership FROM account_year_facts"
    ).fetchall()
    by_account: dict[tuple[str, str], set[str]] = defaultdict(set)
    by_issuer: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        holders = _holders(row["holder_names"])
        if not holders:
            continue
        if row["ownership"] == "unknown":
            conn.execute(
                "UPDATE account_year_facts SET ownership = ? WHERE id = ?",
                ("individual" if len(holders) == 1 else "joint", row["id"]),
            )
        by_account[(row["issuer"], _account_family(row["account_key"]))].update(holders)
        by_issuer[row["issuer"]].update(holders)
    for row in rows:
        if _holders(row["holder_names"]):
            continue
        holders = by_account[(row["issuer"], _account_family(row["account_key"]))]
        if not holders:
            holders = by_issuer[row["issuer"]]
        if len(holders) == 1:
            conn.execute(
                "UPDATE account_year_facts SET holder_names = ?, ownership = 'individual' WHERE id = ?",
                (json.dumps(sorted(holders)), row["id"]),
            )
        elif len(holders) == 2:
            conn.execute(
                "UPDATE account_year_facts SET holder_names = ?, ownership = 'joint' WHERE id = ?",
                (json.dumps(sorted(holders)), row["id"]),
            )


def _holders(value: str | None) -> list[str]:
    try:
        return json.loads(value or "[]")
    except json.JSONDecodeError:
        return []


def _account_family(account_key: str) -> str:
    return account_key.split(":", 1)[0]


def _logical_key(year: int, issuer: str, account_key: str, logical_group: str | None) -> tuple[int, str]:
    acct = (account_key or "").lower().replace(" ", "")
    return year, f"{issuer}:{acct}"


def _score(row) -> tuple:
    doc_type = row["doc_type"] or ""
    prio = canonical_priority(row["issuer"], doc_type)
    completeness = sum(
        1
        for v in (
            row["start_balance"],
            row["end_balance"],
            row["interest_received"],
            row["dividends_gross"],
            row["deposits"],
            row["capital_gain"],
        )
        if v is not None
    )
    return (prio, completeness, -row["id"])
