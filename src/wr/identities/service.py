from __future__ import annotations

import sqlite3
from uuid import NAMESPACE_URL, UUID, uuid5

from wr.identities.matching import resolve_identity, name_key, name_tokens, same_person
from wr.models.identities import ChildIdentity, HouseholdSettings, TaxpayerIdentity, TaxpayerPosition
from wr.models.settings import IdentitySuggestions
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
    identities = tuple(
        TaxpayerIdentity(
            id=_suggested_id(group[0]), name=group[0], aliases=tuple(group[1:]), position=position,
        )
        for position, group in zip(TaxpayerPosition, chosen)
    ) + tuple(
        ChildIdentity(id=_suggested_id(group[0]), name=group[0], aliases=tuple(group[1:]))
        for group in children
    )
    return IdentitySuggestions(HouseholdSettings(identities=identities), tuple(sorted(unresolved)))


def _suggested_id(name: str) -> UUID:
    return uuid5(NAMESPACE_URL, "wr:identity:" + " ".join(name_key(name)))


def effective_household(conn: sqlite3.Connection, configured: HouseholdSettings | None) -> HouseholdSettings:
    if configured and configured.children and not configured.taxpayers:
        detected = suggest_identities(conn).household
        primary = [
            identity for identity in detected.taxpayers
            if resolve_identity(identity.name, configured) is None
        ]
        taxpayers = tuple(
            identity.model_copy(update={"position": position})
            for position, identity in zip(TaxpayerPosition, primary)
        )
        return HouseholdSettings(
            identities=taxpayers + configured.children, unassigned_names=configured.unassigned_names,
        )
    if configured and configured.taxpayers:
        detected = suggest_identities(conn).household
        additions = tuple(
            child for child in detected.children
            if len(name_tokens(child.name)) >= 2
            and resolve_identity(child.name, configured) is None
            and not any(name_key(child.name) == name_key(name) for name in configured.unassigned_names)
            and not any(same_person(child.name, identity.name) for identity in configured.identities)
        )
        return HouseholdSettings(
            identities=configured.identities + additions, unassigned_names=configured.unassigned_names,
        )
    return suggest_identities(conn).household


def validate_household(household: HouseholdSettings) -> None:
    seen: dict[tuple[str, ...], UUID] = {}
    for identity in household.identities:
        for name in (identity.name, *identity.aliases):
            key = name_key(name)
            if not key:
                raise ValueError("Names must contain letters.")
            if key in seen and seen[key] != identity.id:
                raise ValueError(f"Name or alias assigned to multiple people: {name}")
            seen[key] = identity.id
