import json
import threading
import urllib.error
import urllib.request

import pytest

from wr.desktop import InstanceLock, child_command, control_request, make_control_server
from wr.desktop_smoke import smoke_test, synthetic_pdf
from wr.desktop_storage import prepare_workspace, remember_folder, selected_folder
from wr.import_pipeline import run_import


def test_desktop_workspace_persists_and_does_not_overwrite_configuration(tmp_path):
    from wr.config import PartnerSettings, load_settings, save_settings
    prepare_workspace(tmp_path)
    save_settings(load_settings(tmp_path), PartnerSettings(partner_a="EXAMPLE"), db_path="custom.sqlite")
    documents = tmp_path / "space and unicode é"
    documents.mkdir()
    remember_folder(tmp_path, str(documents))
    assert selected_folder(tmp_path) == str(documents)
    assert prepare_workspace(tmp_path) == tmp_path
    assert load_settings(tmp_path).partners.partner_a == "EXAMPLE"
    assert load_settings(tmp_path).resolved_db_path == tmp_path / "custom.sqlite"
    with pytest.raises(ValueError):
        remember_folder(tmp_path, str(tmp_path / ".wr-settings.json"))


def test_single_instance_lock_recovers_after_close(tmp_path):
    first, second = InstanceLock(tmp_path), InstanceLock(tmp_path)
    assert first.acquire()
    assert not second.acquire()
    first.close()
    assert second.acquire()
    second.close()


def test_legacy_desktop_storage_migrates_once_and_reset_stays_reset(tmp_path):
    from wr.config import load_settings
    from wr.workspace import reset_workspace

    documents = tmp_path / "statements"
    documents.mkdir()
    legacy = 'db_path = "custom.sqlite"\n[partners]\npartner_a="EXAMPLE"\n'
    (tmp_path / "config.toml").write_text(legacy)
    (tmp_path / "preferences.json").write_text(json.dumps({"selected_folder": str(documents)}))
    assert prepare_workspace(tmp_path) == tmp_path
    cfg = load_settings(tmp_path)
    assert cfg.resolved_db_path == tmp_path / "custom.sqlite"
    assert cfg.partners.partner_a == "EXAMPLE"
    assert selected_folder(tmp_path) == str(documents)
    assert (tmp_path / "config.toml").read_text() == legacy
    reset_workspace(cfg)
    prepare_workspace(tmp_path)
    assert selected_folder(tmp_path) is None
    assert load_settings(tmp_path).partners.partner_a is None
    assert documents.is_dir()


def test_desktop_folder_selection_preserves_upstream_profiles_and_storage(tmp_path):
    from wr.config import ChildSettings, PartnerSettings, load_settings, save_settings

    prepare_workspace(tmp_path)
    partners = PartnerSettings(partner_a="EXAMPLE", children=(ChildSettings("CHILD", ("C. EXAMPLE",)),))
    options = {"flatex": {"beneficial_owner": "EXAMPLE"}}
    save_settings(load_settings(tmp_path), partners, db_path="custom.sqlite", institution_options=options)
    documents = tmp_path / "statements"
    documents.mkdir()
    remember_folder(tmp_path, str(documents))
    cfg = load_settings(tmp_path)
    assert cfg.partners == partners
    assert cfg.institution_options == options
    assert cfg.resolved_db_path == tmp_path / "custom.sqlite"
    assert cfg.import_root == documents


def test_control_api_requires_token_and_rejects_browser_origin():
    actions = []
    server = make_control_server("synthetic-secret", lambda action: actions.append(action) or {"ok": True})
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    endpoint = f"http://127.0.0.1:{server.server_port}"
    try:
        assert server.server_address[0] == "127.0.0.1"
        assert control_request(endpoint, "synthetic-secret", "status") == {"ok": True}
        for token, origin in [("wrong", None), ("synthetic-secret", "https://example.com")]:
            headers = {"X-WR-Token": token}
            if origin:
                headers["Origin"] = origin
            request = urllib.request.Request(endpoint + "/folder", data=b"", headers=headers)
            with pytest.raises(urllib.error.HTTPError) as error:
                urllib.request.urlopen(request)
            assert error.value.code == 403
        assert actions == ["status"]
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def test_child_command_uses_frozen_executable(monkeypatch, tmp_path):
    import sys
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    assert child_command(tmp_path, 1234) == [sys.executable, "--serve", str(tmp_path), "1234"]


def test_native_pdf_import_and_audit_smoke_without_poppler(tmp_path, monkeypatch):
    smoke_test(tmp_path)
    result = json.loads((tmp_path / "smoke-result.json").read_text())
    assert result["parsers"] == 8
    assert (tmp_path / "audit.zip").is_file()


