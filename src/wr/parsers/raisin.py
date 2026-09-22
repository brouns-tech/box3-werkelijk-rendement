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
        "raisin" in text
        and "raisin financieel jaaroverzicht" in text
        and "raisin spaarproduct" in text
        and "kenmerk:" in text
        and "omschrijving:" in text
        and "bronbelasting" in text
    )


def parse_raisin(text: str, tax_year: int | None = None) -> ParseResult:
    year = resolve_tax_year(text, tax_year)
    if year is None:
        return ParseResult("raisin", "jaaroverzicht", None, notes=["no year"])

    facts: list[AccountYearFact] = []
    # Blocks with KENMERK / IBAN / balances
    blocks = re.split(r"\n\s*KENMERK:", text)
    for block in blocks[1:]:
        kenmerk_m = re.search(r"^\s*(\S+)", block)
        iban_m = re.search(r"IBAN:\s*([A-Z0-9]+)", block)
        bank_m = re.search(r"BANK:\s*([^\n]+)", block)
        land_m = re.search(r"LAND:\s*([^\n]+)", block)
        # Saldo 01.01 / 31.12 / Rente Bruto / Netto
        am = re.search(
            rf"(EUR|USD)\s+([\d.]+,\d{{2}})\s+([\d.]+,\d{{2}})\s+([\d.]+,\d{{2}})\s+([\d.]+,\d{{2}})",
            block,
        )
        if not am:
            continue
        iban = normalize_iban(iban_m.group(1)) if iban_m else (kenmerk_m.group(1) if kenmerk_m else "raisin")
        label_parts = ["Raisin"]
        if bank_m:
            label_parts.append(bank_m.group(1).strip())
        if land_m:
            label_parts.append(land_m.group(1).strip())
        fact = AccountYearFact(
            tax_year=year,
            issuer="raisin",
            account_key=iban,
            account_label=" ".join(label_parts),
            holder_names=_holders(text),
            currency=am.group(1),
            start_balance=parse_nl_amount(am.group(2)),
            end_balance=parse_nl_amount(am.group(3)),
            interest_received=parse_nl_amount(am.group(5)),  # netto
            extra={"rente_bruto": parse_nl_amount(am.group(4))},
        )
        fact.compute_capital_gain()
        facts.append(fact)

    return ParseResult("raisin", "jaaroverzicht", year, facts=facts)


def _holders(text: str) -> list[str]:
    return first_holder(text, r"Naam:\s*([^\n]+)")


PLUGIN = InstitutionPlugin(
    issuer="raisin",
    classification_rules=(
        ClassificationRule("raisin", "jaaroverzicht", _is_supported_document),
    ),
    parsers={
        "jaaroverzicht": ParserRegistration(simple_parser(parse_raisin), 90),
    },
)
