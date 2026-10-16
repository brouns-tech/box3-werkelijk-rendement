from __future__ import annotations

from pathlib import Path
import os
import sys

from wr.config import INSTANCE_LOCK_FILENAME


class InstanceLock:
    def __init__(self, directory: Path):
        self.path = directory / INSTANCE_LOCK_FILENAME
        self.file = None

    def acquire(self) -> bool:
        self.file = self.path.open("a+b")
        try:
            # Windows byte-range locks also deny reads from another process.
            # Inspect metadata without touching byte zero until we own the lock.
            if os.fstat(self.file.fileno()).st_size == 0:
                self.file.write(b"0")
                self.file.flush()
            self.file.seek(0)
            if sys.platform == "win32":
                import msvcrt
                msvcrt.locking(self.file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.file.close()
            self.file = None
            return False
        return True

    def close(self) -> None:
        if self.file:
            self.file.close()
            self.file = None
