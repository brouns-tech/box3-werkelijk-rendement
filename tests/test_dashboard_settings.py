from pathlib import Path

from streamlit.testing.v1 import AppTest

from wr.config import load_settings


APP = Path(__file__).resolve().parents[1] / "dashboard" / "app.py"


def taxpayer_input(app, field):
    widgets = app.text_area if field.startswith("aliases_") else app.text_input
    return next(widget for widget in widgets if widget.key.endswith(f"_{field}"))


def test_settings_can_be_saved_before_first_import(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    app = AppTest.from_file(str(APP)).run()
    assert not app.exception
    taxpayer_input(app, "canonical_a").set_value("Sophie de Vries")
    taxpayer_input(app, "aliases_a").set_value("Fie\nS. de Vries")
    app.button(key="save_settings").click().run()
    assert not app.exception
    assert load_settings().partners.partner_a == "Sophie de Vries"
    assert load_settings().partners.partner_a_aliases == ("Fie", "S. de Vries")
    restarted = AppTest.from_file(str(APP)).run()
    assert not restarted.exception
    assert taxpayer_input(restarted, "canonical_a").value == "Sophie de Vries"
    assert restarted.button(key="import_documents").disabled


def test_detected_name_assignment_updates_results_and_survives_restart(tmp_path, monkeypatch):
    from wr.db import connect
    from wr.demo import create_demo_workspace

    create_demo_workspace(tmp_path)
    monkeypatch.chdir(tmp_path)
    cfg = load_settings()
    with connect(cfg.resolved_db_path) as conn:
        conn.execute("UPDATE account_year_facts SET holder_names = '[\"Fie\"]' WHERE account_key = 'NL22RABO0002345678'")
    app = AppTest.from_file(str(APP)).run()
    assert not app.exception
    nickname = next(select for select in app.selectbox if select.label == "Fie")
    assert nickname.value == "unassigned"
    nickname.set_value("a")
    taxpayer_input(app, "canonical_a").set_value("Sophie Example")
    app.button(key="save_settings").click().run()
    assert not app.exception
    assert load_settings().partners.partner_a == "Sophie Example"
    assert "Fie" in load_settings().partners.partner_a_aliases
    with connect(cfg.resolved_db_path) as conn:
        row = conn.execute("SELECT partner_name FROM partner_tax_results WHERE partner = 'a'").fetchone()
        assert row[0] == "Sophie Example"
        holders = conn.execute("SELECT holder_names FROM account_year_facts WHERE account_key = 'NL22RABO0002345678'").fetchone()[0]
        assert holders == '["Fie"]'
    restarted = AppTest.from_file(str(APP)).run()
    assert not restarted.exception
    assert next(select for select in restarted.selectbox if select.label == "Fie").value == "a"
    next(select for select in restarted.selectbox if select.label == "Fie").set_value("unassigned")
    restarted.button(key="save_settings").click().run()
    assert not restarted.exception
    assert "Fie" in load_settings().partners.unassigned_names


def test_document_folder_controls_are_in_documents_tab(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    app = AppTest.from_file(str(APP)).run()
    assert not app.exception
    assert [tab.label for tab in app.tabs] == ["Overview", "Documents", "Taxpayers", "Settings"]
    assert app.tabs[1].button(key="import_documents").disabled
    assert app.tabs[1].text_input(key="document_folder").label == "Document folder"
    assert [button.label for button in app.tabs[1].button] == ["Save folder", "🗂️ Browse Folders", "Import documents"]
    assert taxpayer_input(app.tabs[2], "canonical_a").label == "Canonical name"
    assert not app.tabs[2].button(key="save_settings").disabled
    assert not app.tabs[0].text_input
    assert not app.get("file_uploader")


def test_folder_import_recurses_deduplicates_and_refreshes_identities(tmp_path, monkeypatch):
    from wr.db import connect

    monkeypatch.chdir(tmp_path)
    folder = tmp_path / "statements"
    nested = folder / "2023"
    nested.mkdir(parents=True)
    source = nested / "annual.PDF"
    source.write_bytes(b"synthetic PDF")
    text = """Jaaroverzicht 2023
ING Betaalrekening: NL00 INGB 0000 0000 00 Mevr. Sophie de Vries
Saldo op 01-01-2023 900,00
Saldo op 31-12-2023 2.318,06
"""
    monkeypatch.setattr("wr.import_pipeline.extract_text", lambda path: (text, 1))
    app = AppTest.from_file(str(APP)).run()
    app.text_input(key="document_folder").set_value(str(folder)).run()
    app.button(key="import_documents").click().run()
    assert not app.exception
    assert any("1 parsed" in info.value for info in app.info)
    assert taxpayer_input(app, "canonical_a").value == "Sophie de Vries"
    with connect(load_settings().resolved_db_path) as conn:
        document = conn.execute("SELECT * FROM documents").fetchone()
        assert document["first_seen_path"] == str(source)
        assert conn.execute("SELECT COUNT(*) FROM account_year_facts").fetchone()[0] == 1
    assert load_settings().import_root == folder
    restarted = AppTest.from_file(str(APP)).run()
    assert restarted.text_input(key="document_folder").value == str(folder)
    restarted.button(key="import_documents").click().run()
    assert not restarted.exception
    assert any("1 duplicates" in info.value for info in restarted.info)


def test_assignment_options_show_canonical_names_and_update_on_rename(tmp_path, monkeypatch):
    from wr.demo import create_demo_workspace

    create_demo_workspace(tmp_path)
    monkeypatch.chdir(tmp_path)
    app = AppTest.from_file(str(APP)).run()
    assert not app.exception
    spelling = next(select for select in app.selectbox if select.label == "Sophie de Vries")
    assert spelling.options == ["Unassigned", "Sophie de Vries", "Daan Jansen"]
    taxpayer_input(app, "canonical_a").set_value("Sophie Example").run()
    assert not app.exception
    spelling = next(select for select in app.selectbox if select.label == "Sophie de Vries")
    assert spelling.options == ["Unassigned", "Sophie Example", "Daan Jansen"]
    assert spelling.value == "a"
    app.button(key="save_settings").click().run()
    assert not app.exception
    assert load_settings().partners.partner_a == "Sophie Example"


def test_folder_path_saves_without_changing_taxpayers(tmp_path, monkeypatch):
    from wr.config import PartnerSettings, save_settings

    monkeypatch.chdir(tmp_path)
    folder = tmp_path / "statements"
    folder.mkdir()
    partners = PartnerSettings(partner_a="Sophie de Vries", partner_a_aliases=("Fie",))
    save_settings(load_settings(), partners, "")
    app = AppTest.from_file(str(APP)).run()
    app.text_input(key="document_folder").set_value(str(folder))
    assert app.text_input(key="document_folder").value == str(folder)
    app.button(key="save_folder").click().run()
    assert not app.exception
    assert load_settings().import_root == folder
    assert load_settings().partners == partners
    restarted = AppTest.from_file(str(APP)).run()
    assert restarted.text_input(key="document_folder").value == str(folder)
    taxpayer_input(restarted, "canonical_a").set_value("Sophie Example")
    restarted.button(key="save_settings").click().run()
    assert load_settings().import_root == folder


def test_invalid_folder_preserves_saved_path(tmp_path, monkeypatch):
    from wr.config import PartnerSettings, save_settings

    monkeypatch.chdir(tmp_path)
    save_settings(load_settings(), PartnerSettings(), str(tmp_path))
    app = AppTest.from_file(str(APP)).run()
    missing = str(tmp_path / "missing")
    app.text_input(key="document_folder").set_value(missing)
    app.button(key="save_folder").click().run()
    assert not app.exception
    assert any("does not exist" in error.value for error in app.error)
    assert load_settings().import_root == tmp_path
    app.button(key="import_documents").click().run()
    assert any("does not exist" in error.value for error in app.error)
    assert app.text_input(key="document_folder").value == missing
    assert load_settings().import_root == tmp_path


def test_relative_and_home_folder_paths_are_resolved(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    folder = tmp_path / "statements"
    folder.mkdir()
    app = AppTest.from_file(str(APP)).run()
    app.text_input(key="document_folder").set_value("statements")
    app.button(key="save_folder").click().run()
    assert not app.exception
    assert load_settings().import_root == folder
    app.text_input(key="document_folder").set_value("~")
    app.button(key="save_folder").click().run()
    assert not app.exception
    assert load_settings().import_root == Path.home()


def test_explorer_selection_fills_field_and_allows_manual_override(tmp_path, monkeypatch):
    from unittest.mock import patch

    monkeypatch.chdir(tmp_path)
    folder = tmp_path / "statements"
    folder.mkdir()
    other = tmp_path / "other"
    other.mkdir()
    # Selection and automatic saving each rerun the page before normal rendering.
    with patch("dashboard.folder_picker.DirPicker", side_effect=[str(folder), None, None]) as picker:
        app = AppTest.from_file(str(APP)).run()
    assert not app.exception
    assert app.text_input(key="document_folder").value == str(folder)
    assert picker.call_args.kwargs["start_path"] == str(folder)
    assert load_settings().import_root == folder
    app.text_input(key="document_folder").set_value(str(other)).run()
    assert not app.exception
    assert app.text_input(key="document_folder").value == str(other)
    app.button(key="save_folder").click().run()
    assert load_settings().import_root == other
    with patch("dashboard.folder_picker.DirPicker", side_effect=[str(folder), None, None]):
        app.run()
    assert app.text_input(key="document_folder").value == str(folder)
    assert load_settings().import_root == folder


def test_explorer_dialog_navigates_selects_and_cancels(tmp_path, monkeypatch, caplog):
    import streamlit as st
    from streamlit.elements.lib import policies

    monkeypatch.setattr(policies, "_shown_default_value_warning", False)

    # AppTest runs full scripts rather than browser-triggered fragment reruns.
    # Exercise the actual dialog and navigation using full reruns in this test.
    rerun = st.rerun
    monkeypatch.setattr("streamlit_explorer.st.rerun", lambda **kwargs: rerun())
    monkeypatch.chdir(tmp_path)
    folder = tmp_path / "statements"
    folder.mkdir()
    app = AppTest.from_file(str(APP)).run()
    next(button for button in app.button if "Browse Folders" in button.label).click().run()
    assert not app.exception
    assert app.get("dialog")
    next(button for button in app.button if button.label == "📂 statements").click().run()
    assert not app.exception
    next(button for button in app.button if button.label == "✅ Select").click().run()
    assert not app.exception
    assert app.text_input(key="document_folder").value == str(folder)
    assert load_settings().import_root == folder
    next(button for button in app.button if "Browse Folders" in button.label).click().run()
    next(button for button in app.button if button.label == "⬆️ Up (Parent Folder)").click().run()
    assert not app.exception
    next(button for button in app.button if button.label == "⬅️ Back").click().run()
    assert not app.exception
    next(button for button in app.button if button.label == "❌ Cancel").click().run()
    assert not app.exception
    assert app.text_input(key="document_folder").value == str(folder)
    assert not any("created with a default value" in record.getMessage() for record in caplog.records)


def test_reset_requires_confirmation_and_refreshes_the_workspace(tmp_path, monkeypatch):
    from wr.db import connect
    from wr.demo import create_demo_workspace

    create_demo_workspace(tmp_path)
    monkeypatch.chdir(tmp_path)
    cfg = load_settings()
    app = AppTest.from_file(str(APP)).run()
    app.text_input(key="document_folder").set_value(str(tmp_path)).run()
    app.button(key="save_folder").click().run()
    app.button(key="reset_workspace").click().run()
    assert not app.exception
    with connect(cfg.resolved_db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0] > 0
    app.button(key="cancel_reset_workspace").click().run()
    assert not app.exception
    assert load_settings().partners.partner_a == "Sophie de Vries"
    assert load_settings().import_root == tmp_path

    app.button(key="reset_workspace").click().run()
    app.button(key="confirm_reset_workspace").click().run()
    assert not app.exception
    assert any("Workspace reset" in message.value for message in app.success)
    assert taxpayer_input(app, "canonical_a").value == ""
    assert taxpayer_input(app, "canonical_b").value == ""
    assert app.text_input(key="document_folder").value == ""
    assert app.button(key="import_documents").disabled
    assert load_settings().partners.partner_a is None
    assert load_settings().import_root is None
    with connect(cfg.resolved_db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM partner_tax_results").fetchone()[0] == 0
    restarted = AppTest.from_file(str(APP)).run()
    assert not restarted.exception
    assert taxpayer_input(restarted, "canonical_a").value == ""
    assert restarted.text_input(key="document_folder").value == ""


def test_storage_and_institution_options_persist_across_tabs_and_sessions(tmp_path, monkeypatch):
    from wr.db import connect
    from wr.demo import create_demo_workspace

    create_demo_workspace(tmp_path)
    monkeypatch.chdir(tmp_path)
    cfg = load_settings()
    app = AppTest.from_file(str(APP)).run()
    assert app.tabs[3].text_input(key="database_file").value == "wr-demo.sqlite"
    app.text_input(key="database_file").set_value("data/new.sqlite")
    app.text_input(key="institution_flatex_linked_account").set_value("NL00 TEST 0000 0000 00")
    app.button(key="save_workspace_settings").click().run()
    assert not app.exception
    loaded = load_settings()
    assert loaded.db_path == Path("data/new.sqlite")
    assert loaded.institution_options == {"flatex": {"linked_account": "NL00 TEST 0000 0000 00"}}
    assert loaded.partners == cfg.partners
    assert loaded.resolved_db_path.is_file()
    with connect(cfg.resolved_db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0] > 0
    app.text_input(key="document_folder").set_value(str(tmp_path))
    app.button(key="save_folder").click().run()
    taxpayer_input(app, "canonical_a").set_value("Sophie Example")
    app.button(key="save_settings").click().run()
    assert not app.exception
    assert load_settings().db_path == loaded.db_path
    assert load_settings().institution_options == loaded.institution_options
    restarted = AppTest.from_file(str(APP)).run()
    assert not restarted.exception
    assert restarted.text_input(key="database_file").value == "data/new.sqlite"
    assert restarted.text_input(key="institution_flatex_linked_account").value == "NL00 TEST 0000 0000 00"
    assert restarted.text_input(key="document_folder").value == str(tmp_path)
    assert taxpayer_input(restarted, "canonical_a").value == "Sophie Example"


def test_taxpayer_fields_refresh_through_repeated_reset_and_import_without_reload(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    folder = tmp_path / "documents"
    folder.mkdir()
    (folder / "full.pdf").write_bytes(b"full")
    (folder / "initials.pdf").write_bytes(b"initials")

    def extract(path):
        name = "Sophie de Vries" if path.stem == "full" else "S. de Vries"
        return (
            f"Jaaroverzicht 2023\nING Betaalrekening: NL00 INGB 0000 0000 00 Mevr. {name}\n"
            "Saldo op 01-01-2023 900,00\nSaldo op 31-12-2023 2.318,06\n",
            1,
        )

    monkeypatch.setattr("wr.import_pipeline.extract_text", extract)
    app = AppTest.from_file(str(APP)).run()
    seen_keys = set()
    for _ in range(2):
        before_import = {widget.key for widget in (*app.tabs[2].text_input, *app.tabs[2].text_area)}
        app.text_input(key="document_folder").set_value(str(folder)).run()
        app.button(key="import_documents").click().run()
        assert not app.exception
        assert taxpayer_input(app, "canonical_a").value == "Sophie de Vries"
        assert taxpayer_input(app, "aliases_a").value == "S. de Vries"
        imported_keys = {widget.key for widget in (*app.tabs[2].text_input, *app.tabs[2].text_area)}
        assert imported_keys.isdisjoint(before_import | seen_keys)
        seen_keys.update(imported_keys)
        # Ordinary reruns preserve the user's unsaved corrections.
        taxpayer_input(app, "canonical_a").set_value("Unsaved taxpayer").run()
        taxpayer_input(app, "aliases_a").set_value("Unsaved nickname").run()
        app.run()
        assert taxpayer_input(app, "canonical_a").value == "Unsaved taxpayer"
        assert taxpayer_input(app, "aliases_a").value == "Unsaved nickname"
        app.button(key="reset_workspace").click().run()
        app.button(key="confirm_reset_workspace").click().run()
        assert not app.exception
        assert all(widget.value == "" for widget in (*app.tabs[2].text_input, *app.tabs[2].text_area))
        reset_keys = {widget.key for widget in (*app.tabs[2].text_input, *app.tabs[2].text_area)}
        assert reset_keys.isdisjoint(seen_keys)
        seen_keys.update(reset_keys)
        assert not app.tabs[2].selectbox


def test_alias_assignments_save_and_recompute_immediately(tmp_path, monkeypatch):
    from wr.db import connect
    from wr.demo import create_demo_workspace

    create_demo_workspace(tmp_path)
    monkeypatch.chdir(tmp_path)
    cfg = load_settings()
    with connect(cfg.resolved_db_path) as conn:
        conn.execute("DELETE FROM account_year_facts WHERE account_key != 'NL22RABO0002345678'")
        conn.execute("UPDATE account_year_facts SET holder_names = '[\"Fie\"]'")
        conn.execute("UPDATE tax_returns SET full_year_fiscal_partners = 0")
    app = AppTest.from_file(str(APP)).run()
    assert not app.exception

    def actual_return(slot):
        with connect(cfg.resolved_db_path) as conn:
            return conn.execute("SELECT allocated_actual_return FROM partner_tax_results WHERE partner = ?", (slot,)).fetchone()[0]

    assert actual_return("a") is None
    next(select for select in app.selectbox if select.label == "Fie").set_value("a").run()
    assert not app.exception
    assert "Fie" in load_settings().partners.partner_a_aliases
    assert "Fie" in taxpayer_input(app, "aliases_a").value
    assert actual_return("a") == 540

    next(select for select in app.selectbox if select.label == "Fie").set_value("b").run()
    assert not app.exception
    assert "Fie" not in load_settings().partners.partner_a_aliases
    assert "Fie" in load_settings().partners.partner_b_aliases
    assert actual_return("a") is None
    assert actual_return("b") == 540

    next(select for select in app.selectbox if select.label == "Fie").set_value("unassigned").run()
    assert not app.exception
    assert "Fie" in load_settings().partners.unassigned_names
    assert "Fie" not in load_settings().partners.partner_b_aliases
    assert actual_return("b") is None
    restarted = AppTest.from_file(str(APP)).run()
    assert next(select for select in restarted.selectbox if select.label == "Fie").value == "unassigned"
