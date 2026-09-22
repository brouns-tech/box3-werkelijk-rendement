from __future__ import annotations

import json
import sqlite3
from collections import defaultdict

from wr.money import add, subtract, total
from wr.parsers import canonical_priority


def canonicalize_facts(
    conn: sqlite3.Connection, flatex_linked_account: str | None = None
) -> None:
    """Mark one canonical fact per issuer, normalized account key, and tax year."""
    _enrich_fact_holders(conn)
    _enrich_sns_account_labels(conn)
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
    _enrich_flatex_inventory_returns(conn, flatex_linked_account)
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


def _enrich_sns_account_labels(conn: sqlite3.Connection) -> None:
    rows = conn.execute(
        "SELECT id, account_key, account_label FROM account_year_facts WHERE issuer = 'sns'"
    ).fetchall()
    product_labels: dict[str, str] = {}
    for row in rows:
        label = (row["account_label"] or "").strip()
        if label.lower().startswith("sns "):
            product_labels[_account_family(row["account_key"])] = label
    for row in rows:
        product_label = product_labels.get(_account_family(row["account_key"]))
        if product_label and not (row["account_label"] or "").lower().startswith("sns "):
            conn.execute(
                "UPDATE account_year_facts SET account_label = ? WHERE id = ?",
                (product_label, row["id"]),
            )


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


def _enrich_flatex_inventory_returns(
    conn: sqlite3.Connection, linked_account: str | None
) -> None:
    conn.execute(
        """
        UPDATE account_year_facts
        SET capital_gain = NULL, gain_method = 'unknown'
        WHERE issuer = 'flatex'
          AND id IN (
              SELECT f.id
              FROM account_year_facts f
              JOIN documents d ON d.content_sha256 = f.document_sha256
              WHERE d.doc_type = 'account_statement' AND f.gain_method = 'balance_flow'
          )
        """
    )
    _select_flatex_statement_canonicals(conn)
    inventories = conn.execute(
        """
        SELECT f.*
        FROM account_year_facts f
        JOIN documents d ON d.content_sha256 = f.document_sha256
        WHERE f.issuer = 'flatex'
          AND f.is_canonical = 1
          AND d.doc_type = 'financial_instruments_statement'
        ORDER BY f.account_key, f.tax_year
        """
    ).fetchall()
    inventory_by_year = {
        (row["account_key"], row["tax_year"]): row for row in inventories
    }

    for inventory in inventories:
        account_key = inventory["account_key"]
        tax_year = inventory["tax_year"]
        flows = conn.execute(
            """
            SELECT start_balance, deposits, withdrawals, extra
            FROM account_year_facts f
            JOIN documents d ON d.content_sha256 = f.document_sha256
            WHERE f.issuer = 'flatex'
              AND f.account_key = ?
              AND f.tax_year = ?
              AND d.doc_type = 'account_statement'
            """,
            (account_key, tax_year),
        ).fetchall()
        if not flows:
            continue

        deposits = total(row["deposits"] or 0.0 for row in flows)
        withdrawals = total(row["withdrawals"] or 0.0 for row in flows)
        previous = inventory_by_year.get((account_key, tax_year - 1))
        start_balance = previous["end_balance"] if previous else _opening_balance(flows)
        if start_balance is None:
            continue

        end_balance = inventory["end_balance"]
        capital_gain = add(subtract(end_balance, start_balance, deposits), withdrawals)
        extra = json.loads(inventory["extra"] or "{}")
        previous_extra = json.loads(previous["extra"] or "{}") if previous else {}
        start_securities_value = previous_extra.get("securities_market_value")
        end_securities_value = extra.get("securities_market_value")
        extra["portfolio_return_basis"] = (
            "year-end securities-and-cash valuation adjusted only for external transfers"
        )
        extra["securities_market_value_start"] = start_securities_value
        extra["securities_market_value_end"] = end_securities_value
        if start_securities_value is not None and end_securities_value is not None:
            extra["securities_market_value_change"] = subtract(
                end_securities_value, start_securities_value
            )
        extra["return_derived_from"] = {
            "opening_balance": "prior_31_december_inventory" if previous else "opening_account_statement",
            "external_flow_documents": len(flows),
            "linked_account": linked_account,
        }
        conn.execute(
            """
            UPDATE account_year_facts
            SET start_balance = ?, deposits = ?, withdrawals = ?,
                capital_gain = ?, gain_method = 'balance_flow', extra = ?
            WHERE id = ?
            """,
            (
                start_balance,
                deposits,
                withdrawals,
                capital_gain,
                json.dumps(extra),
                inventory["id"],
            ),
        )



