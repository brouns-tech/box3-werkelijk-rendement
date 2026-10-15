"""Host-desktop integration, separate from the bundled application process."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys


def host_environment() -> dict[str, str]:
    environment = dict(os.environ)
    if getattr(sys, "frozen", False) and sys.platform.startswith("linux"):
        # PyInstaller's private libraries must not be injected into the host browser.
        original = environment.pop("LD_LIBRARY_PATH_ORIG", None)
        if original is None:
            environment.pop("LD_LIBRARY_PATH", None)
        else:
            environment["LD_LIBRARY_PATH"] = original
        for variable in ("PYTHONHOME", "PYTHONPATH"):
            environment.pop(variable, None)
    return environment


def open_external(target: str) -> None:
    if sys.platform == "win32":
        os.startfile(target)
        return
    opener = shutil.which("xdg-open") if sys.platform.startswith("linux") else "/usr/bin/open"
    if not opener:
        raise FileNotFoundError("xdg-open is unavailable; install your desktop's xdg-utils package")
    subprocess.Popen([opener, target], env=host_environment(), stdin=subprocess.DEVNULL,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
