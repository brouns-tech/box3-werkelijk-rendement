from pathlib import Path

from streamlit.testing.v1 import AppTest

from wr.config import load_settings


APP = Path(__file__).resolve().parents[1] / "dashboard" / "app.py"


def test_pre_filing_partnership_checkbox_persists_and_updates_overview(tmp_path, monkeypatch):
    from wr.db import connect
    from wr.demo import create_demo_workspace

    create_demo_workspace(tmp_path)
    monkeypatch.chdir(tmp_path)
    cfg = load_settings()
    with connect(cfg.resolved_db_path) as conn:
        conn.execute('DELETE FROM tax_returns')
    app = AppTest.from_file(str(APP)).run()
    assert not app.exception
    checkbox = next(widget for widget in app.checkbox if widget.key.endswith('_assume_fiscal_partnership'))
    assert checkbox.value is True
    decision = next(table.value for table in app.dataframe if 'Taxpayer' in table.value.columns)
    assert decision['Decision'].tolist() == ['Pre-filing', 'Pre-filing']
    for field in ['Tax allocation', 'Allocated actual return', 'Fictitious return', 'Potential tax savings']:
        assert decision[field].tolist() == ['—', '—']
    assert all(value != '—' for value in decision['Statement return by holder'])
    assert any('Pre-filing overview' in info.value for info in app.info)
    effective = next(table.value for table in app.dataframe if 'Effective return (EUR)' in table.value.columns)['Effective return (EUR)'].tolist()
    checkbox.uncheck().run()
    assert not app.exception
    assert load_settings().partners.assume_fiscal_partnership is False
    assert next(table.value for table in app.dataframe if 'Effective return (EUR)' in table.value.columns)['Effective return (EUR)'].tolist() == effective
    decision = next(table.value for table in app.dataframe if 'Taxpayer' in table.value.columns)
    assert all(value != '—' for value in decision['Allocated actual return'])
    restarted = AppTest.from_file(str(APP)).run()
    assert not next(widget for widget in restarted.checkbox if widget.key.endswith('_assume_fiscal_partnership')).value


def test_initial_variants_are_assigned_and_labeled_without_manual_assignments(tmp_path, monkeypatch):
    from dataclasses import replace
    from dashboard.app import _canonical_name_map, _holder_label
    from wr.config import save_settings
    from wr.db import connect
    from wr.demo import create_demo_workspace

    create_demo_workspace(tmp_path)
    monkeypatch.chdir(tmp_path)
    cfg = load_settings()
    partners = replace(cfg.partners, partner_a_aliases=("ABC Example",))
    save_settings(cfg, partners)
    holders = '["A.B.C. EXAMPLE", "A B C Example"]'
    with connect(cfg.resolved_db_path) as conn:
        conn.execute("UPDATE account_year_facts SET holder_names = ? WHERE account_key = 'NL22RABO0002345678'", (holders,))
    app = AppTest.from_file(str(APP)).run()
    assert not app.exception
    for name in ("A.B.C. EXAMPLE", "A B C Example"):
        assert next(widget for widget in app.selectbox if widget.label == name).value == "a"
    assert load_settings().partners == partners
    assert _holder_label(holders, _canonical_name_map(partners)) == partners.partner_a


def test_empty_assignment_does_not_crash_or_change_existing_ownership(tmp_path, monkeypatch):
    from wr.demo import create_demo_workspace
    from wr.identities import identity_slot
    create_demo_workspace(tmp_path)
    monkeypatch.chdir(tmp_path)
    app = AppTest.from_file(str(APP)).run()
    assignment = next(widget for widget in app.selectbox if "_identity_" in (widget.key or ""))
    name, original_slot = assignment.label, assignment.value
    assignment.set_value(None).run()
    assert not app.exception
    assert identity_slot(name, load_settings().partners) == original_slot


def taxpayer_input(app, field):
    widgets = app.text_area if field.startswith("aliases_") else app.text_input
    return next(widget for widget in widgets if widget.key.endswith(f"_{field}"))


def save_taxpayer_edits(app):
    app.run()
    buttons = [button for button in app.button if button.key.startswith("save_field_")]
    if buttons:
        buttons[0].click().run()


