from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import json
import os
import tempfile

from pydantic import JsonValue, TypeAdapter

from wr.config import DEFAULT_WORKSPACE_DATABASE, SETTINGS_FILENAME
from wr.models.settings import (
    InstitutionSettings,
    HouseholdSettings,
    PersistedSettings,
    SETTINGS_VERSION,
    Settings,
)
from wr.parsers._schemas import parse_institution_settings


def load_settings(workspace: str | Path | None = None) -> Settings:
    root = Path(workspace or Path.cwd()).expanduser().resolve()
    if root.exists() and not root.is_dir():
        raise ValueError(f"Workspace must be a directory: {root}")
    path = root / SETTINGS_FILENAME
    raw = TypeAdapter(dict[str, JsonValue]).validate_json(path.read_text(encoding="utf-8")) if path.exists() else {}
    version = raw.get("version", 1)
    if not isinstance(version, int) or not 1 <= version <= SETTINGS_VERSION:
        raise ValueError(f"Unsupported workspace settings version: {version}")
    upgrade = bool(raw) and version < SETTINGS_VERSION
    if version < 3:
        from wr.workspace.legacy import migrate_household

        raw = dict(raw)
        raw["household"] = migrate_household(raw.pop("partners", {})).model_dump(mode="json")
    settings = _settings_from_mapping(raw, root)
    if upgrade:
        save_settings(settings)
    return settings


def save_settings(
    settings: Settings,
    household: HouseholdSettings | None = None,
    import_root: str | None = None,
    *,
    db_path: str | Path | None = None,
    institution_options: dict[str, InstitutionSettings | dict[str, JsonValue]] | None = None,
) -> None:
    """Atomically save UI settings while preserving fields edited in other tabs."""
    from wr.identities.service import validate_household

    updated = replace(
        settings,
        household=household if household is not None else settings.household,
        import_root=(Path(import_root.strip()) if import_root.strip() else None) if import_root is not None else settings.import_root,
        db_path=Path(db_path) if db_path is not None else settings.db_path,
        institution_options=institution_options if institution_options is not None else settings.institution_options,
    )
    validate_household(updated.household)
    payload = {
        "version": SETTINGS_VERSION,
        "db_path": str(updated.db_path),
        "import_root": str(updated.import_root) if updated.import_root else None,
        "household": updated.household.model_dump(mode="json"),
        "institutions": {name: options.model_dump(exclude_unset=True) for name, options in updated.institution_options.items()},
    }
    _settings_from_mapping(payload, settings.project_root)
    serialized = json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
    path = settings.settings_path
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(dir=path.parent, prefix=f"{path.stem}-", suffix=".tmp")
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
    return Settings(
        project_root=root,
        import_root=Path(persisted.import_root) if persisted.import_root else None,
        db_path=Path(persisted.db_path) if persisted.db_path else DEFAULT_WORKSPACE_DATABASE,
        household=persisted.household,
        institution_options=persisted.institutions,
    )


def resolve_db_path(settings: Settings) -> Path:
    return settings.resolved_db_path
