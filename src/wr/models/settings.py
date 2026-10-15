from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Annotated

from pydantic import (
    BeforeValidator,
    ConfigDict,
    Field,
    JsonValue,
    SerializeAsAny,
    StringConstraints,
    field_validator,
)

from wr.models.base import Record


NonEmptyString = Annotated[str, StringConstraints(strict=True, strip_whitespace=True, min_length=1)]
StringTuple = Annotated[tuple[NonEmptyString, ...], BeforeValidator(lambda value: () if value is None else value)]

SETTINGS_VERSION = 2


class InstitutionSettings(Record):
    model_config = ConfigDict(extra="allow")
    __pydantic_extra__: dict[str, JsonValue] = Field(init=False)


@dataclass(frozen=True)
class ChildSettings:
    canonical_name: str
    aliases: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class PartnerSettings:
    partner_a: str | None = None
    partner_b: str | None = None
    partner_a_aliases: tuple[str, ...] = field(default_factory=tuple)
    partner_b_aliases: tuple[str, ...] = field(default_factory=tuple)
    unassigned_names: tuple[str, ...] = field(default_factory=tuple)
    children: tuple[ChildSettings, ...] = field(default_factory=tuple)

    def identities(self) -> tuple[tuple[str, str | None], ...]:
        return self.configured() + tuple(
            (f"child_{index}", child.canonical_name) for index, child in enumerate(self.children)
        )

    def canonical_for(self, slot: str) -> str | None:
        return dict(self.identities()).get(slot)

    def configured(self) -> tuple[tuple[str, str | None], ...]:
        return (("a", self.partner_a), ("b", self.partner_b))

    def aliases_for(self, slot: str) -> tuple[str, ...]:
        if slot == "a":
            return self.partner_a_aliases
        if slot == "b":
            return self.partner_b_aliases
        if slot.startswith("child_"):
            return self.children[int(slot.removeprefix("child_"))].aliases
        raise ValueError(f"Unknown partner slot: {slot}")


@dataclass(frozen=True)
class Settings:
    project_root: Path
    import_root: Path | None = None
    db_path: Path = Path("data/wr.sqlite")
    partners: PartnerSettings = field(default_factory=PartnerSettings)
    institution_options: dict[str, InstitutionSettings] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "institution_options", {
            name: options if isinstance(options, InstitutionSettings) else InstitutionSettings.model_validate(options)
            for name, options in self.institution_options.items()
        })

    @property
    def resolved_db_path(self) -> Path:
        path = self.db_path.expanduser()
        return path if path.is_absolute() else self.project_root / path

    @property
    def settings_path(self) -> Path:
        return self.project_root / ".wr-settings.json"


class PersistedChild(Record):
    canonical_name: NonEmptyString
    aliases: StringTuple = ()


class PersistedPartners(Record):
    partner_a: NonEmptyString | None = None
    partner_b: NonEmptyString | None = None
    partner_a_aliases: StringTuple = ()
    partner_b_aliases: StringTuple = ()
    unassigned_names: StringTuple = ()
    children: tuple[PersistedChild, ...] = ()


class PersistedSettings(Record):
    model_config = ConfigDict(extra="ignore", allow_inf_nan=False)
    version: int = Field(default=1, strict=True, ge=1, le=SETTINGS_VERSION)
    import_root: NonEmptyString | None = None
    db_path: NonEmptyString | None = None
    partners: PersistedPartners = Field(default_factory=PersistedPartners)
    institutions: dict[str, SerializeAsAny[InstitutionSettings]] = Field(default_factory=dict)

    @field_validator("partners", "institutions", mode="before")
    @classmethod
    def empty_object(cls, value: object) -> object:
        return {} if value is None else value


@dataclass(frozen=True)
class IdentitySuggestions:
    partners: PartnerSettings
    unresolved: tuple[str, ...]
