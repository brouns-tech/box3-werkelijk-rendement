from __future__ import annotations

import re
from datetime import date
from decimal import Decimal

from wr.models import AccountYearFact, ParseResult
from wr.money import subtract, total
from wr.parsers.base import (
    ClassificationRule,
    InstitutionPlugin,
    ParserRegistration,
    doc_type_parser,
)
from wr.parsers.common import resolve_tax_year
from wr.pdf import normalize_account_id, normalize_iban, parse_en_amount, parse_nl_amount


def _is_annual_summary(text: str) -> bool:
    return (
        "revolut" in text
        and bool(re.search(r"annual financial summary\s+20\d{2}", text))
        and "account number" in text
    )


def _is_savings_statement(text: str) -> bool:
    return (
        "revolut" in text
        and bool(re.search(r"period jan 1, (20\d{2})\s*-\s*dec 31, \1", text))
        and "account number" in text
        and "flexible cash funds" in text
        and "total earned return" in text
    )


def _is_account_statement(text: str) -> bool:
    return (
        "revolut" in text
        and "account (current account)" in text
        and bool(re.search(r"\b(?:eur|usd|gbp) statement\b", text))
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
    notes: list[str] = []
    # A combined PDF has a new statement heading for each fund overview.
    sections = re.split(
        r"(?=^[ \t]*Flexible Cash Funds Statement[ \t]*$)", text, flags=re.I | re.M
    )
    for section in sections:
        if "Opening Balance" not in section:
            continue
        period = re.search(r"Period Jan 1, (20\d{2})\s*-\s*Dec 31, \1", section, re.I)
        if not period or int(period.group(1)) != year:
            notes.append("Flexible Cash Funds overview does not cover the requested full year")
            continue
        closing = re.search(r"^Closing Balance[^\n]*", section, re.I | re.M)
        if not closing:
            notes.append("Flexible Cash Funds overview has no closing balance")
            continue
        overview = section[:closing.end()]
        portfolio = re.search(r"Portfolio Number[ \t]+([0-9a-f-]{20,})", overview, re.I)
        identifiers = re.findall(
            r"\b(?:[0-9a-f]{32}|[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12})\b",
            overview, re.I,
        )
        portfolio_number = normalize_account_id(portfolio.group(1)) if portfolio else None
        account_numbers = sorted({
            normalize_account_id(n) for n in identifiers
            if normalize_account_id(n) != portfolio_number
        })
        # Older overviews provide a single account UUID, newer ones a portfolio
        # UUID and several underlying fund accounts. Never repeat aggregate totals
        # once per underlying account.
        identity = portfolio_number or (account_numbers[0] if len(account_numbers) == 1 else None)
        header = overview.split("Opening Balance", 1)[0]
        currencies = re.findall(r"Value,[ \t]*(EUR|USD|GBP)\b", header, re.I)
        currencies = [c.upper() for c in currencies]
        if not identity or currencies not in (["EUR"], ["USD", "EUR"], ["GBP", "EUR"]):
            notes.append("Flexible Cash Funds overview lacks identity or supported EUR columns")
            continue
        fund_currency = currencies[0]
        labels = {
            "opening": "Opening Balance", "closing": "Closing Balance",
            "purchased": "Total Value purchased", "sold": "Total Value sold",
            "earned": "Total Earned Return", "fees": "Total Fees",
            "withdrawn_return": "Total Withdrawn Return",
            "reinvested_return": "Total Reinvested Return",
        }
        values: dict[str, list[Decimal] | None] = {}
        token = r"(?:-?(?:\d{1,3}(?:,\d{3})+|\d+)\.\d{2,4}|-)"
        for key, label in labels.items():
            row = re.search(
                rf"^{label}[ \t]+({token}(?:[ \t]+{token})*)[ \t]*$",
                overview, re.I | re.M,
            )
            raw = row.group(1).split() if row else []
            values[key] = (
                [Decimal(v.replace(",", "")) if v != "-" else Decimal(0) for v in raw]
                if len(raw) == len(currencies) else None
            )
        eur = {key: row[-1] if row is not None else None for key, row in values.items()}
        complete = all(row is not None for row in values.values())
        actual_return = None
        fx_gain = None
        # Reconcile in the fund currency first. Purchases include reinvested
        # returns; withdrawn/reinvested return rows are negative transfers.
        if complete:
            native = {key: row[0] for key, row in values.items()}
            expected = (
                native["opening"] + native["purchased"] + native["sold"]
                + native["earned"] + native["fees"]
                + native["withdrawn_return"] + native["reinvested_return"]
            )
            complete = abs(expected - native["closing"]) <= Decimal("0.02")
            complete = complete and all(
                summary[k] <= 0
                for summary in (native, eur)
                for k in ("sold", "fees", "withdrawn_return", "reinvested_return")
            ) and native["purchased"] >= 0 and eur["purchased"] >= 0
            if complete:
                # EUR value change plus external payouts, adding back separately
                # charged (non-deductible) service fees. This includes FX changes.
                actual_return = (
                    eur["closing"] - eur["opening"] - eur["purchased"]
                    - eur["sold"] - eur["withdrawn_return"]
                    - eur["reinvested_return"] - eur["fees"]
                )
                fx_gain = actual_return - eur["earned"]
        if not complete:
            notes.append(f"Flexible Cash Funds {fund_currency} overview is incomplete or does not reconcile")
        holders = _holders(section)
        facts.append(AccountYearFact(
            tax_year=year, issuer="revolut",
            account_key=f"{identity}:fund:{fund_currency.lower()}",
            account_label=f"Revolut Flexible Cash Funds ({fund_currency})",
            holder_names=holders, ownership="individual" if len(holders) == 1 else "unknown",
            currency="EUR", start_balance=float(eur["opening"]) if eur["opening"] is not None else None,
            end_balance=float(eur["closing"]) if eur["closing"] is not None else None,
            deposits=float(eur["purchased"] + eur["reinvested_return"]) if complete else None,
            withdrawals=float(-eur["sold"] - eur["withdrawn_return"]) if complete else None,
            capital_gain=float(actual_return) if actual_return is not None else None,
            gain_method="earned_return" if actual_return is not None else "unknown",
            extra={
                "portfolio_number": portfolio_number, "account_numbers": account_numbers,
                "fund_currency": fund_currency, "summary_currencies": currencies,
                "summary": {
                    key: [float(v) for v in row] if row is not None else None
                    for key, row in values.items()
                },
                "earned_return": float(eur["earned"]) if eur["earned"] is not None else None,
                "fees": float(eur["fees"]) if eur["fees"] is not None else None,
                "net_earned_return": (
                    float(eur["earned"] + eur["fees"])
                    if eur["earned"] is not None and eur["fees"] is not None else None
                ),
                "fx_gain": float(fx_gain) if fx_gain is not None else None,
                "return_source": "eur_summary_reconciliation" if complete else "incomplete_summary",
                "fees_treatment": "non_deductible_service_fees",
            },
        ))
    return ParseResult("revolut", "savings_statement", year, facts=facts, notes=notes)


def _usd_cash_evidence(body: str, year: int, opening: float, closing: float,
                       incoming: float, outgoing: float) -> dict:
    """Retain dated cash flows only when every transaction reconciles."""
    months = {name: index for index, name in enumerate(
        ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"), 1)}
    transactions = []
    balance = Decimal(str(opening))
    money_in = money_out = Decimal(0)
    last_day = date(year, 1, 1)
    for line in body.splitlines():
        match = re.match(r"^\s*([A-Z][a-z]{2})\s+(\d{1,2}),\s+(20\d{2})\s+(.*)", line)
        if not match:
            continue
        try:
            day = date(int(match[3]), months[match[1]], int(match[2]))
        except (KeyError, ValueError):
            return {"reconciled": False, "reason": "invalid transaction date"}
        values = re.findall(r"\$\s*(-?[\d,]+\.\d{2})", match[4])
        if day.year != year or day < last_day or len(values) != 2:
            return {"reconciled": False, "reason": "unsupported transaction row"}
        value, after = (Decimal(v.replace(",", "")) for v in values)
        delta = after - balance
        if value <= 0 or abs(delta) != value:
            return {"reconciled": False, "reason": "transaction balance mismatch"}
        is_interest = bool(re.search(r"Net Interest Paid to", match[4], re.I))
        if re.search(r"interest", match[4], re.I) and not is_interest:
            return {"reconciled": False, "reason": "unsupported interest transaction"}
        direction = "in" if delta > 0 else "out"
        if is_interest and direction != "in":
            return {"reconciled": False, "reason": "unexpected debit interest"}
        transactions.append({"date": day.isoformat(), "amount": str(value),
                             "direction": direction, "kind": "interest" if is_interest else "transfer"})
        if delta > 0:
            money_in += value
        else:
            money_out += value
        last_day, balance = day, after
    reconciled = (balance == Decimal(str(closing)) and money_in == Decimal(str(incoming))
                  and money_out == Decimal(str(outgoing)))
    return {"reconciled": reconciled, "transactions": transactions}


def _parse_account_statement(text: str, year: int) -> ParseResult:
    # Partial statements — extract opening/closing if present; often incomplete for Box 3.
    facts: list[AccountYearFact] = []
    iban_m = re.search(r"(NL\d{2}REVO\d+)", text, re.I)
    account_key = normalize_iban(iban_m.group(1)) if iban_m else f"revolut-stmt-{year}"
    currency_match = re.search(r"^\s*(EUR|USD|GBP) Statement\s*$", text, re.I | re.M)
    currency = currency_match.group(1).upper() if currency_match else "EUR"
    if currency != "EUR":
        account_key = f"{account_key}:{currency}"

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
            gain_method="interest_only" if interest is not None else "unknown",
            capital_gain=interest,
            extra={"product": product, "money_in_includes_interest": incoming,
                   "interest_source": "net_interest_transactions" if credits else "no_interest_transactions",
                   "interest_credit_count": len(credits),
                   "fx_status": "requires_eur_conversion" if currency != "EUR" else "not_required"},
        )
        if currency == "USD":
            evidence = _usd_cash_evidence(body, year, fact.start_balance, fact.end_balance,
                                          incoming, fact.withdrawals)
            # The transaction heading establishes the full-year section, even
            # for an unused account whose zero summary has no transaction rows.
            evidence["reconciled"] = bool(section) and evidence["reconciled"]
            fact.extra["fx_evidence"] = evidence
            if evidence["reconciled"]:
                fact.interest_received = total(
                    item["amount"] for item in evidence["transactions"] if item["kind"] == "interest")
                fact.deposits = subtract(incoming, fact.interest_received)
                fact.capital_gain = fact.interest_received
                fact.gain_method = "interest_only"
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
    # Fund overviews place the holder immediately after the generation date.
    fund_holder = re.search(r"Generation date:[^\n]*\n([^\n]+)", text, re.I)
    if fund_holder and re.fullmatch(r"[A-ZÀ-Ÿ][A-ZÀ-Ÿ \'’.-]+", fund_holder.group(1).strip()):
        return [fund_holder.group(1).strip()]
    # Personal account statements print the holder immediately after the bank.
    holder = re.search(r"Revolut Bank UAB[^\n]*\n([^\n]+)", text)
    if holder and re.fullmatch(r"[A-ZÀ-Ÿ][A-ZÀ-Ÿ \'’.-]+", holder.group(1).strip()):
        return [holder.group(1).strip()]
    return []


PLUGIN = InstitutionPlugin(
    issuer="revolut",
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
