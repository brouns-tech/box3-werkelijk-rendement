from __future__ import annotations

from enum import Enum
from typing import Annotated, Literal
from uuid import UUID, uuid4

from pydantic import ConfigDict, Field, StringConstraints, model_validator

from wr.models.base import Record


IdentityName = Annotated[str, StringConstraints(strict=True, strip_whitespace=True, min_length=1)]


class IdentityRole(str, Enum):
    TAXPAYER = "taxpayer"
    CHILD = "child"


class TaxpayerPosition(str, Enum):
    PRIMARY = "primary"
    SECONDARY = "secondary"


class PersonIdentity(Record):
    model_config = ConfigDict(frozen=True)

    id: UUID = Field(default_factory=uuid4)
    name: IdentityName
    aliases: tuple[IdentityName, ...] = ()


class TaxpayerIdentity(PersonIdentity):
    role: Literal[IdentityRole.TAXPAYER] = IdentityRole.TAXPAYER
    position: TaxpayerPosition


class ChildIdentity(PersonIdentity):
    role: Literal[IdentityRole.CHILD] = IdentityRole.CHILD


Identity = Annotated[TaxpayerIdentity | ChildIdentity, Field(discriminator="role")]


class HouseholdSettings(Record):
    model_config = ConfigDict(frozen=True)

    identities: tuple[Identity, ...] = ()
    unassigned_names: tuple[IdentityName, ...] = ()

    @model_validator(mode="after")
    def unique_identities(self) -> HouseholdSettings:
        identifiers = [identity.id for identity in self.identities]
        if len(set(identifiers)) != len(identifiers):
            raise ValueError("Identity IDs must be unique within a household")
        positions = [identity.position for identity in self.taxpayers]
        if len(set(positions)) != len(positions):
            raise ValueError("Taxpayer positions must be unique within a household")
        return self

    @property
    def taxpayers(self) -> tuple[TaxpayerIdentity, ...]:
        return tuple(
            sorted(
                (identity for identity in self.identities if isinstance(identity, TaxpayerIdentity)),
                key=lambda identity: tuple(TaxpayerPosition).index(identity.position),
            )
        )

    @property
    def children(self) -> tuple[ChildIdentity, ...]:
        return tuple(identity for identity in self.identities if isinstance(identity, ChildIdentity))

    def taxpayer(self, position: TaxpayerPosition) -> TaxpayerIdentity | None:
        return next((identity for identity in self.taxpayers if identity.position == position), None)

    @property
    def primary(self) -> TaxpayerIdentity | None:
        return self.taxpayer(TaxpayerPosition.PRIMARY)

    @property
    def secondary(self) -> TaxpayerIdentity | None:
        return self.taxpayer(TaxpayerPosition.SECONDARY)

    def identity(self, identifier: UUID) -> TaxpayerIdentity | ChildIdentity | None:
        return next((identity for identity in self.identities if identity.id == identifier), None)
