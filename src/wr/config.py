from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any

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
    assume_fiscal_partnership: bool = True

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
    institution_options: dict[str, dict[str, object]] = field(default_factory=dict)

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
    raw = _mapping(json.loads(path.read_text(encoding="utf-8")), "settings") if path.exists() else {}
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
    institution_options: dict[str, dict[str, object]] | None = None,
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
        "institutions": updated.institution_options,
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


def _settings_from_mapping(raw: dict[str, Any], root: Path) -> Settings:
    partner_raw = _mapping(raw.get("partners"), "partners")
    institution_raw = _mapping(raw.get("institutions"), "institutions")
    return Settings(
        project_root=root,
        import_root=_optional_path(raw.get("import_root"), "import_root"),
        db_path=_optional_path(raw.get("db_path"), "db_path") or Path("data/wr.sqlite"),
        partners=PartnerSettings(
            partner_a=_optional_string(partner_raw.get("partner_a"), "partners.partner_a"),
            partner_b=_optional_string(partner_raw.get("partner_b"), "partners.partner_b"),
            partner_a_aliases=_string_tuple(partner_raw.get("partner_a_aliases"), "partners.partner_a_aliases"),
            partner_b_aliases=_string_tuple(partner_raw.get("partner_b_aliases"), "partners.partner_b_aliases"),
            unassigned_names=_string_tuple(partner_raw.get("unassigned_names"), "partners.unassigned_names"),
            children=_children(partner_raw.get("children", [])),
            assume_fiscal_partnership=_boolean(partner_raw.get("assume_fiscal_partnership", True), "partners.assume_fiscal_partnership"),
        ),
        institution_options={name: _mapping(options, f"institutions.{name}") for name, options in institution_raw.items()},
    )


def _mapping(value: Any, name: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be an object")
    return value


def _boolean(value: Any, name: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{name} must be a boolean")
    return value


def _children(value: Any) -> tuple[ChildSettings, ...]:
    if not isinstance(value, (list, tuple)):
        raise ValueError("partners.children must be an array")
    children = []
    for item in value:
        raw = _mapping(item, "child")
        name = _optional_string(raw.get("canonical_name"), "child.canonical_name")
        if name is None:
            raise ValueError("Provide a child canonical name.")
        children.append(ChildSettings(name, _string_tuple(raw.get("aliases"), "child.aliases")))
    return tuple(children)


def _optional_string(value: Any, name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value.strip()


def _optional_path(value: Any, name: str) -> Path | None:
    parsed = _optional_string(value, name)
    return Path(parsed) if parsed else None


def _string_tuple(value: Any, name: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, (list, tuple)) or any(not isinstance(item, str) or not item.strip() for item in value):
        raise ValueError(f"{name} must be an array of non-empty strings")
    return tuple(item.strip() for item in value)


def resolve_db_path(settings: Settings) -> Path:
    return settings.resolved_db_path
