"""Reviewable lexical identity suggestions; source names are never rewritten."""
from __future__ import annotations

import json
import re
import sqlite3
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher

from wr.config import PartnerSettings


def name_tokens(name: str) -> tuple[str, ...]:
    text = unicodedata.normalize("NFKD", name.casefold())
    text = "".join(c for c in text if not unicodedata.combining(c))
    tokens = re.findall(r"[a-z]+", text)
    while tokens and tokens[0] in {"mr", "mrs", "ms", "dr", "dhr", "mevr", "deheer", "mevrouw"}:
        tokens.pop(0)
    return tuple(tokens)


def similarity(left: str, right: str) -> float:
    a, b = name_tokens(left), name_tokens(right)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    if len(a) == 1 or len(b) == 1:
        short, long = (a, b) if len(a) == 1 else (b, a)
        # First names may match uniquely; surnames alone never establish identity.
        return 0.8 if len(short[0]) > 1 and short[0] == long[0] and len(long) > 1 else 0.0
    if a[1:] == b[1:]:
        if a[0][0] != b[0][0]:
            return 0.0
        if len(a[0]) == 1 or len(b[0]) == 1:
            return 0.85
        return 0.9 if SequenceMatcher(None, a[0], b[0]).ratio() >= 0.86 else 0.0
    # Multiple initials, optionally expanded to full given names.
    if a[-1] == b[-1] and len(a) == len(b):
        if all(x == y or (min(len(x), len(y)) == 1 and x[0] == y[0]) for x, y in zip(a[:-1], b[:-1])):
            return 0.85
    if a[0] == b[0] and len(a[0]) > 1:
        return 0.9 if SequenceMatcher(None, " ".join(a[1:]), " ".join(b[1:])).ratio() >= 0.9 else 0.0
    return 0.0


def observed_names(conn: sqlite3.Connection) -> list[str]:
    names: set[str] = set()
    for row in conn.execute("SELECT filer_name, partner_a_name, partner_b_name FROM tax_returns"):
        names.update(name.strip() for name in row if name and name.strip())
    for row in conn.execute("SELECT holder_names FROM account_year_facts"):
        names.update(name.strip() for name in json.loads(row[0] or "[]") if name.strip())
    return sorted((n for n in names if name_tokens(n) and n.casefold() not in {"unknown", "onbekend", "partner_a", "partner_b"}), key=lambda n: (name_tokens(n), n))


@dataclass(frozen=True)
class IdentitySuggestions:
    partners: PartnerSettings
    unresolved: tuple[str, ...]


def suggest_identities(conn: sqlite3.Connection) -> IdentitySuggestions:
    names = observed_names(conn)
    # Rich names establish groups first, so ambiguous initials cannot bridge people.
    ranked = sorted(names, key=lambda n: (-sum(len(t) > 1 for t in name_tokens(n)), -len(n), n.casefold()))
    groups: list[list[str]] = []
    unresolved = []
    for name in ranked:
        candidates = [group for group in groups if similarity(name, group[0]) >= 0.8]
        if len(candidates) == 1:
            candidates[0].append(name)
        elif len(candidates) > 1:
            unresolved.append(name)
        elif any(name_tokens(group[0])[-len(name_tokens(name)):] == name_tokens(name) for group in groups):
            unresolved.append(name)
        else:
            groups.append([name])
    # Prefer tax-return identities over incidental statement holders.
    tax_names = {row[0] for row in conn.execute("SELECT filer_name FROM tax_returns")}
    groups.sort(key=lambda g: (not any(n in tax_names for n in g), name_tokens(g[0])))
    chosen = groups[:2]
    unresolved.extend(n for g in groups[2:] for n in g)
    values = {}
    for slot, group in zip(("a", "b"), chosen):
        values[f"partner_{slot}"] = group[0]
        values[f"partner_{slot}_aliases"] = tuple(group[1:])
    return IdentitySuggestions(PartnerSettings(**values), tuple(sorted(unresolved)))


def effective_partners(conn: sqlite3.Connection, configured: PartnerSettings | None) -> PartnerSettings:
    if configured and any(name for _, name in configured.configured()):
        return configured
    return suggest_identities(conn).partners


def identity_slot(name: str | None, partners: PartnerSettings) -> str | None:
    if not name:
        return None
    if any(name_tokens(name) == name_tokens(excluded) for excluded in partners.unassigned_names):
        return None
    scores = []
    for slot, canonical in partners.configured():
        if canonical:
            score = max(similarity(name, alias) for alias in (canonical, *partners.aliases_for(slot)))
            scores.append((score, slot))
    scores.sort(reverse=True)
    if not scores or scores[0][0] < 0.8:
        return None
    if len(scores) > 1 and scores[0][0] - scores[1][0] < 0.1:
        return None
    return scores[0][1]


def validate_partners(partners: PartnerSettings) -> None:
    seen: dict[tuple[str, ...], str] = {}
    for slot, canonical in partners.configured():
        aliases = partners.aliases_for(slot)
        if aliases and not canonical:
            raise ValueError("Provide a taxpayer name before assigning aliases.")
        for name in ((canonical,) if canonical else ()) + aliases:
            key = name_tokens(name)
            if not key:
                raise ValueError("Names must contain letters.")
            if key in seen and seen[key] != slot:
                raise ValueError(f"Name or alias assigned to both taxpayers: {name}")
            seen[key] = slot
