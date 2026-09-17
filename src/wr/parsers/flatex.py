from __future__ import annotations

import re

from wr.classify import guess_tax_year
from wr.models import AccountYearFact, ParseResult
from wr.pdf import parse_nl_amount
from wr.source_rules import flatex_linked_account, has_zero_return_by_product


def parse_flatex(
    text: str,
    tax_year: int | None,
    doc_type: str,
    linked_account: str | None = None,
) -> ParseResult:
    if doc_type == "financial_instruments_statement":
        return _parse_financial_instruments_statement(text)
    if doc_type == "account_statement":
        return _parse_account_statement(text, linked_account or flatex_linked_account())

    year = tax_year or guess_tax_year(text)
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
    zero_return = has_zero_return_by_product("flatex", account_label)
    fact = AccountYearFact(
        tax_year=year,
        issuer="flatex",
        account_key=account.group(1),
        account_label=account_label,
        start_balance=opening_balance if opening_statement else None,
        end_balance=end_balance,
        deposits=linked_deposits,
        withdrawals=linked_withdrawals,
        capital_gain=0.0 if zero_return else None,
        gain_method="explicit" if zero_return else "unknown",
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
