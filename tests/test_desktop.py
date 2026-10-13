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
    config = prepare_workspace(tmp_path)
    config.write_text('db_path = "custom.sqlite"\n[partners]\npartner_a="EXAMPLE"\n')
    documents = tmp_path / "space and unicode é"
    documents.mkdir()
    remember_folder(tmp_path, str(documents))
    assert selected_folder(tmp_path) == str(documents)
    assert prepare_workspace(tmp_path).read_text() == config.read_text()
    with pytest.raises(ValueError):
        remember_folder(tmp_path, str(config))


def test_single_instance_lock_recovers_after_close(tmp_path):
    first, second = InstanceLock(tmp_path), InstanceLock(tmp_path)
    assert first.acquire()
    assert not second.acquire()
    first.close()
    assert second.acquire()
    second.close()


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
    assert child_command(tmp_path / "config.toml", 1234) == [sys.executable, "--serve", str(tmp_path / "config.toml"), "1234"]


def test_native_pdf_import_and_audit_smoke_without_poppler(tmp_path, monkeypatch):
    monkeypatch.setattr("wr.pdf.shutil.which", lambda _: None)
    smoke_test(tmp_path)
    result = json.loads((tmp_path / "smoke-result.json").read_text())
    assert result["parsers"] == 8
    assert (tmp_path / "audit.zip").is_file()


def test_cancel_between_documents_preserves_imported_data(tmp_path, monkeypatch):
    monkeypatch.setattr("wr.pdf.shutil.which", lambda _: None)
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
        assert args == ["--config", str(tmp_path / "config.toml")]

    monkeypatch.setenv("WR_DASHBOARD_PATH", "synthetic-prefix")
    monkeypatch.setattr(bootstrap, "run", check_run)
    serve(tmp_path / "config.toml", 9876)


def test_dashboard_onboarding_import_needs_no_cli(tmp_path, monkeypatch):
    import sys
    from pathlib import Path
    from streamlit.testing.v1 import AppTest

    config = prepare_workspace(tmp_path)
    documents = tmp_path / "statements"
    documents.mkdir()
    synthetic_pdf(documents / "statement.pdf")
    monkeypatch.setattr("wr.pdf.shutil.which", lambda _: None)
    monkeypatch.setattr("dashboard.desktop_import.desktop_request", lambda _: {"folder": str(documents)})
    monkeypatch.setenv("WR_CONTROL_URL", "http://synthetic.invalid")
    monkeypatch.setattr(sys, "argv", ["app.py", "--config", str(config)])
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "dashboard/app.py")).run()
    assert not app.exception
    next(b for b in app.button if b.label == "Map selecteren").click().run()
    next(b for b in app.button if b.label == "Documenten scannen en berekenen").click().run()
    assert app.session_state["import_job"].done.wait(timeout=10)
    app.run()
    assert not app.exception
    assert any("1 verwerkt" in result.value for result in app.success)


def test_windowed_smoke_failure_writes_traceback_instead_of_error_dialog(tmp_path, monkeypatch):
    import sys
    from wr import desktop, desktop_smoke

    def fail(_directory):
        raise RuntimeError("synthetic extraction failure")

    monkeypatch.setattr(sys, "argv", ["desktop", "--smoke-test", str(tmp_path)])
    monkeypatch.setattr(desktop_smoke, "smoke_test", fail)
    assert desktop.main() == 1
    assert "synthetic extraction failure" in (tmp_path / "smoke-error.log").read_text()
