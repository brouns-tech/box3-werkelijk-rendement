from __future__ import annotations

import sqlite3
from collections import defaultdict


# Higher = preferred when multiple facts share a logical account/year.
_ISSUER_DOC_PRIORITY = {
    ("degiro", "jaaroverzicht"): 100,
    ("raisin", "jaaroverzicht"): 90,
    ("revolut", "jaaroverzicht"): 90,
    ("revolut", "savings_statement"): 85,
    ("sns", "jaaroverzicht"): 90,
    ("ing", "jaaroverzicht"): 90,
    ("sns", "totaaloverzicht"): 50,
    ("revolut", "account_statement"): 20,
    ("flatex", "belastingcertificaat"): 10,
    ("flatex", "other"): 5,
}


def canonicalize_facts(conn: sqlite3.Connection) -> None:
    """Mark one canonical fact per (normalized account_key, tax_year), with flatex/degiro merge."""
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
    conn.commit()


def _logical_key(year: int, issuer: str, account_key: str, logical_group: str | None) -> tuple[int, str]:
    acct = (account_key or "").lower().replace(" ", "")
    if logical_group == "flatex_degiro" or issuer in {"degiro", "flatex"}:
        # Collapse flatex cash noise into degiro portfolio when account keys differ.
        # Prefer per-account when IBAN-like; else group by issuer family + year.
        if len(acct) >= 6 and not acct.startswith("flatex"):
            return year, f"flatex_degiro:{acct}"
        return year, f"flatex_degiro:portfolio:{acct or 'default'}"
    return year, f"{issuer}:{acct}"


def _score(row) -> tuple:
    doc_type = row["doc_type"] or ""
    prio = _ISSUER_DOC_PRIORITY.get((row["issuer"], doc_type), 1)
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
    # Prefer degiro over flatex always
    issuer_boost = 10 if row["issuer"] == "degiro" else 0
    return (prio + issuer_boost, completeness, -row["id"])
