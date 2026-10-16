"""Upgrade household identities from earlier JSON settings versions."""
from __future__ import annotations

from pydantic import field_validator

from wr.models.base import Record
from wr.models.identities import ChildIdentity, HouseholdSettings, TaxpayerIdentity, TaxpayerPosition


class LegacyChild(Record):
    canonical_name: str
    aliases: tuple[str, ...] = ()

    @field_validator("aliases", mode="before")
    @classmethod
    def empty_aliases(cls, value: object) -> object:
        return () if value is None else value


class LegacyPartners(Record):
    partner_a: str | None = None
    partner_b: str | None = None
    partner_a_aliases: tuple[str, ...] = ()
    partner_b_aliases: tuple[str, ...] = ()
    unassigned_names: tuple[str, ...] = ()
    children: tuple[LegacyChild, ...] = ()

    @field_validator("partner_a_aliases", "partner_b_aliases", "unassigned_names", mode="before")
    @classmethod
    def empty_names(cls, value: object) -> object:
        return () if value is None else value


def migrate_household(value: object) -> HouseholdSettings:
    legacy = LegacyPartners.model_validate({} if value is None else value)
    taxpayers = []
    for position, name, aliases in (
        (TaxpayerPosition.PRIMARY, legacy.partner_a, legacy.partner_a_aliases),
        (TaxpayerPosition.SECONDARY, legacy.partner_b, legacy.partner_b_aliases),
    ):
        if aliases and not name:
            raise ValueError("Provide a taxpayer name before assigning aliases.")
        if name:
            taxpayers.append(TaxpayerIdentity(name=name, aliases=aliases, position=position))
    return HouseholdSettings(
        identities=tuple(taxpayers) + tuple(
            ChildIdentity(name=child.canonical_name, aliases=child.aliases) for child in legacy.children
        ),
        unassigned_names=legacy.unassigned_names,
    )
