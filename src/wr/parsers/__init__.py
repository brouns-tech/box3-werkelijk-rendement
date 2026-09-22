from __future__ import annotations

import importlib
import pkgutil
import sqlite3
from pathlib import Path
from typing import Mapping

from wr.models import ParseResult
from wr.parsers.base import (
    ClassificationRule,
    InstitutionOptions,
    InstitutionPlugin,
    ParserContext,
    ParserRegistration,
)

_INFRASTRUCTURE_MODULES = {"base", "common"}


def _discover_plugins() -> tuple[InstitutionPlugin, ...]:
    discovered: list[tuple[str, InstitutionPlugin]] = []
    for module_info in pkgutil.iter_modules([str(Path(__file__).parent)]):
        if module_info.name.startswith("_") or module_info.name in _INFRASTRUCTURE_MODULES:
            continue
        module = importlib.import_module(f"{__name__}.{module_info.name}")
        plugin = getattr(module, "PLUGIN", None)
        if not isinstance(plugin, InstitutionPlugin):
            raise RuntimeError(
                f"Parser module {module.__name__} must export an InstitutionPlugin named PLUGIN"
            )
        discovered.append((module_info.name, plugin))

    discovered.sort(key=lambda item: (-item[1].classification_priority, item[0]))
    issuers = [plugin.issuer for _, plugin in discovered]
    if len(issuers) != len(set(issuers)):
        raise RuntimeError("Institution plugin issuer names must be unique")
    return tuple(plugin for _, plugin in discovered)


PLUGINS: tuple[InstitutionPlugin, ...] = _discover_plugins()

PARSER_REGISTRY: dict[tuple[str, str], ParserRegistration] = {
    (plugin.issuer, doc_type): registration
    for plugin in PLUGINS
    for doc_type, registration in plugin.parsers.items()
}


def classification_rules() -> tuple[ClassificationRule, ...]:
    return tuple(rule for plugin in PLUGINS for rule in plugin.classification_rules)


def parse_document(
    issuer: str,
    doc_type: str,
    text: str,
    tax_year: int | None,
    *,
    institution_options: InstitutionOptions | None = None,
) -> ParseResult:
    registration = PARSER_REGISTRY.get((issuer, doc_type))
    if registration is None:
        return ParseResult(
            issuer=issuer,
            doc_type=doc_type,
            tax_year=tax_year,
            notes=["no parser registered"],
        )
    options: Mapping[str, object] = (institution_options or {}).get(issuer, {})
    return registration.parser(text, tax_year, ParserContext(issuer, doc_type, options))


def canonical_priority(issuer: str, doc_type: str) -> int:
    registration = PARSER_REGISTRY.get((issuer, doc_type))
    return registration.canonical_priority if registration else 1


def postprocess_facts(
    conn: sqlite3.Connection,
    institution_options: InstitutionOptions | None = None,
) -> None:
    options = institution_options or {}
    for plugin in PLUGINS:
        if plugin.postprocess:
            plugin.postprocess(conn, options.get(plugin.issuer, {}))
