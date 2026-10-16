import ast
from dataclasses import FrozenInstanceError
import inspect
import io
import json
import sqlite3
import zipfile
from pathlib import Path
from string import Formatter

import pytest
from streamlit.testing.v1 import AppTest

from wr.demo import create_demo_workspace
from wr.desktop.storage import prepare_workspace, remember_folder, remember_language, remembered_language, selected_folder
from wr.i18n import STATUS_MESSAGES, Translator, coverage_details, currency, status_label, translate, translator
from wr.messages import Message, Messages, MessageTemplate


@pytest.mark.parametrize("language,expected", [("en", "€ -12,345.67"), ("nl", "€ -12.345,67")])
def test_currency_format_is_local_to_each_language(language, expected):
    assert currency(-12345.67, language) == expected
    assert currency(0, language).endswith("0,00" if language == "nl" else "0.00")
    assert currency(None, language) == "—"


def test_preference_survives_folder_changes_and_invalid_files(tmp_path):
    prepare_workspace(tmp_path)
    documents = tmp_path / "documents"
    documents.mkdir()
    assert remembered_language(tmp_path) == "nl"
    remember_language(tmp_path, "en")
    remember_folder(tmp_path, str(documents))
    assert remembered_language(tmp_path) == "en"
    assert selected_folder(tmp_path) == str(documents)
    remember_language(tmp_path, "nl")
    assert selected_folder(tmp_path) == str(documents)
    with pytest.raises(ValueError):
        remember_language(tmp_path, "fr")
    for invalid in ['broken', '[]', '{"language": "fr"}', '{"language": []}']:
        (tmp_path / "language.json").write_text(invalid)
        assert remembered_language(tmp_path, default="en") == "en"