def test_cancel_between_documents_preserves_imported_data(tmp_path, monkeypatch):
    documents = tmp_path / "documents"
    documents.mkdir()
    synthetic_pdf(documents / "one.PDF")
    synthetic_pdf(documents / "two.pdf")
    stop = threading.Event()
    report = run_import(documents, tmp_path / "data.sqlite", progress=lambda _: stop.set(), cancelled=stop.is_set)
    assert report.cancelled and report.parsed == 1 and report.seen == 1
    # Retained facts deduplicate on the next import.
    report = run_import(documents, tmp_path / "data.sqlite")
    assert report.duplicate == 2


def test_invalid_root_does_not_create_database(tmp_path):
    db = tmp_path / "data.sqlite"
    with pytest.raises(ValueError):
        run_import(tmp_path / "missing", db)
    assert not db.exists()


def test_server_bootstrap_applies_security_options_before_run(monkeypatch, tmp_path):
    prepare_workspace(tmp_path)
    from streamlit import config
    from streamlit.web import bootstrap
    from wr.desktop import serve

    def check_run(app, _, args, options):
        assert config.get_option("server.address") == "127.0.0.1"
        assert config.get_option("server.port") == 9876
        assert config.get_option("browser.gatherUsageStats") is False
        assert config.get_option("server.enableCORS") is True
        assert config.get_option("server.enableXsrfProtection") is True
        assert config.get_option("global.developmentMode") is False
        assert config.get_option("server.baseUrlPath") == "synthetic-prefix"
        assert args == ["--workspace", str(tmp_path)]

    monkeypatch.setenv("WR_DASHBOARD_PATH", "synthetic-prefix")
    monkeypatch.setattr(bootstrap, "run", check_run)
    serve(tmp_path, 9876)


@pytest.mark.parametrize("finish_before_poll", [False, True])
def test_dashboard_onboarding_import_needs_no_cli(tmp_path, monkeypatch, finish_before_poll):
    import sys
    from pathlib import Path
    from streamlit.testing.v1 import AppTest
    from dashboard.desktop_import import ImportJob

    release = threading.Event()
    if finish_before_poll:
        from types import SimpleNamespace
        class JoinedThread:
            def __init__(self, **kwargs):
                self.thread = threading.Thread(**kwargs)

            def start(self):
                self.thread.start()
                self.thread.join(timeout=10)
                assert not self.thread.is_alive()

        monkeypatch.setattr("dashboard.desktop_import.threading", SimpleNamespace(Thread=JoinedThread))
    else:
        run = ImportJob.run

        def delayed_import(job, folder, cfg):
            if release.wait(timeout=10):
                run(job, folder, cfg)
            else:
                job.error = "Test did not release the background import"
                job.done.set()

        monkeypatch.setattr(ImportJob, "run", delayed_import)

    config = prepare_workspace(tmp_path)
    documents = tmp_path / "statements"
    documents.mkdir()
    synthetic_pdf(documents / "statement.pdf")
    monkeypatch.setattr("dashboard.desktop_import.desktop_request", lambda _: {"folder": str(documents)})
    monkeypatch.setenv("WR_CONTROL_URL", "http://synthetic.invalid")
    monkeypatch.setattr(sys, "argv", ["app.py", "--workspace", str(config)])
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "dashboard/app.py")).run()
    assert not app.exception
    next(b for b in app.button if b.label == "Map selecteren").click().run()
    try:
        next(b for b in app.button if b.label == "Documenten scannen en berekenen").click().run()
        assert not app.exception
    finally:
        # AppTest does not emulate browser polling. Keep the asynchronous import
        # pending until its first script render has settled, then render completion.
        # The joined-thread case separately covers finishing before the first poll.
        release.set()
    job = app.session_state["import_job"]
    assert job.done.wait(timeout=10)
    assert job.error is None
    assert not job.busy
    assert job.report.parsed == 1 and job.report.failed == 0
    app.run()
    assert not app.exception
    assert app.session_state["import_job"] is job
    assert any("1 verwerkt" in result.value for result in app.success), {
        "success": [result.value for result in app.success],
        "errors": [result.value for result in app.error],
        "same_job": app.session_state["import_job"] is job,
        "editor_refreshed": job.editor_refreshed,
    }


