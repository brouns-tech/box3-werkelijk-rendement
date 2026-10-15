from __future__ import annotations

from dataclasses import asdict, replace
from pathlib import Path
import json
import os
import tempfile

from pydantic import JsonValue, TypeAdapter

from wr.models.settings import (
    ChildSettings,
    InstitutionSettings,
    PartnerSettings,
    PersistedSettings,
    SETTINGS_VERSION,
    Settings,
)
from wr.parsers._schemas import parse_institution_settings


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
        from wr.workspace.legacy import read_legacy_settings

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
    from wr.identities.service import validate_partners

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


def _settings_from_mapping(raw: object, root: Path) -> Settings:
    if isinstance(raw, dict):
        raw = dict(raw)
        institutions = raw.get("institutions")
        if isinstance(institutions, dict):
            raw["institutions"] = {name: parse_institution_settings(name, value) for name, value in institutions.items()}
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
