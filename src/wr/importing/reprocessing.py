from __future__ import annotations

import sqlite3

from wr.documents.extraction import extraction_profile
from wr.storage.documents import count_outdated_documents


def pending_reprocessing(conn: sqlite3.Connection) -> int:
    return count_outdated_documents(conn, extraction_profile())
