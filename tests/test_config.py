import json
from pathlib import Path

import pytest

from wr.models.identities import HouseholdSettings, TaxpayerIdentity, TaxpayerPosition
from wr.cli import main
from wr.models.settings import Settings
from wr.workspace.settings import load_settings, resolve_db_path, save_settings
from wr.models.importing import ImportReport
from wr.importing.pipeline import run_import
from wr.parsers import parse_document


def test_settings_default_to_current_workspace(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    settings = load_settings()
    assert settings.settings_path == tmp_path / ".wr-settings.json"
    assert resolve_db_path(settings) == tmp_path / "data" / "wr.sqlite"
    assert settings.household == HouseholdSettings()


def test_settings_persist_all_options_across_updates(tmp_path):
    settings = Settings(project_root=tmp_path, db_path=Path("state/results.sqlite"),
                        institution_options={"broker": {"linked_account": "NL00 TEST 0000 0000 00"}})
    save_settings(settings, HouseholdSettings(identities=(TaxpayerIdentity(name="Sophie de Vries", position=TaxpayerPosition.PRIMARY, aliases=("S. de Vries",)),)), "documents")
    loaded = load_settings(tmp_path)
    assert loaded.resolved_db_path == tmp_path / "state" / "results.sqlite"
    assert loaded.household.secondary is None
    save_settings(loaded, import_root="other-documents")
    reloaded = load_settings(tmp_path)
    assert reloaded.household == loaded.household
    assert reloaded.institution_options == settings.institution_options
    assert reloaded.import_root == Path("other-documents")
    assert reloaded.db_path == settings.db_path


def test_legacy_settings_are_migrated_once_and_then_ignored(tmp_path):
    legacy = tmp_path / "config.toml"
    legacy.write_text(
        'import_root = "statements"\n'
        'db_path = "state/results.sqlite"\n'
        '[partners]\npartner_a = "Alex Example"\n'
        'partner_a_aliases = ["A. Example"]\n'
        '[institutions.broker]\nlinked_account = "NL00 TEST 0000 0000 00"\n'
    )
    settings = load_settings(tmp_path)
    assert settings.import_root == Path("statements")
    assert settings.resolved_db_path == tmp_path / "state" / "results.sqlite"
    assert settings.household.primary.name == "Alex Example"
    assert settings.institution_options["broker"].model_dump() == {"linked_account": "NL00 TEST 0000 0000 00"}
    assert settings.settings_path.is_file()
    legacy.write_text("invalid and retired TOML")
    assert load_settings(tmp_path) == settings


def test_migration_preserves_existing_ui_overrides(tmp_path):
    (tmp_path / "config.toml").write_text('db_path = "custom.sqlite"\n[partners]\npartner_a = "Legacy Person"\n[institutions.flatex]\nlinked_account = "NL00TEST0000000000"\n')
    (tmp_path / ".wr-settings.json").write_text(json.dumps({"partners": {}, "import_root": None}))
    settings = load_settings(tmp_path)
    assert settings.household == HouseholdSettings()
    assert settings.import_root is None
    assert settings.db_path == Path("custom.sqlite")
    assert settings.institution_options["flatex"].linked_account == "NL00TEST0000000000"
    assert json.loads(settings.settings_path.read_text())["version"] == 3


def test_workspace_must_be_a_directory(tmp_path):
    file = tmp_path / "not-a-workspace"
    file.touch()
    with pytest.raises(ValueError, match="Workspace must be a directory"):
        load_settings(file)


def test_import_with_root_does_not_require_configuration(monkeypatch, tmp_path):
    statements = tmp_path / "statements"
    statements.mkdir()
    monkeypatch.chdir(tmp_path)

    exit_code = main(["import", "--root", str(statements)])

    assert exit_code == 0
    assert (tmp_path / "data" / "wr.sqlite").is_file()


def test_import_returns_a_structured_report(tmp_path):
    statements = tmp_path / "statements"
    statements.mkdir()

    report = run_import(statements, tmp_path / "result.sqlite")

    assert isinstance(report, ImportReport)
    assert report.seen == 0
    assert report.outcomes == []


def test_parser_receives_institution_options():
    text = (
        "flatex Bank AG\n"
        "Rekeninguittreksel nr: 001/2020\n"
        "Rekeningnummer: 1000000000\n"
        "Oud saldo van 05.02.2020 in EUR 0,00+\n"
        "06.02. 06.02. Überweisung 5.000,00+\n"
        "NL00 TEST 0000 0000 00\n"
        "Nieuw saldo 31.12.2020 Nr. 001/2020 valuta EUR 5.000,00+\n"
    )

    result = parse_document(
        "flatex",
        "account_statement",
        text,
        2020,
        institution_options={
            "flatex": {"linked_account": "NL00 TEST 0000 0000 00"}
        },
    )

    assert result.facts[0].deposits == 5000.0


def test_cli_uses_ui_settings_from_selected_workspace(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    documents = workspace / "statements"
    documents.mkdir()
    save_settings(Settings(project_root=workspace, db_path=Path("custom.sqlite")), import_root="statements")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    assert main(["--workspace", str(workspace), "import"]) == 0
    assert (workspace / "custom.sqlite").is_file()
    assert not (elsewhere / "data" / "wr.sqlite").exists()


def test_dashboard_and_demo_launch_with_workspace_settings(tmp_path, monkeypatch):
    calls = []

    def launch(workspace, port):
        settings = load_settings(workspace)
        calls.append((workspace, port, settings))
        assert not (workspace / "config.toml").exists()
        return 0

    monkeypatch.setattr("wr.cli._launch_dashboard", launch)
    assert main(["--workspace", str(tmp_path), "dashboard", "--port", "8502"]) == 0
    assert calls[0][:2] == (tmp_path, 8502)
    assert main(["demo", "--port", "8503"]) == 0
    assert calls[1][1] == 8503
    assert calls[1][2].household.primary.name == "Sophie de Vries"
    assert not calls[1][0].exists()


def test_fresh_import_with_invalid_folder_preserves_database(tmp_path):
    database = tmp_path / "data" / "wr.sqlite"
    database.parent.mkdir()
    database.write_bytes(b"existing database")
    assert main(["--workspace", str(tmp_path), "import", "--fresh", "--root", str(tmp_path / "missing")]) == 2
    assert database.read_bytes() == b"existing database"


def test_settings_validation_rejects_invalid_version_and_institution_shape(tmp_path):
    path = tmp_path / ".wr-settings.json"
    path.write_text(json.dumps({"version": 999}))
    with pytest.raises(ValueError, match="version"):
        load_settings(tmp_path)
    path.write_text(json.dumps({"version": 2, "institutions": {"flatex": "invalid"}}))
    with pytest.raises(ValueError, match="institutions.flatex must be an object"):
        load_settings(tmp_path)