def test_catalog_covers_ui_and_preserves_format_fields():
    root = Path(__file__).resolve().parents[1]
    for filename in ["dashboard/app.py", "dashboard/desktop_import.py", "src/wr/desktop/launcher.py", "dashboard/settings.py", "dashboard/workspace_settings.py", "dashboard/folder_picker.py", "dashboard/localization.py"]:
        tree = ast.parse((root / filename).read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "t":
                assert not node.keywords, filename
                assert not isinstance(node.args[0], ast.Constant), filename
            if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == "Messages":
                assert isinstance(getattr(Messages, node.attr), (Message, MessageTemplate)), (filename, node.attr)
    catalog = {name: message for name, message in vars(Messages).items() if not name.startswith("_")}
    for name, message in catalog.items():
        assert isinstance(message, (Message, MessageTemplate)), name
        assert message.en and message.nl, name
        english_fields = {field for _, field, _, _ in Formatter().parse(message.en) if field is not None}
        dutch_fields = {field for _, field, _, _ in Formatter().parse(message.nl) if field is not None}
        assert english_fields == dutch_fields, name
        if isinstance(message, MessageTemplate):
            method = getattr(Translator, name.lower())
            parameters = dict(inspect.signature(method).parameters)
            parameters.pop("self")
            assert set(parameters) == english_fields, name
            assert all(parameter.kind is inspect.Parameter.KEYWORD_ONLY for parameter in parameters.values())
            arguments = {field: 2 if field in {"number", "count", "parsed", "duplicate", "skipped", "failed"} else "example" for field in english_fields}
            for language in ("en", "nl"):
                assert method(translator(language), **arguments) == getattr(message, language).format(**arguments)
    assert set(STATUS_MESSAGES.values()) <= set(catalog.values())
    assert list(STATUS_MESSAGES) == sorted(STATUS_MESSAGES)
    assert status_label("INDETERMINATE_MISSING_DATA", "nl") == "Onvolledige gegevens"
    assert status_label("future-unimplemented-code", "nl") == "future-unimplemented-code"
    with pytest.raises(ValueError):
        translator("fr")
    assert translator("nl").folder_selection_failed(error="EXAMPLE.pdf") == "Mapselectie mislukt: EXAMPLE.pdf"


def test_message_schema_rejects_invalid_templates_and_is_immutable():
    with pytest.raises(ValueError, match="MessageTemplate"):
        Message(en="Child {number}", nl="Kind {number}")
    with pytest.raises(ValueError, match="matching parameters"):
        MessageTemplate(en="Child {number}", nl="Kind {count}")
    with pytest.raises(ValueError, match="matching parameters"):
        MessageTemplate(en="Child", nl="Kind")
    with pytest.raises(FrozenInstanceError):
        Messages.SETTINGS_SAVED.nl = "changed"


def test_translator_constrains_messages_and_parameters_without_shared_language_state():
    english = translator("en")
    dutch = translator("nl")
    assert english(Messages.SETTINGS_SAVED) == "Settings saved."
    assert dutch(Messages.SETTINGS_SAVED) == "Instellingen opgeslagen."
    assert english(Messages.SETTINGS_SAVED) == "Settings saved."
    assert translate("nl", Messages.SELECT_FOLDER) == "Map selecteren"
    assert dutch.child(number=2) == "Kind 2"
    assert dutch.folder_selection_failed(error=OSError("example")) == "Mapselectie mislukt: example"
    with pytest.raises(TypeError, match="Expected a Message"):
        dutch("Settings saved.")
    with pytest.raises(TypeError, match="Expected a Message"):
        dutch(Messages.CHILD)
    with pytest.raises(TypeError):
        dutch.child(count=2)
    with pytest.raises(TypeError):
        dutch.child()


def test_status_and_coverage_translate_known_messages_and_preserve_source_text():
    assert status_label(None, "nl") == "—"
    assert status_label("parsed", "nl") == "Verwerkt"
    assert status_label("Settings saved.", "nl") == "Settings saved."
    assert coverage_details("Settings saved.", "nl") == "Settings saved."
    assert coverage_details("example (no actual-return fields)", "nl") == "example (Geen gegevens voor werkelijk rendement)"
    assert coverage_details("example (requires EUR conversion and currency gain/loss)", "nl") == "example (Omrekening naar EUR en valutawinst/-verlies vereist)"


def test_institution_settings_support_messages_and_literal_plugin_text(tmp_path, monkeypatch):
    from dataclasses import replace
    from dashboard import workspace_settings
    from wr.parsers.base import InstitutionSetting

    create_demo_workspace(tmp_path)
    monkeypatch.chdir(tmp_path)
    plugin = replace(workspace_settings.PLUGINS[0], settings_fields=(
        InstitutionSetting("translated", Messages.ACCOUNT_LABEL, Messages.DOCUMENT_FOLDER_HELP),
        InstitutionSetting("literal", "Plugin label", "Plugin help"),
    ))
    monkeypatch.setattr(workspace_settings, "PLUGINS", (plugin,))
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "dashboard/app.py")).run()
    assert not app.exception
    assert app.text_input(key=f"institution_{plugin.issuer}_translated").label == "Account label"
    assert app.text_input(key=f"institution_{plugin.issuer}_literal").label == "Plugin label"
    app.selectbox(key="ui_language").select("nl").run()
    assert not app.exception
    translated = app.text_input(key=f"institution_{plugin.issuer}_translated")
    assert translated.label == "Rekeningnaam"
    assert translated.help == Messages.DOCUMENT_FOLDER_HELP.nl
    assert app.text_input(key=f"institution_{plugin.issuer}_literal").label == "Plugin label"
    assert app.text_input(key=f"institution_{plugin.issuer}_literal").help == "Plugin help"


