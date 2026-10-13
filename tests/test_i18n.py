import ast
import io
import sqlite3
import zipfile
from pathlib import Path
from string import Formatter

import pytest
from streamlit.testing.v1 import AppTest

from wr.demo import create_demo_workspace
from wr.desktop_storage import prepare_workspace, remember_folder, remember_language, remembered_language, selected_folder
from wr.i18n import DUTCH, STATUS_MESSAGES, currency, status_label, translate, translator


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
    for filename in ["dashboard/app.py", "dashboard/desktop_import.py", "src/wr/desktop.py"]:
        tree = ast.parse((root / filename).read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "t":
                if node.args and isinstance(node.args[0], ast.Constant):
                    assert node.args[0].value in DUTCH, (filename, node.args[0].value)
    for english, dutch in DUTCH.items():
        fields = lambda text: {name for _, name, _, _ in Formatter().parse(text) if name is not None}
        assert fields(english) == fields(dutch), english
    assert set(STATUS_MESSAGES.values()) <= set(DUTCH)
    assert status_label("INDETERMINATE_MISSING_DATA", "nl") == "Onvolledige gegevens"
    assert status_label("future-unimplemented-code", "nl") == "future-unimplemented-code"
    with pytest.raises(ValueError):
        translator("fr")
    assert translate("nl", "Folder selection failed: {error}", error="EXAMPLE.pdf") == "Mapselectie mislukt: EXAMPLE.pdf"


def test_dashboard_switches_language_and_retains_year_and_evidence(tmp_path, monkeypatch):
    import sys
    config = create_demo_workspace(tmp_path)
    monkeypatch.setattr(sys, "argv", ["app.py", "--config", str(config)])
    monkeypatch.delenv("WR_CONTROL_URL", raising=False)
    # Find the demo's configured database without making assumptions about its name.
    from wr.config import load_config
    database = load_config(config).resolved_db_path

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
    from wr.import_pipeline import ImportReport
    config = prepare_workspace(tmp_path)
    monkeypatch.setenv("WR_CONTROL_URL", "http://synthetic.invalid")
    monkeypatch.setattr(sys, "argv", ["app.py", "--config", str(config)])
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


def test_native_launcher_updates_from_selector_and_dashboard_preference(tmp_path, monkeypatch):
    import tkinter as tk
    from tkinter import ttk
    from wr import desktop

    widgets = []

    class Widget:
        def __init__(self, *args, **kwargs):
            self.options = kwargs
            self.callback = None
            widgets.append(self)

        def pack(self, **kwargs):
            pass

        def config(self, **kwargs):
            self.options.update(kwargs)

        def bind(self, _, callback):
            self.callback = callback

    class Variable:
        def __init__(self, value):
            self.value = value

        def set(self, value):
            self.value = value

        def get(self):
            return self.value

    class Window:
        def title(self, value):
            pass

        def geometry(self, value):
            pass

        def protocol(self, *args):
            pass

        def destroy(self):
            pass

        def after(self, _, callback):
            self.tick = callback

        def mainloop(self):
            selector = next(w for w in widgets if w.callback)
            selector.options["textvariable"].set("English")
            selector.callback(None)
            assert remembered_language(tmp_path) == "en"
            assert any(w.options.get("text") == "Open dashboard" for w in widgets)
            # The dashboard writes the same preference file; the launcher polls it.
            remember_language(tmp_path, "nl")
            self.tick()
            assert any(w.options.get("text") == "Dashboard openen" for w in widgets)
            assert selector.options["textvariable"].get() == "Nederlands"

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

    monkeypatch.setattr(tk, "Tk", Window)
    for name in ("Frame", "Label", "Button"):
        monkeypatch.setattr(tk, name, Widget)
    monkeypatch.setattr(tk, "StringVar", Variable)
    monkeypatch.setattr(ttk, "Combobox", Widget)
    monkeypatch.setattr(desktop, "app_data_dir", lambda: tmp_path)
    monkeypatch.setattr(desktop.sys, "argv", ["desktop"])
    monkeypatch.setattr(desktop.subprocess, "Popen", lambda *args, **kwargs: Child())
    monkeypatch.setattr(desktop, "open_external", lambda _: None)
    monkeypatch.setattr(desktop.urllib.request, "build_opener", lambda *args: Health())
    assert desktop.main() == 0
