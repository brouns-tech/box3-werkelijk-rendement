from pathlib import Path

from streamlit.testing.v1 import AppTest

from wr.config import load_config


APP = Path(__file__).resolve().parents[1] / "dashboard" / "app.py"


def test_settings_can_be_saved_before_first_import(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    app = AppTest.from_file(str(APP)).run()
    assert not app.exception
    app.text_input(key="canonical_a").set_value("Sophie de Vries")
    app.text_area(key="aliases_a").set_value("Fie\nS. de Vries")
    app.button(key="save_settings").click().run()
    assert not app.exception
    assert load_config().partners.partner_a == "Sophie de Vries"
    assert load_config().partners.partner_a_aliases == ("Fie", "S. de Vries")
    restarted = AppTest.from_file(str(APP)).run()
    assert not restarted.exception
    assert restarted.text_input(key="canonical_a").value == "Sophie de Vries"
    assert restarted.button(key="import_documents").disabled


def test_detected_name_assignment_updates_results_and_survives_restart(tmp_path, monkeypatch):
    from wr.db import connect
    from wr.demo import create_demo_workspace

    create_demo_workspace(tmp_path)
    monkeypatch.chdir(tmp_path)
    cfg = load_config()
    with connect(cfg.resolved_db_path) as conn:
        conn.execute("UPDATE account_year_facts SET holder_names = '[\"Fie\"]' WHERE account_key = 'NL22RABO0002345678'")
    app = AppTest.from_file(str(APP)).run()
    assert not app.exception
    nickname = next(select for select in app.selectbox if select.label == "Fie")
    assert nickname.value == "unassigned"
    nickname.set_value("a")
    app.text_input(key="canonical_a").set_value("Sophie Example")
    app.button(key="save_settings").click().run()
    assert not app.exception
    assert load_config().partners.partner_a == "Sophie Example"
    assert "Fie" in load_config().partners.partner_a_aliases
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
    assert "Fie" in load_config().partners.unassigned_names


def test_document_folder_controls_are_in_documents_tab(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    app = AppTest.from_file(str(APP)).run()
    assert not app.exception
    assert [tab.label for tab in app.tabs] == ["Overview", "Documents", "Taxpayers"]
    assert app.tabs[1].button(key="import_documents").disabled
    assert app.tabs[1].text_input(key="document_folder").label == "Document folder"
    assert [button.label for button in app.tabs[1].button] == ["Save folder", "🗂️ Browse Folders", "Import documents"]
    assert app.tabs[2].text_input(key="canonical_a").label == "Canonical name"
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
    assert app.text_input(key="canonical_a").value == "Sophie de Vries"
    with connect(load_config().resolved_db_path) as conn:
        document = conn.execute("SELECT * FROM documents").fetchone()
        assert document["first_seen_path"] == str(source)
        assert conn.execute("SELECT COUNT(*) FROM account_year_facts").fetchone()[0] == 1
    assert load_config().import_root == folder
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
    app.text_input(key="canonical_a").set_value("Sophie Example").run()
    assert not app.exception
    spelling = next(select for select in app.selectbox if select.label == "Sophie de Vries")
    assert spelling.options == ["Unassigned", "Sophie Example", "Daan Jansen"]
    assert spelling.value == "a"
    app.button(key="save_settings").click().run()
    assert not app.exception
    assert load_config().partners.partner_a == "Sophie Example"


def test_folder_path_saves_without_changing_taxpayers(tmp_path, monkeypatch):
    from wr.config import PartnerSettings, save_settings

    monkeypatch.chdir(tmp_path)
    folder = tmp_path / "statements"
    folder.mkdir()
    partners = PartnerSettings(partner_a="Sophie de Vries", partner_a_aliases=("Fie",))
    save_settings(load_config(), partners, "")
    app = AppTest.from_file(str(APP)).run()
    app.text_input(key="document_folder").set_value(str(folder))
    assert app.text_input(key="document_folder").value == str(folder)
    app.button(key="save_folder").click().run()
    assert not app.exception
    assert load_config().import_root == folder
    assert load_config().partners == partners
    restarted = AppTest.from_file(str(APP)).run()
    assert restarted.text_input(key="document_folder").value == str(folder)
    restarted.text_input(key="canonical_a").set_value("Sophie Example")
    restarted.button(key="save_settings").click().run()
    assert load_config().import_root == folder


def test_invalid_folder_preserves_saved_path(tmp_path, monkeypatch):
    from wr.config import PartnerSettings, save_settings

    monkeypatch.chdir(tmp_path)
    save_settings(load_config(), PartnerSettings(), str(tmp_path))
    app = AppTest.from_file(str(APP)).run()
    missing = str(tmp_path / "missing")
    app.text_input(key="document_folder").set_value(missing)
    app.button(key="save_folder").click().run()
    assert not app.exception
    assert any("does not exist" in error.value for error in app.error)
    assert load_config().import_root == tmp_path
    app.button(key="import_documents").click().run()
    assert any("does not exist" in error.value for error in app.error)
    assert app.text_input(key="document_folder").value == missing
    assert load_config().import_root == tmp_path


def test_relative_and_home_folder_paths_are_resolved(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    folder = tmp_path / "statements"
    folder.mkdir()
    app = AppTest.from_file(str(APP)).run()
    app.text_input(key="document_folder").set_value("statements")
    app.button(key="save_folder").click().run()
    assert not app.exception
    assert load_config().import_root == folder
    app.text_input(key="document_folder").set_value("~")
    app.button(key="save_folder").click().run()
    assert not app.exception
    assert load_config().import_root == Path.home()


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
    assert load_config().import_root == folder
    app.text_input(key="document_folder").set_value(str(other)).run()
    assert not app.exception
    assert app.text_input(key="document_folder").value == str(other)
    app.button(key="save_folder").click().run()
    assert load_config().import_root == other
    with patch("dashboard.folder_picker.DirPicker", side_effect=[str(folder), None, None]):
        app.run()
    assert app.text_input(key="document_folder").value == str(folder)
    assert load_config().import_root == folder


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
    assert load_config().import_root == folder
    next(button for button in app.button if "Browse Folders" in button.label).click().run()
    next(button for button in app.button if button.label == "⬆️ Up (Parent Folder)").click().run()
    assert not app.exception
    next(button for button in app.button if button.label == "⬅️ Back").click().run()
    assert not app.exception
    next(button for button in app.button if button.label == "❌ Cancel").click().run()
    assert not app.exception
    assert app.text_input(key="document_folder").value == str(folder)
    assert not any("created with a default value" in record.getMessage() for record in caplog.records)
