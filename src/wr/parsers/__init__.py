from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from wr.models import ParseResult
from wr.parsers.aangifte import parse_aangifte
from wr.parsers.degiro import parse_degiro
from wr.parsers.flatex import parse_flatex
from wr.parsers.ing import parse_ing
from wr.parsers.rabobank import parse_rabobank
from wr.parsers.raisin import parse_raisin
from wr.parsers.revolut import parse_revolut
from wr.parsers.sns import parse_sns

Parser = Callable[[str, int | None, "ParserOptions"], ParseResult]


@dataclass(frozen=True)
class ParserOptions:
    flatex_linked_account: str | None = None


@dataclass(frozen=True)
class ParserRegistration:
    parser: Parser
    canonical_priority: int


def _simple(parser: Callable[[str, int | None], ParseResult]) -> Parser:
    return lambda text, year, _options: parser(text, year)


def _sns(doc_type: str) -> Parser:
    return lambda text, year, _options: parse_sns(text, year, doc_type)


def _revolut(doc_type: str) -> Parser:
    return lambda text, year, _options: parse_revolut(text, year, doc_type)


def _flatex(doc_type: str) -> Parser:
    return lambda text, year, options: parse_flatex(
        text, year, doc_type, options.flatex_linked_account
    )


PARSER_REGISTRY: dict[tuple[str, str], ParserRegistration] = {
    ("belastingdienst", "aangifte_ib"): ParserRegistration(_simple(parse_aangifte), 100),
    ("degiro", "jaaroverzicht"): ParserRegistration(_simple(parse_degiro), 100),
    ("ing", "jaaroverzicht"): ParserRegistration(_simple(parse_ing), 90),
    ("rabobank", "jaaroverzicht"): ParserRegistration(_simple(parse_rabobank), 90),
    ("raisin", "jaaroverzicht"): ParserRegistration(_simple(parse_raisin), 90),
    ("sns", "jaaroverzicht"): ParserRegistration(_sns("jaaroverzicht"), 90),
    ("sns", "totaaloverzicht"): ParserRegistration(_sns("totaaloverzicht"), 50),
    ("revolut", "jaaroverzicht"): ParserRegistration(_revolut("jaaroverzicht"), 90),
    ("revolut", "savings_statement"): ParserRegistration(
        _revolut("savings_statement"), 85
    ),
    ("revolut", "account_statement"): ParserRegistration(
        _revolut("account_statement"), 20
    ),
    ("flatex", "financial_instruments_statement"): ParserRegistration(
        _flatex("financial_instruments_statement"), 100
    ),
    ("flatex", "account_statement"): ParserRegistration(
        _flatex("account_statement"), 20
    ),
    ("flatex", "belastingcertificaat"): ParserRegistration(
        _flatex("belastingcertificaat"), 10
    ),
}


def parse_document(
    issuer: str,
    doc_type: str,
    text: str,
    tax_year: int | None,
    *,
    flatex_linked_account: str | None = None,
) -> ParseResult:
    registration = PARSER_REGISTRY.get((issuer, doc_type))
    if registration is None:
        return ParseResult(
            issuer=issuer,
            doc_type=doc_type,
            tax_year=tax_year,
            notes=["no parser registered"],
        )
    return registration.parser(
        text,
        tax_year,
        ParserOptions(flatex_linked_account=flatex_linked_account),
    )


def canonical_priority(issuer: str, doc_type: str) -> int:
    registration = PARSER_REGISTRY.get((issuer, doc_type))
    return registration.canonical_priority if registration else 1
