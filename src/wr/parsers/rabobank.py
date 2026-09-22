from __future__ import annotations

import re

from wr.models import AccountYearFact, ParseResult
from wr.parsers.base import (
    ClassificationRule,
    InstitutionPlugin,
    ParserRegistration,
    simple_parser,
)
from wr.parsers.common import amount_after_label, first_holder, resolve_tax_year
from wr.pdf import normalize_iban


def _is_supported_document(text: str) -> bool:
    return (
        "rabobank" in text
        and "financieel jaaroverzicht" in text
        and (
            bool(re.search(r"onderwerp\s+financieel jaaroverzicht", text))
            or "hierbij ontvangt u een financieel jaaroverzicht over het afgelopen jaar" in text
            or "dit is uw financieel jaaroverzicht van het afgelopen jaar" in text
            or (
                "alstublieft, uw financieel jaaroverzicht" in text
                and "op het overzicht vindt u de gegevens van uw eigen" in text
            )
        )
        and ("saldo 01-01" in text or "sa l do 01 - 01" in text)
        and ("saldo 31-12" in text or "sa l do 31 - 12" in text)
    )


def parse_rabobank(text: str, tax_year: int | None = None) -> ParseResult:
    """Parse Rabobank Financieel Jaaroverzicht deposit-account blocks."""
    year = resolve_tax_year(text, tax_year)
    if year is None:
        return ParseResult("rabobank", "jaaroverzicht", None, notes=["no year"])

    facts: list[AccountYearFact] = []
    account = re.compile(
        r"(?P<iban>NL\d{2}\s*RABO\s*\d{4}\s*\d{4}\s*\d{2})\s*EUR\s*"
        r"(?P<label>[^\n]+)\n"
        r"(?P<body>.*?)(?=\n\s*NL\d{2}\s*RABO\s*\d{4}\s*\d{4}\s*\d{2}\s+EUR|\Z)",
        re.I | re.S,
    )

    for match in account.finditer(text):
        label = re.sub(r"\s+", " ", match.group("label")).strip()
        # A credit-card balance is a debt, and its statement line carries the
        # linked payment account IBAN rather than a distinct asset account.
        if "creditcard" in label.lower():
            continue

        body = match.group("body")
        start = amount_after_label(body, f"Saldo 01-01-{year}")
        end = amount_after_label(body, f"Saldo 31-12-{year}")
        if start is None and end is None:
            continue

        fact = AccountYearFact(
            tax_year=year,
            issuer="rabobank",
            account_key=normalize_iban(match.group("iban")),
            account_label=f"Rabobank {label}",
            holder_names=_holders(text),
            start_balance=start,
            end_balance=end,
            interest_received=amount_after_label(
                body, f"Door u ontvangen rente in {year}"
            ),
            interest_paid=amount_after_label(body, f"Door u betaalde rente in {year}"),
        )
        fact.compute_capital_gain()
        facts.append(fact)

    return ParseResult("rabobank", "jaaroverzicht", year, facts=facts)


def _holders(text: str) -> list[str]:
    return first_holder(text, r"\b([A-Z](?:\.[A-Z])+\.\s+[A-Z][A-Za-z]+)\b")


PLUGIN = InstitutionPlugin(
    issuer="rabobank",
    classification_rules=(
        ClassificationRule("rabobank", "jaaroverzicht", _is_supported_document),
    ),
    parsers={
        "jaaroverzicht": ParserRegistration(simple_parser(parse_rabobank), 90),
    },
)
