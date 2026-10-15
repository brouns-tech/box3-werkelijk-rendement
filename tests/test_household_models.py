import json

import pytest
from pydantic import ValidationError

from wr.identities.matching import resolve_identity
from wr.models.identities import (
    ChildIdentity,
    HouseholdSettings,
    IdentityRole,
    TaxpayerIdentity,
    TaxpayerPosition,
)
from wr.workspace.settings import load_settings, save_settings


@pytest.mark.parametrize("identity", [
    {"role": "taxpayer", "name": "Alex Example"},
    {"role": "taxpayer", "name": "Alex Example", "position": "a"},
    {"role": "child", "name": "Charlie Example", "position": "primary"},
    {"role": "unknown", "name": "Alex Example"},
    {"role": "child", "name": "   "},
    {"role": "child", "name": "Charlie Example", "aliases": [123]},
    {"role": "child", "name": "Charlie Example", "id": "invalid"},
])
def test_household_rejects_invalid_identity_variants(identity):
    with pytest.raises(ValidationError):
        HouseholdSettings.model_validate({"identities": [identity]})


def test_household_requires_unique_identifiers_and_taxpayer_positions():
    primary = TaxpayerIdentity(name="Alex Example", position=TaxpayerPosition.PRIMARY)
    with pytest.raises(ValidationError, match="Identity IDs"):
        HouseholdSettings(identities=(primary, ChildIdentity(id=primary.id, name="Charlie Example")))
    with pytest.raises(ValidationError, match="Taxpayer positions"):
        HouseholdSettings(identities=(primary, TaxpayerIdentity(name="Blair Example", position=TaxpayerPosition.PRIMARY)))


def test_identities_are_immutable_and_taxpayers_are_ordered_by_position():
    primary = TaxpayerIdentity(name="Alex Example", position=TaxpayerPosition.PRIMARY)
    secondary = TaxpayerIdentity(name="Blair Example", position=TaxpayerPosition.SECONDARY)
    child = ChildIdentity(name="Charlie Example")
    household = HouseholdSettings(identities=(child, secondary, primary))
    assert household.taxpayers == (primary, secondary)
    assert household.children == (child,)
    with pytest.raises(ValidationError, match="frozen"):
        child.name = "Other Name"
    with pytest.raises(ValidationError, match="frozen"):
        household.identities = ()


def test_identity_id_survives_rename_reorder_and_settings_round_trip(tmp_path):
    first = ChildIdentity(name="Charlie Example")
    second = ChildIdentity(name="Robin Example", aliases=("Robin",))
    renamed = ChildIdentity(id=second.id, name="Robin Updated", aliases=second.aliases)
    household = HouseholdSettings(identities=(renamed, first))
    save_settings(load_settings(tmp_path), household)
    restored = load_settings(tmp_path).household
    assert restored == household
    assert resolve_identity("Robin", restored).id == second.id
    assert restored.children[0].role is IdentityRole.CHILD
    payload = json.loads((tmp_path / ".wr-settings.json").read_text())
    assert payload["version"] == 3
    assert payload["household"]["identities"][0]["id"] == str(second.id)
    assert "partners" not in payload


def test_version_two_settings_migrate_to_typed_household_once(tmp_path):
    path = tmp_path / ".wr-settings.json"
    path.write_text(json.dumps({
        "version": 2,
        "db_path": "existing.sqlite",
        "import_root": "statements",
        "partners": {
            "partner_a": "Alex Example", "partner_a_aliases": ["A. Example"],
            "partner_b": "Blair Example",
            "children": [{"canonical_name": "Charlie Example", "aliases": ["Charlie"]}],
            "unassigned_names": ["C. Example"],
        },
        "institutions": {"future-bank": {"custom": [1, 2]}},
    }))
    (tmp_path / "config.toml").write_text("invalid retired configuration")
    settings = load_settings(tmp_path)
    assert settings.db_path.name == "existing.sqlite"
    assert settings.import_root.name == "statements"
    assert settings.household.primary.name == "Alex Example"
    assert settings.household.primary.position is TaxpayerPosition.PRIMARY
    assert settings.household.secondary.position is TaxpayerPosition.SECONDARY
    assert settings.household.children[0].aliases == ("Charlie",)
    assert resolve_identity("C. Example", settings.household) is None
    assert settings.institution_options["future-bank"].model_dump() == {"custom": [1, 2]}
    saved = path.read_bytes()
    assert load_settings(tmp_path) == settings
    assert path.read_bytes() == saved


@pytest.mark.parametrize("value", [[], "", 0, False])
def test_invalid_legacy_household_is_not_silently_discarded(tmp_path, value):
    path = tmp_path / ".wr-settings.json"
    path.write_text(json.dumps({"version": 2, "partners": value}))
    before = path.read_bytes()
    with pytest.raises(ValidationError):
        load_settings(tmp_path)
    assert path.read_bytes() == before


def test_legacy_null_aliases_remain_supported(tmp_path):
    (tmp_path / ".wr-settings.json").write_text(json.dumps({
        "version": 2,
        "partners": {
            "partner_a": "Alex Example", "partner_a_aliases": None,
            "unassigned_names": None,
            "children": [{"canonical_name": "Charlie Example", "aliases": None}],
        },
    }))
    household = load_settings(tmp_path).household
    assert household.primary.aliases == household.children[0].aliases == ()
