from __future__ import annotations

import re

from wr.models import AccountYearFact, ParseResult
from wr.parsers.base import (
    ClassificationRule,
    InstitutionPlugin,
    ParserRegistration,
    simple_parser,
)
from wr.parsers.common import first_holder, resolve_tax_year
from wr.pdf import normalize_iban, parse_nl_amount


def _is_supported_document(text: str) -> bool:
    return (
        "ing" in text
        and bool(re.search(r"jaaroverzicht\s+20\d{2}", text))
        and "saldo op 01-01" in text
        and "saldo op 31-12" in text
        and any(
            marker in text
            for marker in ("ing betaalrekening", "ing oranje spaarrekening", "creditcards")
        )
    )


def parse_ing(text: str, tax_year: int | None = None) -> ParseResult:
    year = resolve_tax_year(text, tax_year)
    facts: list[AccountYearFact] = []
    if year is None:
        return ParseResult("ing", "jaaroverzicht", None, notes=["no year"])

    # Blocks list one product, account identifier, balances, and optional interest.
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
        if any(
            product in label.casefold()
            for product in ("betaalrekening", "creditcardrekening")
        ):
            fact.capital_gain = 0.0
            fact.gain_method = "explicit"
            fact.extra = {"return_assumption": "zero_by_product"}
        fact.compute_capital_gain()
        facts.append(fact)

    return ParseResult("ing", "jaaroverzicht", year, facts=facts)


def _ing_account_key(raw: str) -> str:
    iban_m = re.search(r"(NL\d{2}\s*INGB\s*[\d\s]+)", raw, re.I)
    if iban_m:
        return normalize_iban(iban_m.group(1))
    code = re.sub(r"\s+", " ", raw)
    code = re.sub(r"\s+Hr.*$", "", code)
    return re.sub(r"[^A-Za-z0-9\-]", "", code).upper() or raw


def _holders(text: str) -> list[str]:
    return first_holder(text, r"(?:Hr|Mevr\.)\s+([^\n*]+)")


PLUGIN = InstitutionPlugin(
    issuer="ing",
    classification_rules=(
        ClassificationRule("ing", "jaaroverzicht", _is_supported_document),
    ),
    parsers={
        "jaaroverzicht": ParserRegistration(simple_parser(parse_ing), 90),
    },
)
