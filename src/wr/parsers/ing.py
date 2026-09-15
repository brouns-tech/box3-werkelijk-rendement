from __future__ import annotations

import re

from wr.classify import guess_tax_year
from wr.models import AccountYearFact, ParseResult
from wr.pdf import normalize_iban, parse_nl_amount


def parse_ing(text: str, tax_year: int | None = None) -> ParseResult:
    year = tax_year or guess_tax_year(text)
    facts: list[AccountYearFact] = []
    if year is None:
        return ParseResult("ing", "jaaroverzicht", None, notes=["no year"])

    # Blocks like:
    # ING Oranje Spaarrekening: A 969-47927 Hr A EXAMPLE*
    # Saldo op 01-01-2023                                                                                                                     5.000,00
    # Saldo op 31-12-2023                                                                                                                         0,00
    # Rente, ontvangen in 2023                                                                                                                   29,65
    pattern = re.compile(
        r"(ING [^\n:]+):\s*([^\n]+)\n"
        r"Saldo op 01-01-(?P<y1>\d{4})\s+(?P<start>[\d.]+,\d{2}|\-[\d.]+,\d{2})\n"
        r"Saldo op 31-12-(?P<y2>\d{4})\s+(?P<end>[\d.]+,\d{2}|\-[\d.]+,\d{2})"
        r"(?:\nRente, (?P<interest_kind>ontvangen|betaald) in \d{4}\s+"
        r"(?P<interest>[\d.]+,\d{2}))?",
        re.M,
    )

    for m in pattern.finditer(text):
        label = m.group(1).strip()
        acct_raw = m.group(2).strip().rstrip("*").strip()
        start = parse_nl_amount(m.group("start"))
        end = parse_nl_amount(m.group("end"))
        interest_kind = m.group("interest_kind")
        interest = parse_nl_amount(m.group("interest")) if m.group("interest") else None
        paid = None
        interest_source = None
        if interest_kind == "betaald":
            paid = interest
            interest = None
            interest_source = "reported_paid"
        elif interest_kind == "ontvangen":
            interest_source = "reported_received"
        elif label.casefold() == "ing betaalrekening":
            # ING annual overviews omit the interest row for payment accounts
            # when no interest was received. The complete account block and
            # balances make this a documented zero rather than missing data.
            interest = 0.0
            interest_source = "inferred_zero_from_annual_overview"

        account_key = _ing_account_key(acct_raw)
        fact = AccountYearFact(
            tax_year=year,
            issuer="ing",
            account_key=account_key,
            account_label=f"{label} {acct_raw}",
            holder_names=_holders(text),
            start_balance=start,
            end_balance=end,
            interest_received=interest,
            interest_paid=paid,
            deposits=None,
            withdrawals=None,
            extra={"interest_source": interest_source} if interest_source else {},
        )
        fact.compute_capital_gain()
        facts.append(fact)

    return ParseResult("ing", "jaaroverzicht", year, facts=facts)


def _ing_account_key(raw: str) -> str:
    # NL06 INGB 0008 6797 63 or A 969-47927
    iban_m = re.search(r"(NL\d{2}\s*INGB\s*[\d\s]+)", raw, re.I)
    if iban_m:
        return normalize_iban(iban_m.group(1))
    code = re.sub(r"\s+", " ", raw)
    code = re.sub(r"\s+Hr.*$", "", code)
    return re.sub(r"[^A-Za-z0-9\-]", "", code).upper() or raw


def _holders(text: str) -> list[str]:
    m = re.search(r"Hr\s+([A-Za-z\. ]+EXAMPLE)", text)
    if m:
        return [m.group(1).strip()]
    return []