def test_inline_save_and_discard_apply_to_all_drafts(tmp_path, monkeypatch):
    from wr.demo import create_demo_workspace

    create_demo_workspace(tmp_path)
    monkeypatch.chdir(tmp_path)
    app = AppTest.from_file(str(APP)).run()
    assert not any(button.key.startswith(("save_field_", "discard_field_")) for button in app.button)
    taxpayer_input(app, "canonical_a").set_value("Alex Example").run()
    taxpayer_input(app, "aliases_b").set_value("Other nickname").run()
    assert app.button(key="save_field_canonical_a").label == "✓"
    assert app.button(key="discard_field_aliases_b").label == "✕"
    assert load_settings().partners.partner_a == "Sophie de Vries"
    app.button(key="discard_field_aliases_b").click().run()
    assert not app.exception
    assert taxpayer_input(app, "canonical_a").value == "Sophie de Vries"
    assert taxpayer_input(app, "aliases_b").value == "D. Jansen"
    assert not any(button.key.startswith(("save_field_", "discard_field_")) for button in app.button)
    taxpayer_input(app, "canonical_a").set_value("Alex Example").run()
    taxpayer_input(app, "aliases_b").set_value("Other nickname").run()
    app.button(key="save_field_aliases_b").click().run()
    assert not app.exception
    assert load_settings().partners.partner_a == "Alex Example"
    assert "Other nickname" in load_settings().partners.partner_b_aliases


def test_delete_child_unassigns_documents_and_does_not_redetect(tmp_path, monkeypatch, caplog):
    from dataclasses import replace
    from types import SimpleNamespace
    from streamlit.elements.lib import policies
    from wr.config import ChildSettings, save_settings
    from wr.db import connect
    from wr.demo import create_demo_workspace

    create_demo_workspace(tmp_path)
    monkeypatch.chdir(tmp_path)
    cfg = load_settings()
    save_settings(cfg, replace(cfg.partners, children=(ChildSettings("Charlie Example", ("Charlie",)), ChildSettings("Robin Example"))))
    with connect(cfg.resolved_db_path) as conn:
        conn.execute("UPDATE account_year_facts SET holder_names = '[\"Charlie\"]' WHERE account_key = 'NL22RABO0002345678'")
    app = AppTest.from_file(str(APP)).run()
    taxpayer_input(app, "canonical_a").set_value("Unsaved parent").run()
    taxpayer_input(app, "canonical_child_1").set_value("Unsaved child").run()
    # AppTest has no server runtime, so enable the policy check locally to catch
    # the default/session-state warning emitted in the running dashboard.
    monkeypatch.setattr(policies, "runtime", SimpleNamespace(exists=lambda: True))
    monkeypatch.setattr(policies, "_shown_default_value_warning", False)
    caplog.clear()
    app.button(key="delete_child_0").click().run()
    assert not app.exception
    cfg = load_settings()
    assert [child.canonical_name for child in cfg.partners.children] == ["Robin Example"]
    assert {"Charlie Example", "Charlie"} <= set(cfg.partners.unassigned_names)
    assert next(select for select in app.selectbox if select.label == "Charlie").value == "unassigned"
    assert taxpayer_input(app, "canonical_child_0").value == "Unsaved child"
    assert taxpayer_input(app, "canonical_a").value == "Unsaved parent"
    assert cfg.partners.partner_a == "Sophie de Vries"
    app.button(key="add_child").click().run()
    assert taxpayer_input(app, "canonical_child_1").value == ""
    assert taxpayer_input(app, "canonical_child_0").value == "Unsaved child"
    assert not app.exception
    assert not any("was created with a default value" in record.getMessage() for record in caplog.records)
    restarted = AppTest.from_file(str(APP)).run()
    assert len([button for button in restarted.button if button.label == "Delete child"]) == 1
    with connect(cfg.resolved_db_path) as conn:
        assert conn.execute("SELECT holder_names FROM account_year_facts WHERE account_key = 'NL22RABO0002345678'").fetchone()[0] == '["Charlie"]'