@pytest.mark.parametrize("already_imported", [False, True])
def test_scan_remembered_folder_in_english_refreshes_editor_without_saving_stale_callbacks(tmp_path, monkeypatch, already_imported):
    import sys
    from pathlib import Path
    from streamlit.testing.v1 import AppTest
    from dashboard.desktop_import import ImportJob
    from wr.config import load_settings
    from wr.desktop_storage import remember_language

    workspace = prepare_workspace(tmp_path)
    documents = tmp_path / "statements"
    documents.mkdir()
    synthetic_pdf(documents / "statement.pdf")
    remember_folder(tmp_path, str(documents))
    remember_language(tmp_path, "en")
    if already_imported:
        run_import(documents, load_settings(tmp_path).resolved_db_path)
    monkeypatch.setenv("WR_CONTROL_URL", "http://synthetic.invalid")
    monkeypatch.setattr(sys, "argv", ["app.py", "--workspace", str(workspace)])
    release = threading.Event()
    run = ImportJob.run

    def delayed_import(job, folder, cfg):
        if release.wait(timeout=10):
            run(job, folder, cfg)

    monkeypatch.setattr(ImportJob, "run", delayed_import)
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "dashboard/app.py")).run()
    before = load_settings(tmp_path).partners
    try:
        app.button(key="scan_documents").click().run()
        assert not app.exception
        assert not any("_identity_" in (widget.key or "") for widget in app.selectbox)
        job = app.session_state["import_job"]
    finally:
        release.set()
    assert job.done.wait(timeout=10)
    # An old browser callback must not save the newly created editor generation.
    app.session_state["taxpayer_assignment_changed"] = True
    app.session_state["taxpayer_save_requested"] = True
    app.run()
    assert not app.exception
    assert app.selectbox(key="ui_language").value == "en"
    expected = "1 duplicate" if already_imported else "1 processed"
    assert any(expected in result.value for result in app.success)
    assert load_settings(tmp_path).partners == before
    assignments = [widget for widget in app.selectbox if "_identity_" in (widget.key or "")]
    assert assignments and all(widget.value is not None for widget in assignments)
    assert not any(button.key == "refresh_dashboard" for button in app.button)
    assert any(header.value == "Decision overview" for header in app.subheader)
    assert job.editor_refreshed
    assert load_settings(tmp_path).import_root == documents


@pytest.mark.parametrize("cancelled", [False, True])
def test_completed_import_fragment_requests_one_full_dashboard_refresh(monkeypatch, cancelled):
    import streamlit as st
    from streamlit.testing.v1 import AppTest
    requests = []
    rerun = st.rerun

    def track_rerun(**kwargs):
        requests.append(kwargs)
        rerun(**kwargs)

    monkeypatch.setattr(st, "rerun", track_rerun)
    app = AppTest.from_string(f'''
import streamlit as st
from dashboard.desktop_import import ImportJob, _render_job
from wr.import_pipeline import ImportReport
if "job" not in st.session_state:
    job = ImportJob(report=ImportReport(cancelled={cancelled}))
    job.done.set()
    st.session_state.job = job
    st.session_state.taxpayer_assignment_changed = True
_render_job(st.session_state.job, "en")
''').run()
    assert not app.exception
    assert requests == [{"scope": "app"}]
    assert "taxpayer_assignment_changed" not in app.session_state
    assert app.success[0].value.startswith("Stopped:" if cancelled else "Done:")
    app.run()
    assert not app.exception
    assert requests == [{"scope": "app"}]


def test_windowed_smoke_failure_writes_traceback_instead_of_error_dialog(tmp_path, monkeypatch):
    import sys
    from wr import desktop, desktop_smoke

    def fail(_directory):
        raise RuntimeError("synthetic extraction failure")

    monkeypatch.setattr(sys, "argv", ["desktop", "--smoke-test", str(tmp_path)])
    monkeypatch.setattr(desktop_smoke, "smoke_test", fail)
    assert desktop.main() == 1
    assert "synthetic extraction failure" in (tmp_path / "smoke-error.log").read_text()


def test_desktop_sidebar_controls_open_storage_and_stop_without_launcher_window(tmp_path, monkeypatch):
    import sys
    from pathlib import Path
    from streamlit.testing.v1 import AppTest
    prepare_workspace(tmp_path)
    actions = []
    monkeypatch.setenv("WR_CONTROL_URL", "http://synthetic.invalid")
    monkeypatch.setattr("wr.desktop.desktop_request", lambda action: actions.append(action) or {})
    monkeypatch.setattr(sys, "argv", ["app.py", "--workspace", str(tmp_path)])
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "dashboard/app.py")).run()
    assert not app.exception
    app.sidebar.button(key="open_local_data").click().run()
    assert actions == ["data"]
    assert not app.exception
    app.sidebar.button(key="exit_application").click().run()
    assert actions == ["data", "stop"]
    assert not app.exception
    assert any("afgesloten" in message.value for message in app.info)


def test_instance_lock_contention_from_another_process_is_not_a_startup_error(tmp_path):
    import subprocess
    import sys
    first = InstanceLock(tmp_path)
    assert first.acquire()
    script = """
from pathlib import Path
import sys
from wr.desktop import InstanceLock
lock = InstanceLock(Path(sys.argv[1]))
print(lock.acquire())
lock.close()
"""
    try:
        second = subprocess.run([sys.executable, "-c", script, str(tmp_path)],
                                capture_output=True, text=True, timeout=10, check=True)
        assert second.stdout.strip() == "False"
    finally:
        first.close()
    after_close = subprocess.run([sys.executable, "-c", script, str(tmp_path)],
                                 capture_output=True, text=True, timeout=10, check=True)
    assert after_close.stdout.strip() == "True"
