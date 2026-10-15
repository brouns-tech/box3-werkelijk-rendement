from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from typing import Callable, Mapping, Protocol

from wr.models import ParseResult
from wr.messages import Message
from wr.records import FactMetadata, InstitutionSettings
from pydantic import JsonValue

InstitutionOptions = Mapping[str, InstitutionSettings | Mapping[str, JsonValue]]


@dataclass(frozen=True)
class ClassificationRule:
    issuer: str
    doc_type: str
    detector: Callable[[str], bool]
    supported: bool = True


@dataclass(frozen=True)
class ParserContext:
    issuer: str
    doc_type: str
    options: InstitutionSettings = field(default_factory=InstitutionSettings)


class Parser(Protocol):
    def __call__(
            self, text: str, tax_year: int | None, context: ParserContext
    ) -> ParseResult: ...


class PostProcessor(Protocol):
    def __call__(
            self, conn: sqlite3.Connection, options: InstitutionSettings
    ) -> None: ...


@dataclass(frozen=True)
class ParserRegistration:
    parser: Parser
    canonical_priority: int


@dataclass(frozen=True)
class InstitutionSetting:
    key: str
    label: Message | str
    help: Message | str = ""


@dataclass(frozen=True)
class InstitutionPlugin:
    issuer: str
    classification_rules: tuple[ClassificationRule, ...]
    parsers: Mapping[str, ParserRegistration]
    postprocess: PostProcessor | None = None
    classification_priority: int = 0
    settings_fields: tuple[InstitutionSetting, ...] = ()
    metadata_model: type[FactMetadata] = FactMetadata
    options_model: type[InstitutionSettings] = InstitutionSettings


def simple_parser(
        parser: Callable[[str, int | None], ParseResult],
) -> Parser:
    return lambda text, year, _context: parser(text, year)


def doc_type_parser(
        parser: Callable[[str, int | None, str], ParseResult],
) -> Parser:
    return lambda text, year, context: parser(text, year, context.doc_type)
