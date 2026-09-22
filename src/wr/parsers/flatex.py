from __future__ import annotations

import json
import re
import sqlite3
from collections import defaultdict
from typing import Mapping

from wr.models import AccountYearFact, ParseResult
from wr.money import add, subtract, total
from wr.parsers.base import (
    ClassificationRule,
    InstitutionPlugin,
    ParserContext,
    ParserRegistration,
)
from wr.parsers.common import resolve_tax_year
from wr.pdf import normalize_iban, parse_nl_amount


def _is_tax_certificate(text: str) -> bool:
    return (
        "flatex" in text
        and "steuerbescheinigung" in text
        and "kunde:" in text
        and "kapitalerträge" in text
    )


def _is_financial_instruments_statement(text: str) -> bool:
    return (
        "flatex" in text
        and "lijst met financiële klanteninstrumenten en klantenfondsen" in text
        and "ingesloten vindt u de lijst voor 31.12." in text
        and "rekeningstand" in text
        and "effectenrekeningposities" in text
    )


def _is_account_statement(text: str) -> bool:
    return (
        "flatex" in text
        and "rekeninguittreksel nr:" in text
        and "rekeningnummer:" in text
        and "oud saldo van" in text
        and "nieuw saldo" in text
    )


def _parse_with_context(
    text: str, tax_year: int | None, context: ParserContext
) -> ParseResult:
    return parse_flatex(
        text,
        tax_year,
        context.doc_type,
        context.string_option("linked_account"),
    )


def parse_flatex(
    text: str,
    tax_year: int | None,
    doc_type: str,
    linked_account: str | None = None,
) -> ParseResult:
    if doc_type == "financial_instruments_statement":
        return _parse_financial_instruments_statement(text)
    if doc_type == "account_statement":
        normalized_account = normalize_iban(linked_account) if linked_account else None
        return _parse_account_statement(text, normalized_account)

    year = resolve_tax_year(text, tax_year)
    # Try period in Steuerbescheinigung
    if year is None:
        m = re.search(r"Zeitraum vom 01\.01\.(20\d{2}) bis 31\.12\.(20\d{2})", text)
        if m:
            year = int(m.group(1))

    if year is None:
        return ParseResult("flatex", doc_type, None, notes=["no year"])

    kunde = re.search(r"Kunde:\s*(\d+)", text)
    account_key = kunde.group(1) if kunde else f"flatex-{year}"

    # These certificates rarely give start/end portfolio for NL Box 3.
    kap = re.search(
        r"Kapitalerträge im Sinne[^\n]*\n[^\n]*?([\d.]+,\d{2})\s*EUR",
        text,
    )
    interest = parse_nl_amount(kap.group(1)) if kap else None

    fact = AccountYearFact(
        tax_year=year,
        issuer="flatex",
        account_key=account_key,
        account_label="flatex (legacy)",
        holder_names=_holder_names(text),
        interest_received=interest,
        gain_method="interest_only" if interest is not None else "unknown",
        capital_gain=interest,
    )
    return ParseResult(
        "flatex",
        doc_type,
        year,
        facts=[fact],
        notes=["flatex tax certificate"],
    )


