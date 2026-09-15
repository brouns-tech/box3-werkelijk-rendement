from __future__ import annotations

import re

from wr.classify import guess_tax_year
from wr.models import AccountYearFact, ParseResult
from wr.pdf import normalize_account_id, normalize_iban, parse_en_amount, parse_nl_amount


def parse_revolut(text: str, tax_year: int | None, doc_type: str) -> ParseResult:
    year = tax_year or guess_tax_year(text)
    if year is None:
        return ParseResult("revolut", doc_type, None, notes=["no year"])

    if doc_type == "jaaroverzicht":
        return _parse_annual(text, year)
    if doc_type == "savings_statement":
        return _parse_savings(text, year)
    return _parse_account_statement(text, year)


def _parse_annual(text: str, year: int) -> ParseResult:
    facts: list[AccountYearFact] = []
    # Amounts may be €451.55 / €1,000.00 with wide spacing or unicode euros.
    row = re.compile(
        r"(NL\d{2}\s*REVO\s*\d+)\s+"
        r"(?:€|EUR)?\s*([\d,]+(?:\.\d{2})?)\s+"
        r"(?:€|EUR)?\s*([\d,]+(?:\.\d{2})?)\s+"
        r"(?:€|EUR)?\s*([\d,]+(?:\.\d{2})?)\s+"
        r"(?:€|EUR)?\s*([\d,]+(?:\.\d{2})?)",
        re.I,
    )
    for m in row.finditer(text):
        fact = AccountYearFact(
            tax_year=year,
            issuer="revolut",
            account_key=normalize_iban(m.group(1)),
            account_label="Revolut Current Account",
            holder_names=_holders(text),
            start_balance=parse_en_amount(m.group(2)),
            end_balance=parse_en_amount(m.group(3)),
            interest_received=parse_en_amount(m.group(4)),
            interest_paid=parse_en_amount(m.group(5)),
        )
        fact.compute_capital_gain()
        facts.append(fact)
    if not facts:
        # Fallback: IBAN anywhere + "Balance on" table header present.
        iban_m = re.search(r"(NL\d{2}\s*REVO\s*\d+)", text, re.I)
        amts = re.findall(r"€\s*([\d,]+.\d{2})", text)
        if iban_m and len(amts) >= 2:
            fact = AccountYearFact(
                tax_year=year,
                issuer="revolut",
                account_key=normalize_iban(iban_m.group(1)),
                account_label="Revolut Current Account",
                holder_names=_holders(text),
                start_balance=parse_en_amount(amts[0]),
                end_balance=parse_en_amount(amts[1]),
                interest_received=parse_en_amount(amts[2]) if len(amts) > 2 else 0.0,
                interest_paid=parse_en_amount(amts[3]) if len(amts) > 3 else 0.0,
            )
            fact.compute_capital_gain()
            facts.append(fact)
    return ParseResult("revolut", "jaaroverzicht", year, facts=facts)


def _parse_savings(text: str, year: int) -> ParseResult:
    facts: list[AccountYearFact] = []
    acct = re.search(r"Account Number\s+([0-9a-f\-]{20,})", text, re.I)
    account_key = normalize_account_id(acct.group(1)) if acct else f"revolut-savings-{year}"

    def euro_line(label: str) -> float | None:
        # Opening Balance                    1,097.04            993.91
        m = re.search(
            rf"{re.escape(label)}\s+([\d,]+\.\d{{2}}|-)\s+([\d,]+\.\d{{2}}|-)",
            text,
            re.I,
        )
        if not m:
            return None
        # Prefer EUR column (second)
        raw = m.group(2)
        if raw == "-":
            return 0.0
        return parse_en_amount(raw)

    opening = euro_line("Opening Balance")
    closing = euro_line("Closing Balance")
    purchased = euro_line("Total Value purchased")
    sold = euro_line("Total Value sold")
    earned = euro_line("Total Earned Return")
    fees = euro_line("Total Fees")

    fact = AccountYearFact(
        tax_year=year,
        issuer="revolut",
        account_key=account_key,
        account_label="Revolut Flexible Cash Funds",
        holder_names=_holders(text),
        start_balance=opening,
        end_balance=closing,
        deposits=purchased,
        withdrawals=sold,
        capital_gain=(earned or 0.0) + (fees or 0.0) if earned is not None else None,
        gain_method="earned_return" if earned is not None else "unknown",
        extra={"fees": fees, "earned_return": earned},
    )
    if fact.capital_gain is None:
        fact.compute_capital_gain()
    facts.append(fact)
    return ParseResult("revolut", "savings_statement", year, facts=facts)


def _parse_account_statement(text: str, year: int) -> ParseResult:
    # Partial statements — extract opening/closing if present; often incomplete for Box 3.
    facts: list[AccountYearFact] = []
    iban_m = re.search(r"(NL\d{2}REVO\d+)", text, re.I)
    account_key = normalize_iban(iban_m.group(1)) if iban_m else f"revolut-stmt-{year}"
    # Try Dutch or EN balance markers
    start = None
    end = None
    m = re.search(r"Opening balance.*?€?\s*([\d.,]+)", text, re.I | re.S)
    if m:
        start = parse_en_amount(m.group(1)) or parse_nl_amount(m.group(1))
    m = re.search(r"Closing balance.*?€?\s*([\d.,]+)", text, re.I | re.S)
    if m:
        end = parse_en_amount(m.group(1)) or parse_nl_amount(m.group(1))
    fact = AccountYearFact(
        tax_year=year,
        issuer="revolut",
        account_key=account_key,
        account_label="Revolut account statement",
        start_balance=start,
        end_balance=end,
        gain_method="unknown",
    )
    facts.append(fact)
    return ParseResult("revolut", "account_statement", year, facts=facts, notes=["partial statement"])


def _holders(text: str) -> list[str]:
    first = re.search(r"First Name\s+(\S+)", text)
    last = re.search(r"Last Name\s+(\S+)", text)
    if first and last:
        return [f"{first.group(1)} {last.group(1)}"]
    m = re.search(r"^(ALEX[^\n]+EXAMPLE)", text, re.M)
    return [m.group(1).title()] if m else []
