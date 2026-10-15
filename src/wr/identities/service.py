from __future__ import annotations

from dataclasses import replace
import sqlite3

from wr.identities.matching import identity_slot, name_key, name_tokens, same_person
from wr.models.settings import ChildSettings, IdentitySuggestions, PartnerSettings
from wr.storage.identities import filer_names, observed_names, tax_identity_names


def suggest_identities(conn: sqlite3.Connection) -> IdentitySuggestions:
    names = observed_names(conn)
    # Rich names establish groups first, so ambiguous initials cannot bridge people.
    ranked = sorted(names, key=lambda n: (-sum(len(t) > 1 for t in name_tokens(n)), -len(n), n.casefold()))
    groups: list[list[str]] = []
    unresolved = []
    for name in ranked:
        exact = [group for group in groups if any(name_key(name) == name_key(alias) for alias in group)]
        candidates = exact or [group for group in groups if same_person(name, group[0])]
        if len(candidates) == 1:
            candidates[0].append(name)
        elif len(candidates) > 1:
            unresolved.append(name)
        elif any(name_tokens(group[0])[-len(name_tokens(name)):] == name_tokens(name) for group in groups):
            unresolved.append(name)
        else:
            groups.append([name])
    # Prefer tax-return identities over incidental statement holders.
    tax_names = tax_identity_names(conn)
    filers = filer_names(conn)
    groups.sort(key=lambda g: (
        not any(n in filers for n in g),
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
            and not any(same_person(child.canonical_name, name) for _, name in configured.identities() if name)
        )
        return replace(configured, children=configured.children + additions) if additions else configured
    return suggest_identities(conn).partners


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
