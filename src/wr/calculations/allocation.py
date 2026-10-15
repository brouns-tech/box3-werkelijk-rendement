from __future__ import annotations

from wr.calculations.returns import fact_return, is_box3_fact
from wr.identities.matching import identity_slot, similarity, same_person
from wr.models import CoverageStatus
from wr.models.settings import PartnerSettings
from wr.models.storage import FactRecord
from wr.money import add, multiply


def individual_portfolio(
    facts: list[FactRecord],
    year: int,
    filer_name: str | None,
    partner_cfg: PartnerSettings,
) -> tuple[float | None, str, str | None]:
    aliases = _aliases_for_filer(filer_name, partner_cfg)
    filer_slot = identity_slot(filer_name, partner_cfg)
    total = 0.0
    used = 0
    missing: list[str] = []
    for fact in facts:
        if not is_box3_fact(fact):
            continue
        holders = fact.holder_names
        holder_slots = [identity_slot(holder, partner_cfg) for holder in holders]
        matches = [identity_slot(holder, partner_cfg) == filer_slot if filer_slot else _matches_alias(holder, aliases) for holder in holders]
        has_child = any(slot and slot.startswith("child_") for slot in holder_slots)
        child_pool = has_child and all(holder_slots) and (
            all(slot.startswith("child_") for slot in holder_slots) or fact.ownership == "joint"
        )
        if child_pool:
            # Child assets belong to the parents' joint pool, never a child tax result.
            portion = 1.0 / len([name for _, name in partner_cfg.configured() if name])
        elif len(holders) == 1 and matches[0]:
            portion = 1.0
        elif fact.ownership == "joint" and len(holders) >= 2 and any(matches):
            portion = 0.5
        elif not holders:
            missing.append(f"{fact.issuer} {fact.account_key} (holder unknown)")
            continue
        else:
            if any(identity_slot(holder, partner_cfg) is None for holder in holders):
                missing.append(f"{fact.issuer} {fact.account_key} (holder needs review)")
            continue
        value = fact_return(fact)
        if value is None:
            reason = "requires EUR conversion and currency gain/loss" if (fact.currency or "EUR") != "EUR" else "no actual-return fields"
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
    filer_name: str | None, partner_cfg: PartnerSettings
) -> list[str]:
    aliases = [filer_name or ""]
    for slot, configured in partner_cfg.configured():
        if same_person(filer_name, configured):
            aliases.extend([configured or "", *partner_cfg.aliases_for(slot)])
    return aliases


def _matches_alias(name: str, aliases: list[str]) -> bool:
    return any(similarity(name, alias) >= 0.8 for alias in aliases)
