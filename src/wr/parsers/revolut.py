from __future__ import annotations

import re

from wr.models import AccountYearFact, GainMethod, ParseResult
from wr.models.metadata import FactMetadata
from wr.money import Currency, add, subtract, total
from wr.parsers._text import normalize_account_id, normalize_iban, parse_en_amount, parse_nl_amount
from wr.parsers.base import ClassificationRule, InstitutionPlugin, ParserRegistration, doc_type_parser
from wr.parsers.common import resolve_tax_year


_CURRENCY_PATTERN = "|".join(currency.value for currency in Currency)


class RevolutMetadata(FactMetadata):
    fees: float | None = None
    earned_return: float | None = None
    product: str | None = None
    money_in_includes_interest: float | None = None
    interest_credit_count: int | None = None
    fx_status: str | None = None


def _is_annual_summary(text: str) -> bool:
    return (
        "revolut" in text
        and bool(re.search(r"annual financial summary\s+20\d{2}", text))
        and "account number" in text
    )


def _is_savings_statement(text: str) -> bool:
    return (
        "revolut" in text
        and "period jan 1" in text
        and "dec 31" in text
        and "account number" in text
        and "flexible cash funds" in text
        and "total earned return" in text
    )


def _is_account_statement(text: str) -> bool:
    return (
        "revolut" in text
        and "account (current account)" in text
        and bool(re.search(rf"\b(?:{_CURRENCY_PATTERN}) statement\b", text, re.I))
        and bool(
            re.search(
                r"(?:transactions|period)\s+from\s+january\s+1.*december\s+31",
                text,
                re.S,
            )
        )
    )


def _is_business_statement(text: str) -> bool:
    return (
        "revolut business" in text
        and "account statement" in text
        and "balance summary" in text
    )


def parse_revolut(text: str, tax_year: int | None, doc_type: str) -> ParseResult:
    year = resolve_tax_year(text, tax_year)
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
        capital_gain=add(earned or 0.0, fees or 0.0) if earned is not None else None,
        gain_method=GainMethod.EARNED_RETURN if earned is not None else GainMethod.UNKNOWN,
        extra=RevolutMetadata(fees=fees, earned_return=earned),
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
    currency_match = re.search(rf"^\s*({_CURRENCY_PATTERN}) Statement\s*$", text, re.I | re.M)
    currency = Currency(currency_match.group(1).upper()) if currency_match else Currency.EUR
    if currency != Currency.EUR:
        account_key = f"{account_key}:{currency.value}"

    # A statement contains distinct products. "Money in" includes interest,
    # so it must not be copied wholesale into external deposits.
    amount = r"[€$£]?\s*(-?[\d,]+\.\d{2})"
    summary_rows = re.finditer(
        rf"^(Account \(Current Account\)|Deposit)[ \t]+{amount}\s+{amount}\s+{amount}\s+{amount}",
        text, re.I | re.M,
    )
    for row in summary_rows:
        product = "deposit" if row.group(1).lower() == "deposit" else "current"
        section_name = "Deposit" if product == "deposit" else "Account"
        section = re.search(rf"{section_name} transactions from[^\n]*\n(.*)", text, re.I | re.S)
        body = section.group(1) if section else ""
        if product == "current":
            body = re.split(r"Deposit transactions from", body, flags=re.I)[0]
        credits = []
        for line in body.splitlines():
            # "Paid to" is interest credited to the customer's savings product.
            if re.search(r"Net Interest Paid to", line, re.I):
                values = re.findall(r"[€$£]\s*([\d,]+\.\d{2})", line)
                if len(values) >= 2:
                    credits.append(parse_en_amount(values[0]))
        interest = total(credits) if credits else (0.0 if product == "current" and section else None)
        incoming = parse_en_amount(row.group(4))
        fact = AccountYearFact(
            tax_year=year, issuer="revolut",
            account_key=account_key + (":deposit" if product == "deposit" else ""),
            account_label="Revolut Deposit" if product == "deposit" else "Revolut Current Account",
            holder_names=_holders(text), currency=currency,
            start_balance=parse_en_amount(row.group(2)),
            end_balance=parse_en_amount(row.group(5)),
            deposits=subtract(incoming, interest or 0),
            withdrawals=parse_en_amount(row.group(3)),
            interest_received=interest,
            gain_method=GainMethod.INTEREST_ONLY if interest is not None else GainMethod.UNKNOWN,
            capital_gain=interest,
            extra=RevolutMetadata(
                product=product,
                money_in_includes_interest=incoming,
                interest_source="net_interest_transactions" if credits else "no_interest_transactions",
                interest_credit_count=len(credits),
                fx_status="requires_eur_conversion" if currency != Currency.EUR else "not_required",
            ),
        )
        # Missing deposit transactions do not prove zero savings interest.
        if product == "current" and interest is None:
            fact.compute_capital_gain()
        facts.append(fact)
    if facts:
        return ParseResult("revolut", "account_statement", year, facts=facts)

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
        currency=currency,
        start_balance=start,
        end_balance=end,
        gain_method="unknown",
    )
    facts.append(fact)
    return ParseResult("revolut", "account_statement", year, facts=facts, notes=["partial statement"])


def _holders(text: str) -> list[str]:
    first = re.search(r"First Name[ \t]+(\S+)", text)
    last = re.search(r"Last Name[ \t]+(\S+)", text)
    if first and last:
        return [f"{first.group(1)} {last.group(1)}"]
    # Personal account statements print the holder immediately after the bank.
    holder = re.search(r"Revolut Bank UAB[^\n]*\n([^\n]+)", text)
    if holder and re.fullmatch(r"[A-ZÀ-Ÿ][A-ZÀ-Ÿ \'’.-]+", holder.group(1).strip()):
        return [holder.group(1).strip()]
    return []


PLUGIN = InstitutionPlugin(
    issuer="revolut",
    metadata_model=RevolutMetadata,
    classification_rules=(
        ClassificationRule("revolut", "jaaroverzicht", _is_annual_summary),
        ClassificationRule("revolut", "savings_statement", _is_savings_statement),
        ClassificationRule(
            "revolut", "business_account_statement", _is_business_statement, supported=False
        ),
        ClassificationRule("revolut", "account_statement", _is_account_statement),
    ),
    parsers={
        "jaaroverzicht": ParserRegistration(doc_type_parser(parse_revolut), 90),
        "savings_statement": ParserRegistration(doc_type_parser(parse_revolut), 85),
        "account_statement": ParserRegistration(doc_type_parser(parse_revolut), 20),
    },
)