def _parse_financial_instruments_statement(text: str) -> ParseResult:
    snapshot = re.search(
        r"Ingesloten vindt u de lijst voor\s+(31\.12\.(20\d{2}))", text, re.I
    )
    if not snapshot:
        return ParseResult(
            "flatex",
            "financial_instruments_statement",
            None,
            notes=["missing 31 December inventory date"],
        )

    year = int(snapshot.group(2))
    account = re.search(r"Rekeningnummer\s*:\s*(\d+)", text, re.I)
    depot = re.search(r"Effectenrekeningnummer\s*:\s*(\d+)", text, re.I)
    cash = _amount_after(text, r"Rekeningstand\s*:\s*")
    positions = _positions(text)
    securities_value = round(sum(position["market_value"] for position in positions), 2)

    if account is None or cash is None or not positions:
        return ParseResult(
            "flatex",
            "financial_instruments_statement",
            year,
            notes=["incomplete financial-instruments inventory"],
        )

    account_key = account.group(1)
    fact = AccountYearFact(
        tax_year=year,
        issuer="flatex",
        account_key=account_key,
        account_label=f"flatex securities portfolio (cash and custody) {account_key}",
        holder_names=_holder_names(text),
        end_balance=round(cash + securities_value, 2),
        extra={
            "inventory_date": snapshot.group(1),
            "cash_balance": cash,
            "securities_account": depot.group(1) if depot else None,
            "securities_market_value": securities_value,
            "asset_class": "securities_portfolio",
            "position_count": len(positions),
            "positions": positions,
        },
    )
    return ParseResult(
        "flatex",
        "financial_instruments_statement",
        year,
        facts=[fact],
    )


def _amount_after(text: str, label_pattern: str) -> float | None:
    m = re.search(label_pattern + r"([\d.]+,\d{2})\s*EUR", text, re.I)
    return parse_nl_amount(m.group(1)) if m else None


def _positions(text: str) -> list[dict[str, float | str]]:
    positions = []
    for match in re.finditer(
        r"^\s*([A-Z]{2}[A-Z0-9]{10})\*{0,4}\s+([\d.]+,\d{2})\s*EUR\s*$",
        text,
        re.M,
    ):
        market_value = parse_nl_amount(match.group(2))
        if market_value is not None:
            positions.append({"isin": match.group(1), "market_value": market_value})
    return positions


def _parse_account_statement(text: str, linked_account: str | None) -> ParseResult:
    statement = re.search(r"Rekeninguittreksel nr:\s*\d+/(20\d{2})", text, re.I)
    account = re.search(r"Rekeningnummer\s*:\s*(\d+)", text, re.I)
    if statement is None or account is None:
        return ParseResult(
            "flatex", "account_statement", None, notes=["missing statement year or account"]
        )

    statement_number = int(re.search(r"\d+", statement.group(0)).group(0))
    year = int(statement.group(1))
    opening = re.search(
        r"Oud saldo van\s+(\d{2}\.\d{2}\.20\d{2}).*?([\d.]+,\d{2})([+-])",
        text,
        re.I | re.S,
    )
    opening_balance = None
    opening_statement = False
    if opening:
        opening_balance = parse_nl_amount(opening.group(2))
        if opening.group(3) == "-" and opening_balance and opening_balance > 0:
            opening_balance = -opening_balance
        opening_statement = (
            statement_number == 1
            and opening.group(1).endswith(str(year))
            and opening_balance == 0.0
        )

    linked_deposits, linked_withdrawals, linked_count = _linked_account_transfers(
        text, linked_account
    )
    sweep_deposits, sweep_withdrawals, sweep_count = _cash_sweep_transfers(text)
    end_balance = _closing_balance(text)
    account_label = f"flatex cash account {account.group(1)}"
    fact = AccountYearFact(
        tax_year=year,
        issuer="flatex",
        account_key=account.group(1),
        account_label=account_label,
        holder_names=_holder_names(text),
        start_balance=opening_balance if opening_statement else None,
        end_balance=end_balance,
        deposits=linked_deposits,
        withdrawals=linked_withdrawals,
        capital_gain=0.0,
        gain_method="explicit",
        extra={
            "linked_account": linked_account,
            "statement_number": statement_number,
            "linked_transfer_count": linked_count,
            "cash_sweep_count": sweep_count,
            "cash_sweep_deposits": sweep_deposits,
            "cash_sweep_withdrawals": sweep_withdrawals,
            "opening_statement": opening_statement,
            "return_assumption": "zero_by_product",
        },
    )
    return ParseResult("flatex", "account_statement", year, facts=[fact])


def _holder_names(text: str) -> list[str]:
    match = re.search(r"(?:De heer|Mevrouw)\s*\n\s*([A-Z][A-Z .'-]{3,80})", text)
    return [match.group(1).strip()] if match else []


