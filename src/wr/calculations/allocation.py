from __future__ import annotations

from wr.calculations.returns import fact_return, is_box3_fact
from wr.identities.matching import resolve_identity, same_person
from wr.models import CoverageStatus, Ownership
from wr.models.identities import HouseholdSettings, IdentityRole
from wr.models.storage import FactRecord
from wr.money import Currency, add, multiply


def individual_portfolio(
    facts: list[FactRecord],
    year: int,
    filer_name: str | None,
    household: HouseholdSettings,
) -> tuple[float | None, str, str | None]:
    aliases = _aliases_for_filer(filer_name, household)
    filer_identity = resolve_identity(filer_name, household)
    total = 0.0
    used = 0
    missing: list[str] = []
    for fact in facts:
        if not is_box3_fact(fact):
            continue
        holders = fact.holder_names
        holder_identities = [resolve_identity(holder, household) for holder in holders]
        matches = [
            identity is not None and identity.id == filer_identity.id
            if filer_identity is not None else _matches_alias(holder, aliases)
            for holder, identity in zip(holders, holder_identities)
        ]
        has_child = any(identity is not None and identity.role is IdentityRole.CHILD for identity in holder_identities)
        child_pool = has_child and all(holder_identities) and (
            all(identity.role is IdentityRole.CHILD for identity in holder_identities) or fact.ownership == Ownership.JOINT
        )
        if child_pool:
            # Child assets belong to the parents' joint pool, never a child tax result.
            portion = 1.0 / len(household.taxpayers)
        elif len(holders) == 1 and matches[0]:
            portion = 1.0
        elif fact.ownership == Ownership.JOINT and len(holders) >= 2 and any(matches):
            portion = 0.5
        elif not holders:
            missing.append(f"{fact.issuer} {fact.account_key} (holder unknown)")
            continue
        else:
            if any(resolve_identity(holder, household) is None for holder in holders):
                missing.append(f"{fact.issuer} {fact.account_key} (holder needs review)")
            continue
        value = fact_return(fact)
        if value is None:
            reason = "requires EUR conversion and currency gain/loss" if (fact.currency or Currency.EUR) != Currency.EUR else "no actual-return fields"
            missing.append(f"{fact.issuer} {fact.account_key} ({reason})")
            continue
        total = add(total, multiply(value, portion))
        used += 1
    if not used:
        missing.append("no statement-derived assets assigned to this filer")
    return (
        total if used else None,
        CoverageStatus.PARTIAL.value if missing else CoverageStatus.COMPLETE.value,
        "; ".join(missing) if missing else None,
    )


def _aliases_for_filer(
    filer_name: str | None, household: HouseholdSettings
) -> list[str]:
    aliases = [filer_name or ""]
    for identity in household.taxpayers:
        if same_person(filer_name, identity.name):
            aliases.extend([identity.name, *identity.aliases])
    return aliases


def _matches_alias(name: str, aliases: list[str]) -> bool:
    return any(same_person(name, alias) for alias in aliases)