def test_delete_unsaved_child_and_discard_new_child_draft(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    app = AppTest.from_file(str(APP)).run()
    app.button(key="add_child").click().run()
    taxpayer_input(app, "canonical_child_0").set_value("Charlie Example").run()
    app.button(key="add_child").click().run()
    taxpayer_input(app, "canonical_child_1").set_value("Robin Example").run()
    app.button(key="delete_child_0").click().run()
    assert not app.exception
    assert taxpayer_input(app, "canonical_child_1").value == "Robin Example"
    app.button(key="add_child").click().run()
    assert taxpayer_input(app, "canonical_child_2").value == ""
    app.button(key="discard_field_canonical_child_1").click().run()
    assert not app.exception
    assert not any(button.label == "Delete child" for button in app.button)
    assert load_settings().partners.children == ()


def test_child_columns_keep_half_width_and_section_headers_match(tmp_path, monkeypatch):
    from dataclasses import replace
    from wr.config import ChildSettings, save_settings
    from wr.demo import create_demo_workspace

    create_demo_workspace(tmp_path)
    monkeypatch.chdir(tmp_path)
    cfg = load_settings()
    save_settings(cfg, replace(cfg.partners, children=(ChildSettings("Charlie Example"),)))
    app = AppTest.from_file(str(APP)).run()
    assert [heading.value for heading in app.tabs[2].subheader] == [
        "Taxpayers", "Minor children (assets attributed to parents)", "Names found in documents",
    ]
    for count in (1, 2, 3):
        columns = app.tabs[2].get("column")
        child_columns = columns[2:]
        assert len(child_columns) == 2 * ((count + 1) // 2)
        assert all(column.proto.weight == 0.5 for column in child_columns)
        assert len(child_columns[-1].text_input) == (0 if count % 2 else 1)
        if count < 3:
            app.button(key="add_child").click().run()
        assert not app.exception


def test_children_dynamic_editor_assignments_and_purple_overview(tmp_path, monkeypatch):
    from dashboard.app import _canonical_name_map, _holder_label, _owner_colors, _owner_style
    from wr.config import ChildSettings, PartnerSettings, save_settings
    from wr.db import connect
    from wr.demo import create_demo_workspace

    create_demo_workspace(tmp_path)
    monkeypatch.chdir(tmp_path)
    cfg = load_settings()
    children = tuple(ChildSettings(f"Child {name} Example", (f"Nickname {name}",)) for name in ("Alpha", "Beta", "Gamma"))
    save_settings(cfg, PartnerSettings(partner_a=cfg.partners.partner_a, partner_b=cfg.partners.partner_b, children=children))
    with connect(cfg.resolved_db_path) as conn:
        conn.execute("UPDATE account_year_facts SET holder_names = '[\"Nickname Gamma\"]' WHERE account_key = 'NL22RABO0002345678'")
    app = AppTest.from_file(str(APP)).run()
    assert not app.exception
    assert taxpayer_input(app, "canonical_child_2").value == "Child Gamma Example"
    select = next(select for select in app.selectbox if select.label == "Nickname Gamma")
    assert select.value == "child_2"
    assert "Child Gamma Example" in select.options
    taxpayer_input(app, "canonical_child_2").set_value("Charlie Example").run()
    assert "Charlie Example" in next(select for select in app.selectbox if select.label == "Nickname Gamma").options
    save_taxpayer_edits(app)
    assert not app.exception
    cfg = load_settings()
    assert cfg.partners.children[2].canonical_name == "Charlie Example"
    assert _holder_label('["Nickname Gamma"]', _canonical_name_map(cfg.partners)) == "Charlie Example"
    colors = _owner_colors(cfg.partners, _canonical_name_map(cfg.partners))
    from dashboard.ownership import PURPLE, table_style
    assert _owner_style("Charlie Example", colors) == table_style(PURPLE)
    assert _owner_style("Nickname Gamma", colors) == table_style(PURPLE)
    account_table = next(table.value for table in app.dataframe if "Account holder" in table.value.columns)
    child_row = account_table[account_table["Account holder"] == "Charlie Example"].iloc[0]
    assert child_row["Allocation"] == "Joint"
    app.button(key="add_child").click().run()
    taxpayer_input(app, "canonical_child_3").set_value("Robin Example")
    save_taxpayer_edits(app)
    assert not app.exception
    assert len(load_settings().partners.children) == 4
    restarted = AppTest.from_file(str(APP)).run()
    assert taxpayer_input(restarted, "canonical_child_3").value == "Robin Example"


def test_settings_can_be_saved_before_first_import(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    app = AppTest.from_file(str(APP)).run()
    assert not app.exception
    taxpayer_input(app, "canonical_a").set_value("Sophie de Vries")
    taxpayer_input(app, "aliases_a").set_value("Fie\nS. de Vries")
    save_taxpayer_edits(app)
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
    save_taxpayer_edits(app)
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
    save_taxpayer_edits(restarted)
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
    assert not any(button.key.startswith("save_field_") for button in app.tabs[2].button)
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
    save_taxpayer_edits(app)
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
    save_taxpayer_edits(restarted)
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
    save_taxpayer_edits(app)
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


def test_overview_keeps_both_partners_when_combined_taxable_base_is_missing(tmp_path, monkeypatch):
    from wr.db import connect
    from wr.demo import create_demo_workspace
    create_demo_workspace(tmp_path)
    monkeypatch.chdir(tmp_path)
    cfg = load_settings()
    with connect(cfg.resolved_db_path) as conn:
        conn.execute('UPDATE tax_returns SET grondslag = NULL, allocation_a = NULL, allocation_b = NULL')
    app = AppTest.from_file(str(APP)).run()
    assert not app.exception
    decision = next(table.value for table in app.dataframe if 'Taxpayer' in table.value.columns)
    assert decision['Taxpayer'].tolist() == [cfg.partners.partner_a, cfg.partners.partner_b]
    assert decision['Decision'].tolist() == ['Manual review needed', 'Manual review needed']
    assert any(':green-badge[' in text.value and 'Ready to review' in text.value for text in app.markdown)