def test_dashboard_switches_language_and_retains_year_and_evidence(tmp_path, monkeypatch):
    import sys
    config = create_demo_workspace(tmp_path)
    monkeypatch.setattr(sys, "argv", ["app.py", "--workspace", str(config)])
    monkeypatch.delenv("WR_CONTROL_URL", raising=False)
    # Find the demo's configured database without making assumptions about its name.
    from wr.workspace.settings import load_settings
    database = load_settings(config).resolved_db_path

    def exported_csvs():
        from wr.export import create_audit_export
        with sqlite3.connect(database) as conn:
            conn.row_factory = sqlite3.Row
            content = create_audit_export(conn)
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            return {name: archive.read(name) for name in archive.namelist() if name.endswith(".csv")}

    original_export = exported_csvs()
    with sqlite3.connect(database) as conn:
        before = list(conn.iterdump())
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "dashboard/app.py")).run()
    assert not app.exception
    assert any(header.value == "Decision overview" for header in app.subheader)
    english_amount = app.metric[1].value
    year = app.selectbox(key="tax_year").value
    app.selectbox(key="ui_language").select("nl").run()
    assert not app.exception
    assert remembered_language(tmp_path) == "nl"
    assert any(header.value == "Vergelijking van rendementen" for header in app.subheader)
    assert app.selectbox(key="tax_year").value == year
    assert app.metric[1].value != english_amount
    assert "Belastingplichtige" in app.dataframe[0].value.columns
    assert "Rekeninghouder" in app.dataframe[1].value.columns
    restarted = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "dashboard/app.py")).run()
    assert restarted.selectbox(key="ui_language").value == "nl"
    restarted.selectbox(key="ui_language").select("en").run()
    assert not restarted.exception
    assert restarted.metric[1].value == english_amount
    assert "Taxpayer" in restarted.dataframe[0].value.columns
    with sqlite3.connect(database) as conn:
        assert list(conn.iterdump()) == before
    assert exported_csvs() == original_export


def test_desktop_import_can_switch_language_during_job(tmp_path, monkeypatch):
    import sys
    from dashboard.desktop_import import ImportJob
    from wr.models.importing import ImportReport
    config = prepare_workspace(tmp_path)
    monkeypatch.setenv("WR_CONTROL_URL", "http://synthetic.invalid")
    monkeypatch.setattr(sys, "argv", ["app.py", "--workspace", str(config)])
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "dashboard/app.py")).run()
    job = ImportJob()
    app.session_state["import_job"] = job
    app.run()
    assert app.button(key="cancel_import").label == "Import stoppen na huidig document"
    app.selectbox(key="ui_language").select("en").run()
    assert not app.exception
    assert app.session_state["import_job"] is job
    app.button(key="cancel_import").click().run()
    assert job.stop.is_set()
    job.report = ImportReport(cancelled=True)
    job.done.set()
    app.run()
    assert any(result.value.startswith("Stopped:") for result in app.success)


def test_upstream_child_editor_survives_language_switch_and_reset(tmp_path, monkeypatch):
    import sys
    from wr.workspace.settings import load_settings

    def child_name(app):
        return [widget for widget in app.text_input if widget.key and "_canonical_" in widget.key][2]

    create_demo_workspace(tmp_path)
    monkeypatch.setattr(sys, "argv", ["app.py", "--workspace", str(tmp_path)])
    monkeypatch.delenv("WR_CONTROL_URL", raising=False)
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "dashboard/app.py")).run()
    app.button(key="add_child").click().run()
    child_name(app).set_value("Charlie Example").run()
    app.selectbox(key="ui_language").select("nl").run()
    assert not app.exception
    assert child_name(app).value == "Charlie Example"
    assert app.button(key="add_child").label == "Kind toevoegen"
    assert [tab.label for tab in app.tabs] == ["Overzicht", "Documenten", "Belastingplichtigen", "Instellingen"]
    next(button for button in app.button if button.key.startswith("save_field_canonical_")).click().run()
    assert load_settings(tmp_path).household.children[0].name == "Charlie Example"
    assert "Toerekening" in app.dataframe[1].value.columns
    app.button(key="reset_workspace").click().run()
    app.button(key="confirm_reset_workspace").click().run()
    assert not app.exception
    assert load_settings(tmp_path).household.children == ()
    assert app.selectbox(key="ui_language").value == "nl"


