from __future__ import annotations

from pathlib import Path
import os


def serve(config: Path, port: int) -> None:
    from streamlit.web import bootstrap
    from wr.workspace.settings import load_settings
    from wr.calculations.service import recompute
    settings = load_settings(config)
    if settings.resolved_db_path.exists():
        # Recover derived results after an interrupted import before displaying them.
        recompute(settings.resolved_db_path, household_config=settings.household,
                  institution_options=settings.institution_options)
    import importlib.util
    app = Path(importlib.util.find_spec("dashboard").origin).parent / "app.py"
    # bootstrap is an internal API: pinned release dependencies and smoke tests protect it.
    options = {
        "global.developmentMode": False,
        "server.address": "127.0.0.1", "server.port": port,
        "browser.serverAddress": "127.0.0.1", "server.headless": True,
        "server.enableCORS": True, "server.enableXsrfProtection": True,
        "browser.gatherUsageStats": False, "server.fileWatcherType": "none",
        "server.enableStaticServing": False,
        "server.baseUrlPath": os.environ.get("WR_DASHBOARD_PATH", ""),
    }
    bootstrap.load_config_options(options)
    bootstrap.run(str(app), False, ["--workspace", str(config)], options)
