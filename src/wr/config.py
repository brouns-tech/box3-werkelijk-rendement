from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Annotated

from pydantic import BeforeValidator, ConfigDict, Field, JsonValue, SerializeAsAny, StringConstraints, TypeAdapter, field_validator
from wr.records import InstitutionSettings, Record, parse_institution_settings

NonEmptyString = Annotated[str, StringConstraints(strict=True, strip_whitespace=True, min_length=1)]
StringTuple = Annotated[tuple[NonEmptyString, ...], BeforeValidator(lambda value: () if value is None else value)]

SETTINGS_VERSION = 2


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
            name: parse_institution_settings(name, options)
            for name, options in self.institution_options.items()
        })

    @property
    def resolved_db_path(self) -> Path:
        path = self.db_path.expanduser()
        return path if path.is_absolute() else self.project_root / path

    @property
    def settings_path(self) -> Path:
        return self.project_root / ".wr-settings.json"


def load_settings(workspace: str | Path | None = None) -> Settings:
    root = Path(workspace or Path.cwd()).expanduser().resolve()
    if root.exists() and not root.is_dir():
        raise ValueError(f"Workspace must be a directory: {root}")
    path = root / ".wr-settings.json"
    raw = TypeAdapter(dict[str, JsonValue]).validate_json(path.read_text(encoding="utf-8")) if path.exists() else {}
    version = raw.get("version", 1)
    if not isinstance(version, int) or not 1 <= version <= SETTINGS_VERSION:
        raise ValueError(f"Unsupported workspace settings version: {version}")
    # Upgrade the original UI preferences, preserving their overrides over TOML.
    # Version 2 is self-contained: legacy files are never read again afterward.
    upgrade = bool(raw) and version < SETTINGS_VERSION
    if version < SETTINGS_VERSION and (root / "config.toml").is_file():
        from wr.legacy_settings import read_legacy_settings

        raw = {**read_legacy_settings(root / "config.toml"), **raw}
        upgrade = True
    settings = _settings_from_mapping(raw, root)
    if upgrade:
        save_settings(settings)
    return settings


def save_settings(
    settings: Settings,
    partners: PartnerSettings | None = None,
    import_root: str | None = None,
    *,
    db_path: str | Path | None = None,
    institution_options: dict[str, InstitutionSettings | dict[str, JsonValue]] | None = None,
) -> None:
    """Atomically save UI settings while preserving fields edited in other tabs."""
    from wr.identities import validate_partners

    updated = replace(
        settings,
        partners=partners if partners is not None else settings.partners,
        import_root=(Path(import_root.strip()) if import_root.strip() else None) if import_root is not None else settings.import_root,
        db_path=Path(db_path) if db_path is not None else settings.db_path,
        institution_options=institution_options if institution_options is not None else settings.institution_options,
    )
    validate_partners(updated.partners)
    payload = {
        "version": SETTINGS_VERSION,
        "db_path": str(updated.db_path),
        "import_root": str(updated.import_root) if updated.import_root else None,
        "partners": asdict(updated.partners),
        "institutions": {name: options.model_dump(exclude_unset=True) for name, options in updated.institution_options.items()},
    }
    _settings_from_mapping(payload, settings.project_root)
    serialized = json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
    path = settings.settings_path
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(dir=path.parent, prefix=".wr-settings-", suffix=".tmp")
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            output.write(serialized)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


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

    @field_validator("institutions", mode="before")
    @classmethod
    def validate_institutions(cls, value: object) -> object:
        if value is None:
            return {}
        if not isinstance(value, dict):
            return value
        result = {}
        for name, options in value.items():
            if options is not None and not isinstance(options, (dict, InstitutionSettings)):
                raise ValueError(f"institutions.{name} must be an object")
            result[name] = parse_institution_settings(name, options)
        return result


def _settings_from_mapping(raw: object, root: Path) -> Settings:
    persisted = PersistedSettings.model_validate(raw)
    partner = persisted.partners
    return Settings(
        project_root=root,
        import_root=Path(persisted.import_root) if persisted.import_root else None,
        db_path=Path(persisted.db_path) if persisted.db_path else Path("data/wr.sqlite"),
        partners=PartnerSettings(
            partner_a=partner.partner_a,
            partner_b=partner.partner_b,
            partner_a_aliases=partner.partner_a_aliases,
            partner_b_aliases=partner.partner_b_aliases,
            unassigned_names=partner.unassigned_names,
            children=tuple(ChildSettings(child.canonical_name, child.aliases) for child in partner.children),
        ),
        institution_options=persisted.institutions,
    )


def resolve_db_path(settings: Settings) -> Path:
    return settings.resolved_db_path