@pytest.mark.parametrize("verification_mode", [False, True])
def test_hidden_supervisor_opens_browser_and_handles_native_actions(tmp_path, monkeypatch, verification_mode):
    import threading
    import time
    import tkinter as tk
    from tkinter import filedialog, messagebox
    from wr.desktop import launcher as desktop

    opened = []
    failures = []
    worker = None

    class Window:
        hidden = False
        destroyed = False

        def __init__(self):
            self.callbacks = []

        def withdraw(self):
            self.hidden = True

        def title(self, value):
            assert self.hidden

        def protocol(self, *args):
            pass

        def destroy(self):
            self.destroyed = True

        def after(self, _, callback):
            self.callbacks.append(callback)

        def mainloop(self):
            nonlocal worker
            assert self.hidden
            remember_language(tmp_path, "en")
            self.callbacks.pop(0)()
            instance = json.loads((tmp_path / "instance.json").read_text())

            def request_actions():
                try:
                    request = lambda action: desktop.control_request(instance["endpoint"], instance["token"], action, 5)
                    assert request("folder").folder == str(tmp_path)
                    assert request("data").opened is True
                    assert request("stop").stopping is True
                except Exception as exc:
                    failures.append(exc)

            worker = threading.Thread(target=request_actions)
            worker.start()
            deadline = time.monotonic() + 10
            while not self.destroyed and time.monotonic() < deadline:
                self.callbacks.pop(0)()
                time.sleep(0.01)
            assert self.destroyed
            worker.join(timeout=5)
            assert not failures
            assert not worker.is_alive()

    class Child:
        returncode = None

        def poll(self):
            return self.returncode

        def terminate(self):
            self.returncode = 0

        def wait(self, **kwargs):
            return self.returncode

    class Health:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def read(self):
            return b"ok"

        def open(self, *args, **kwargs):
            return self

    def folder_picker(**kwargs):
        assert kwargs["parent"].hidden
        assert kwargs["title"] == "Select folder"
        return str(tmp_path)

    def unexpected_widget(*args, **kwargs):
        pytest.fail("The supervisor must not create persistent widgets")

    def unexpected_error(*args, **kwargs):
        pytest.fail("Healthy startup must not show an error dialog")

    monkeypatch.setattr(tk, "Tk", Window)
    for name in ("Frame", "Label", "Button"):
        monkeypatch.setattr(tk, name, unexpected_widget)
    monkeypatch.setattr(filedialog, "askdirectory", folder_picker)
    monkeypatch.setattr(messagebox, "showerror", unexpected_error)
    monkeypatch.setattr(desktop, "app_data_dir", lambda: tmp_path)
    monkeypatch.setattr(desktop.sys, "argv", ["desktop", "--verify-launcher"] if verification_mode else ["desktop"])
    child = Child()
    monkeypatch.setattr(desktop.subprocess, "Popen", lambda *args, **kwargs: child)
    monkeypatch.setattr(desktop, "open_external", opened.append)
    # Replace only the health check opener; control_request still uses real IPC.
    real_opener = desktop.urllib.request.build_opener
    class Opener:
        def open(self, target, **kwargs):
            if isinstance(target, str):
                return Health()
            return real_opener(desktop.urllib.request.ProxyHandler({})).open(target, **kwargs)
    monkeypatch.setattr(desktop.urllib.request, "build_opener", lambda *args: Opener())
    assert desktop.main() == 0
    assert child.returncode == 0
    assert not (tmp_path / "instance.json").exists()
    if verification_mode:
        assert opened == []
    else:
        assert opened[0].startswith("http://127.0.0.1:")
        assert opened[1] == str(tmp_path)