def _linked_account_transfers(
    text: str, linked_account: str | None
) -> tuple[float, float, int]:
    deposits = 0.0
    withdrawals = 0.0
    count = 0
    for match in re.finditer(
        r"^\s*\d{2}\.\d{2}\.\s+.*?(?:Überweisung|Overboeking)\s+"
        r"(-?[\d.]+,\d{2})([+-])\s*$",
        text,
        re.I | re.M,
    ):
        next_transaction = re.search(
            r"^\s*\d{2}\.\d{2}\.", text[match.end() :], re.M
        )
        details_end = (
            match.end() + next_transaction.start()
            if next_transaction
            else len(text)
        )
        details = text[match.end() : details_end]
        if not linked_account or linked_account not in details.replace(" ", ""):
            continue
        amount = parse_nl_amount(match.group(1))
        if amount is None:
            continue
        if match.group(2) == "-" and amount > 0:
            amount = -amount
        if amount >= 0:
            deposits += amount
        else:
            withdrawals += abs(amount)
        count += 1
    return round(deposits, 2), round(withdrawals, 2), count


def _cash_sweep_transfers(text: str) -> tuple[float, float, int]:
    deposits = 0.0
    withdrawals = 0.0
    count = 0
    for match in re.finditer(
        r"^\s*\d{2}\.\d{2}\.\s+.*?Cash Sweep\s+"
        r"(-?[\d.]+,\d{2})([+-])\s*$",
        text,
        re.I | re.M,
    ):
        amount = parse_nl_amount(match.group(1))
        if amount is None:
            continue
        if match.group(2) == "-" and amount > 0:
            amount = -amount
        if amount >= 0:
            deposits += amount
        else:
            withdrawals += abs(amount)
        count += 1
    return round(deposits, 2), round(withdrawals, 2), count


def _closing_balance(text: str) -> float | None:
    closing = re.search(
        r"Nieuw saldo\s+\d{2}\.\d{2}\.20\d{2}.*?([\d.]+,\d{2})([+-])",
        text,
        re.I | re.S,
    )
    if not closing:
        return None
    balance = parse_nl_amount(closing.group(1))
    if closing.group(2) == "-" and balance and balance > 0:
        return -balance
    return balance


def _postprocess(conn: sqlite3.Connection, options: Mapping[str, object]) -> None:
    linked_account = options.get("linked_account")
    normalized_account = (
        normalize_iban(linked_account)
        if isinstance(linked_account, str) and linked_account.strip()
        else None
    )
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
    _select_statement_canonicals(conn)
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
            "opening_balance": (
                "prior_31_december_inventory" if previous else "opening_account_statement"
            ),
            "external_flow_documents": len(flows),
            "linked_account": normalized_account,
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


def _select_statement_canonicals(conn: sqlite3.Connection) -> None:
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


def _statement_number(row) -> int:
    extra = json.loads(row["extra"] or "{}")
    return int(extra.get("statement_number", 0))


def _opening_balance(flows) -> float | None:
    opening_balances = []
    for flow in flows:
        extra = json.loads(flow["extra"] or "{}")
        if extra.get("opening_statement") and flow["start_balance"] is not None:
            opening_balances.append(flow["start_balance"])
    return opening_balances[0] if len(opening_balances) == 1 else None


PLUGIN = InstitutionPlugin(
    issuer="flatex",
    classification_rules=(
        ClassificationRule("flatex", "belastingcertificaat", _is_tax_certificate),
        ClassificationRule(
            "flatex",
            "financial_instruments_statement",
            _is_financial_instruments_statement,
        ),
        ClassificationRule("flatex", "account_statement", _is_account_statement),
    ),
    parsers={
        "financial_instruments_statement": ParserRegistration(_parse_with_context, 100),
        "account_statement": ParserRegistration(_parse_with_context, 20),
        "belastingcertificaat": ParserRegistration(_parse_with_context, 10),
    },
    postprocess=_postprocess,
)
