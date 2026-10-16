from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Annotated

from pydantic import (
    ConfigDict,
    Field,
    JsonValue,
    SerializeAsAny,
    StringConstraints,
    field_validator,
)

from wr.config import DEFAULT_WORKSPACE_DATABASE, SETTINGS_FILENAME
from wr.models.base import Record
from wr.models.identities import HouseholdSettings


NonEmptyString = Annotated[str, StringConstraints(strict=True, strip_whitespace=True, min_length=1)]


SETTINGS_VERSION = 3


class InstitutionSettings(Record):
    model_config = ConfigDict(extra="allow")
    __pydantic_extra__: dict[str, JsonValue] = Field(init=False)


@dataclass(frozen=True)
class Settings:
    project_root: Path
    import_root: Path | None = None
    db_path: Path = DEFAULT_WORKSPACE_DATABASE
    household: HouseholdSettings = field(default_factory=HouseholdSettings)
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
        return self.project_root / SETTINGS_FILENAME


class PersistedSettings(Record):
    model_config = ConfigDict(extra="ignore", allow_inf_nan=False)
    version: int = Field(default=1, strict=True, ge=1, le=SETTINGS_VERSION)
    import_root: NonEmptyString | None = None
    db_path: NonEmptyString | None = None
    household: HouseholdSettings = Field(default_factory=HouseholdSettings)
    institutions: dict[str, SerializeAsAny[InstitutionSettings]] = Field(default_factory=dict)

    @field_validator("household", "institutions", mode="before")
    @classmethod
    def empty_object(cls, value: object) -> object:
        return {} if value is None else value


@dataclass(frozen=True)
class IdentitySuggestions:
    household: HouseholdSettings
    unresolved: tuple[str, ...]