def _select_flatex_statement_canonicals(conn: sqlite3.Connection) -> None:
    rows = conn.execute(
        """
        SELECT f.id, f.tax_year, f.account_key, f.extra
        FROM account_year_facts f
        JOIN documents d ON d.content_sha256 = f.document_sha256
        WHERE f.issuer = 'flatex' AND d.doc_type = 'account_statement'
        ORDER BY f.tax_year, f.account_key
        """
    ).fetchall()
    groups: dict[tuple[int, str], list] = defaultdict(list)
    for row in rows:
        groups[(row["tax_year"], row["account_key"])].append(row)

    for (tax_year, account_key), statements in groups.items():
        has_inventory = conn.execute(
            """
            SELECT 1
            FROM account_year_facts f
            JOIN documents d ON d.content_sha256 = f.document_sha256
            WHERE f.issuer = 'flatex' AND f.tax_year = ? AND f.account_key = ?
              AND d.doc_type = 'financial_instruments_statement'
            """,
            (tax_year, account_key),
        ).fetchone()
        if has_inventory:
            continue
        selected = max(statements, key=_statement_number)
        conn.execute(
            """
            UPDATE account_year_facts SET is_canonical = 0
            WHERE issuer = 'flatex' AND tax_year = ? AND account_key = ?
            """,
            (tax_year, account_key),
        )
        conn.execute(
            "UPDATE account_year_facts SET is_canonical = 1 WHERE id = ?",
            (selected["id"],),
        )


def _enrich_flatex_statement_returns(conn, inventories, linked_account: str | None) -> None:
    inventory_keys = set(inventories)
    rows = conn.execute(
        """
        SELECT f.*
        FROM account_year_facts f
        JOIN documents d ON d.content_sha256 = f.document_sha256
        WHERE f.issuer = 'flatex' AND d.doc_type = 'account_statement'
        ORDER BY f.account_key, f.tax_year
        """
    ).fetchall()
    groups: dict[tuple[str, int], list] = defaultdict(list)
    for row in rows:
        groups[(row["account_key"], row["tax_year"])].append(row)

    closing_by_year: dict[tuple[str, int], float] = {
        key: row["end_balance"] for key, row in inventories.items()
    }
    for (account_key, tax_year), statements in groups.items():
        selected = max(statements, key=_statement_number)
        if selected["end_balance"] is not None:
            closing_by_year[(account_key, tax_year)] = selected["end_balance"]
        if (account_key, tax_year) in inventory_keys:
            continue

        start_balance = closing_by_year.get((account_key, tax_year - 1))
        if start_balance is None:
            start_balance = _opening_balance(statements)
        end_balance = selected["end_balance"]
        if start_balance is None or end_balance is None:
            continue

        deposits = total(row["deposits"] or 0.0 for row in statements)
        withdrawals = total(row["withdrawals"] or 0.0 for row in statements)
        capital_gain = add(subtract(end_balance, start_balance, deposits), withdrawals)
        extra = json.loads(selected["extra"] or "{}")
        extra["return_derived_from"] = {
            "opening_balance": "prior_31_december_balance"
            if (account_key, tax_year - 1) in closing_by_year
            else "opening_account_statement",
            "flow_documents": len(statements),
            "linked_account": linked_account,
        }
        conn.execute(
            """
            UPDATE account_year_facts
            SET start_balance = ?, deposits = ?, withdrawals = ?,
                capital_gain = ?, gain_method = 'balance_flow', extra = ?
            WHERE id = ?
            """,
            (
                start_balance,
                deposits,
                withdrawals,
                capital_gain,
                json.dumps(extra),
                selected["id"],
            ),
        )


def _statement_number(row) -> int:
    extra = json.loads(row["extra"] or "{}")
    return int(extra.get("statement_number", 0))


def _opening_balance(flows) -> float | None:
    opening_balances = []
    for flow in flows:
        extra = json.loads(flow["extra"] or "{}")
        if extra.get("opening_statement") and flow["start_balance"] is not None:
            opening_balances.append(flow["start_balance"])
    if len(opening_balances) == 1:
        return opening_balances[0]
    return None
