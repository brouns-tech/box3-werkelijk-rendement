from __future__ import annotations

from wr.models import ParseResult


def parse_document(issuer: str, doc_type: str, text: str, tax_year: int | None) -> ParseResult:
    if issuer == "belastingdienst" and doc_type == "aangifte_ib":
        from wr.parsers.aangifte import parse_aangifte

        return parse_aangifte(text, tax_year)

    if issuer == "degiro":
        from wr.parsers.degiro import parse_degiro

        return parse_degiro(text, tax_year)

    if issuer == "ing":
        from wr.parsers.ing import parse_ing

        return parse_ing(text, tax_year)

    if issuer == "sns":
        from wr.parsers.sns import parse_sns

        return parse_sns(text, tax_year, doc_type)

    if issuer == "raisin":
        from wr.parsers.raisin import parse_raisin

        return parse_raisin(text, tax_year)

    if issuer == "revolut":
        from wr.parsers.revolut import parse_revolut

        return parse_revolut(text, tax_year, doc_type)

    if issuer == "flatex":
        from wr.parsers.flatex import parse_flatex

        return parse_flatex(text, tax_year, doc_type)

    return ParseResult(issuer=issuer, doc_type=doc_type, tax_year=tax_year, notes=["no parser"])
