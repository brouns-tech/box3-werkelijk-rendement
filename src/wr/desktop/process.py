from __future__ import annotations

from pathlib import Path
import os
import sys
import time


def child_command(config: Path, port: int) -> list[str]:
    prefix = [sys.executable] if getattr(sys, "frozen", False) else [sys.executable, "-m", "wr.desktop"]
    return [*prefix, "--serve", str(config), str(port)]


def watch_parent() -> None:
    """Exit the server if the supervisor dies, including Task Manager termination."""
    parent = int(os.environ["WR_PARENT_PID"])
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.WaitForSingleObject.argtypes = (wintypes.HANDLE, wintypes.DWORD)
        kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
        handle = kernel.OpenProcess(0x00100000, False, parent)  # SYNCHRONIZE
        if not handle:
            os._exit(1)
        kernel.WaitForSingleObject(handle, 0xFFFFFFFF)
        kernel.CloseHandle(handle)
    else:
        while os.getppid() == parent:
            time.sleep(1)
    os._exit(0)
