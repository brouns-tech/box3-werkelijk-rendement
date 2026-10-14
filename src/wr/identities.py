"""Reviewable lexical identity suggestions; source names are never rewritten."""
from __future__ import annotations

import json
import re
import sqlite3
import unicodedata
from dataclasses import dataclass, replace
from difflib import SequenceMatcher

from wr.config import ChildSettings, PartnerSettings


def name_tokens(name: str) -> tuple[str, ...]:
    text = unicodedata.normalize("NFKD", name.casefold())
    text = "".join(c for c in text if not unicodedata.combining(c))
    tokens = re.findall(r"[a-z]+", text)
    while tokens and tokens[0] in {"mr", "mrs", "ms", "dr", "dhr", "mevr", "deheer", "mevrouw"}:
        tokens.pop(0)
    return tuple(tokens)


def name_key(name: str) -> tuple[str, ...]:
    """Ignore case and dots/spaces between leading initials, retaining name boundaries."""
    tokens = name_tokens(name)
    initials = 0
    while initials < len(tokens) and len(tokens[initials]) == 1:
        initials += 1
    if initials > 1:
        return ("".join(tokens[:initials]), *tokens[initials:])
    return tokens


def similarity(left: str, right: str) -> float:
    a, b = name_tokens(left), name_tokens(right)
    if not a or not b:
        return 0.0
    if name_key(left) == name_key(right):
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
        exact = [group for group in groups if any(name_key(name) == name_key(alias) for alias in group)]
        candidates = exact or [group for group in groups if similarity(name, group[0]) >= 0.8]
        if len(candidates) == 1:
            candidates[0].append(name)
        elif len(candidates) > 1:
            unresolved.append(name)
        elif any(name_tokens(group[0])[-len(name_tokens(name)):] == name_tokens(name) for group in groups):
            unresolved.append(name)
        else:
            groups.append([name])
    # Prefer tax-return identities over incidental statement holders.
    tax_names = {
        name for row in conn.execute("SELECT filer_name, partner_a_name, partner_b_name FROM tax_returns")
        for name in row if name and name_tokens(name) and name.casefold() not in {"unknown", "onbekend", "partner_a", "partner_b"}
    }
    filer_names = {row[0] for row in conn.execute("SELECT filer_name FROM tax_returns")}
    groups.sort(key=lambda g: (
        not any(n in filer_names for n in g),
        not any(n in tax_names for n in g), name_tokens(g[0]),
    ))
    primary = [g for g in groups if any(n in tax_names for n in g)] if tax_names else groups
    chosen = primary[:2]
    unresolved.extend(n for g in primary[2:] for n in g)
    children = [g for g in groups if g not in primary] if tax_names else []
    values = {}
    for slot, group in zip(("a", "b"), chosen):
        values[f"partner_{slot}"] = group[0]
        values[f"partner_{slot}_aliases"] = tuple(group[1:])
    values["children"] = tuple(ChildSettings(g[0], tuple(g[1:])) for g in children)
    return IdentitySuggestions(PartnerSettings(**values), tuple(sorted(unresolved)))


def effective_partners(conn: sqlite3.Connection, configured: PartnerSettings | None) -> PartnerSettings:
    if configured and configured.children and not any(name for _, name in configured.configured()):
        detected = suggest_identities(conn).partners
        primary = [(slot, name) for slot, name in detected.configured() if name and identity_slot(name, configured) is None]
        values = {}
        for new_slot, (slot, name) in zip(("a", "b"), primary):
            values[f"partner_{new_slot}"] = name
            values[f"partner_{new_slot}_aliases"] = detected.aliases_for(slot)
        return replace(configured, **values)
    if configured and any(name for _, name in configured.configured()):
        # Preserve reviewed profiles; suggest newly imported, distinct holders only.
        detected = suggest_identities(conn).partners
        additions = tuple(
            child for child in detected.children
            if len(name_tokens(child.canonical_name)) >= 2
            and identity_slot(child.canonical_name, configured) is None
            and not any(name_key(child.canonical_name) == name_key(n) for n in configured.unassigned_names)
            and not any(similarity(child.canonical_name, name) >= 0.8 for _, name in configured.identities() if name)
        )
        return replace(configured, children=configured.children + additions) if additions else configured
    return suggest_identities(conn).partners


def identity_slot(name: str | None, partners: PartnerSettings) -> str | None:
    if not name:
        return None
    if any(name_key(name) == name_key(excluded) for excluded in partners.unassigned_names):
        return None
    scores = []
    for slot, canonical in partners.identities():
        if canonical:
            score = max(similarity(name, alias) for alias in (canonical, *partners.aliases_for(slot)))
            scores.append((score, slot))
    scores.sort(reverse=True)
    if not scores or scores[0][0] < 0.8:
        return None
    if scores[0][0] == 1.0 and (len(scores) == 1 or scores[1][0] < 1.0):
        return scores[0][1]
    if len(scores) > 1 and scores[0][0] - scores[1][0] < 0.1:
        return None
    return scores[0][1]


def validate_partners(partners: PartnerSettings) -> None:
    seen: dict[tuple[str, ...], str] = {}
    for slot, canonical in partners.identities():
        aliases = partners.aliases_for(slot)
        if aliases and not canonical:
            raise ValueError("Provide a taxpayer name before assigning aliases.")
        for name in ((canonical,) if canonical else ()) + aliases:
            key = name_key(name)
            if not key:
                raise ValueError("Names must contain letters.")
            if key in seen and seen[key] != slot:
                description = "both taxpayers" if {slot, seen[key]} <= {"a", "b"} else "multiple people"
                raise ValueError(f"Name or alias assigned to {description}: {name}")
            seen[key] = slot
