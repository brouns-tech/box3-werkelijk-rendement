from __future__ import annotations

import re

from wr.classify import guess_tax_year
from wr.models import AccountYearFact, ParseResult
from wr.pdf import parse_nl_amount


def parse_flatex(text: str, tax_year: int | None, doc_type: str) -> ParseResult:
    """Legacy Flatex docs. Prefer Degiro jaaroverzicht when both exist."""
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
        logical_group="flatex_degiro",
        gain_method="interest_only" if interest is not None else "unknown",
        capital_gain=interest,
    )
    return ParseResult(
        "flatex",
        doc_type,
        year,
        facts=[fact],
        notes=["legacy flatex; superseded by degiro jaaroverzicht when present"],
    )
