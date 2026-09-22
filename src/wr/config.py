from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib  # type: ignore

from wr.pdf import normalize_iban


@dataclass(frozen=True)
class PartnerSettings:
    partner_a: str | None = None
    partner_b: str | None = None
    partner_a_aliases: tuple[str, ...] = field(default_factory=tuple)
    partner_b_aliases: tuple[str, ...] = field(default_factory=tuple)

    def configured(self) -> tuple[tuple[str, str | None], ...]:
        return (("a", self.partner_a), ("b", self.partner_b))

    def aliases_for(self, slot: str) -> tuple[str, ...]:
        if slot == "a":
            return self.partner_a_aliases
        if slot == "b":
            return self.partner_b_aliases
        raise ValueError(f"Unknown partner slot: {slot}")


@dataclass(frozen=True)
class AccountSettings:
    flatex_linked_account: str | None = None


@dataclass(frozen=True)
class Settings:
    project_root: Path
    config_path: Path | None = None
    import_root: Path | None = None
    db_path: Path = Path("data/wr.sqlite")
    partners: PartnerSettings = field(default_factory=PartnerSettings)
    accounts: AccountSettings = field(default_factory=AccountSettings)

    @property
    def resolved_db_path(self) -> Path:
        if self.db_path.is_absolute():
            return self.db_path
        return self.project_root / self.db_path


def load_config(path: str | Path | None = None) -> Settings:
    candidate = Path(path) if path is not None else Path.cwd() / "config.toml"
    if not candidate.is_file():
        if path is not None:
            raise FileNotFoundError(f"Config file not found: {candidate}")
        return Settings(project_root=Path.cwd().resolve())

    with candidate.open("rb") as config_file:
        raw = tomllib.load(config_file)
    return _settings_from_mapping(raw, candidate.resolve())


def _settings_from_mapping(raw: dict[str, Any], config_path: Path) -> Settings:
    partner_raw = _mapping(raw.get("partners"), "partners")
    account_raw = _mapping(raw.get("accounts"), "accounts")
    linked_account = _optional_string(
        account_raw.get("flatex_linked_account"), "accounts.flatex_linked_account"
    )
    return Settings(
        project_root=config_path.parent,
        config_path=config_path,
        import_root=_optional_path(raw.get("import_root"), "import_root"),
        db_path=_optional_path(raw.get("db_path"), "db_path") or Path("data/wr.sqlite"),
        partners=PartnerSettings(
            partner_a=_optional_string(partner_raw.get("partner_a"), "partners.partner_a"),
            partner_b=_optional_string(partner_raw.get("partner_b"), "partners.partner_b"),
            partner_a_aliases=_string_tuple(
                partner_raw.get("partner_a_aliases"), "partners.partner_a_aliases"
            ),
            partner_b_aliases=_string_tuple(
                partner_raw.get("partner_b_aliases"), "partners.partner_b_aliases"
            ),
        ),
        accounts=AccountSettings(
            flatex_linked_account=normalize_iban(linked_account) if linked_account else None
        ),
    )


def _mapping(value: Any, name: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be a TOML table")
    return value


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
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item.strip() for item in value
    ):
        raise ValueError(f"{name} must be an array of non-empty strings")
    return tuple(item.strip() for item in value)


def resolve_db_path(settings: Settings) -> Path:
    return settings.resolved_db_path
