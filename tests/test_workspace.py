import pytest


from wr.models.identities import HouseholdSettings
from wr.workspace.settings import load_settings, save_settings
from wr.storage.migrations import SCHEMA_VERSION
from wr.storage.connection import connect
from wr.demo import create_demo_workspace
from wr.workspace.reset import reset_workspace


TABLES = ("documents", "account_year_facts", "tax_returns", "yearly_portfolio", "taxpayer_tax_results")


def test_reset_clears_data_and_profiles_without_removing_source_files(tmp_path):
    workspace = create_demo_workspace(tmp_path)
    cfg = load_settings(workspace)
    source = tmp_path / "documents" / "original.pdf"
    source.parent.mkdir()
    source.write_bytes(b"original statement")
    export = tmp_path / "audit.zip"
    export.write_bytes(b"saved audit export")
    save_settings(cfg, cfg.household, str(source.parent), institution_options={"flatex": {"linked_account": "NL00TEST0000000000"}})
    with connect(cfg.resolved_db_path) as conn:
        assert all(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in TABLES)

    reset_workspace(load_settings(workspace))

    with connect(cfg.resolved_db_path) as conn:
        assert all(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0 for table in TABLES)
        assert conn.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0] == SCHEMA_VERSION
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    assert load_settings(workspace).household == HouseholdSettings()
    assert load_settings(workspace).import_root is None
    assert load_settings(workspace).institution_options == {}
    assert load_settings(workspace).db_path == cfg.db_path
    assert source.read_bytes() == b"original statement"
    assert export.read_bytes() == b"saved audit export"
    assert not (workspace / "config.toml").exists()
    reset_workspace(load_settings(workspace))
    assert load_settings(workspace).household == HouseholdSettings()


def test_reset_rolls_back_database_if_settings_cannot_be_saved(tmp_path, monkeypatch):
    workspace = create_demo_workspace(tmp_path)
    cfg = load_settings(workspace)
    with connect(cfg.resolved_db_path) as conn:
        before = {table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in TABLES}

    def fail_save(*args, **kwargs):
        raise OSError("Settings are read-only")

    monkeypatch.setattr("wr.workspace.reset.save_settings", fail_save)
    with pytest.raises(OSError, match="read-only"):
        reset_workspace(cfg)
    with connect(cfg.resolved_db_path) as conn:
        after = {table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in TABLES}
    assert after == before
    assert load_settings(workspace).household == cfg.household


def test_reset_does_not_restore_retired_toml_profiles(tmp_path):
    (tmp_path / "config.toml").write_text('[partners]\npartner_a = "Retired Person"\n')
    settings = load_settings(tmp_path)
    assert settings.household.primary.name == "Retired Person"
    reset_workspace(settings)
    assert load_settings(tmp_path).household == HouseholdSettings()
