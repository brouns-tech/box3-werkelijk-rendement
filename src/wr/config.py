"""Application defaults; workspace-specific overrides live in the settings JSON."""
from pathlib import Path
from typing import Final


APP_NAME: Final = "Werkelijk Rendement"
APP_DATA_DIRECTORY: Final = "WerkelijkRendement"
DISTRIBUTION_NAME: Final = "box3-werkelijk-rendement"

SETTINGS_FILENAME: Final = ".wr-settings.json"
DATABASE_FILENAME: Final = "wr.sqlite"
DEFAULT_WORKSPACE_DATABASE: Final = Path("data") / DATABASE_FILENAME
DEFAULT_DESKTOP_DATABASE: Final = Path(DATABASE_FILENAME)
DEMO_DATABASE_FILENAME: Final = "wr-demo.sqlite"
DEFAULT_AUDIT_EXPORT: Final = Path("exports/wr-audit.zip")
DEFAULT_DASHBOARD_PORT: Final = 8501

LANGUAGE_FILENAME: Final = "language.json"
LEGACY_PREFERENCES_FILENAME: Final = "preferences.json"
INSTANCE_FILENAME: Final = "instance.json"
INSTANCE_LOCK_FILENAME: Final = "instance.lock"
SERVER_LOG_FILENAME: Final = "server.log"
LAUNCHER_LOG_FILENAME: Final = "launcher.log"
SELFCHECK_ERROR_FILENAME: Final = "smoke-error.log"
