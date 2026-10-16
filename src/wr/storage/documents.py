from __future__ import annotations

import sqlite3

from wr.models.storage import DocumentInput, DocumentUpdate
from wr.storage.reconciliation import invalidate_reconciliation


def upsert_document(conn: sqlite3.Connection, **kwargs: str | int | None) -> bool:
    """Insert document if new. Returns True if inserted, False if already present."""
    document = DocumentInput.model_validate(kwargs)
    cur = conn.execute(
        "SELECT 1 FROM documents WHERE content_sha256 = ?",
        (document.content_sha256,),
    )
    if cur.fetchone():
        return False
    conn.execute(
        """
        INSERT INTO documents (
            content_sha256, byte_size, page_count, first_seen_path, imported_at,
            issuer, doc_type, tax_year, raw_text_excerpt, parse_status
        ) VALUES (
            :content_sha256, :byte_size, :page_count, :first_seen_path, :imported_at,
            :issuer, :doc_type, :tax_year, :raw_text_excerpt, :parse_status
        )
        """,
        document.model_dump(),
    )
    return True


def update_document(conn: sqlite3.Connection, sha: str, **kwargs: str | int | None) -> None:
    update = DocumentUpdate.model_validate(kwargs)
    params = update.model_dump(exclude_unset=True)
    if not params:
        return
    cols = ", ".join(f"{column} = :{column}" for column in params)
    params["content_sha256"] = sha
    conn.execute(f"UPDATE documents SET {cols} WHERE content_sha256 = :content_sha256", params)


def count_outdated_documents(conn: sqlite3.Connection, profile: str) -> int:
    return conn.execute(
        "SELECT COUNT(*) FROM documents WHERE parse_status = 'parsed' "
        "AND (observations_version != 1 OR processing_profile IS NULL OR processing_profile NOT IN (?, 'synthetic-demo-v1'))",
        (profile,),
    ).fetchone()[0]


def document_is_current(conn: sqlite3.Connection, sha: str, profile: str) -> bool:
    row = conn.execute(
        "SELECT parse_status, processing_profile, observations_version FROM documents WHERE content_sha256 = ?", (sha,)
    ).fetchone()
    return row is not None and row["parse_status"] == "parsed" and row["processing_profile"] == profile and row["observations_version"] == 1


def clear_document_records(conn: sqlite3.Connection, sha: str) -> None:
    invalidate_reconciliation(conn)
    conn.execute("DELETE FROM account_year_facts WHERE document_sha256 = ?", (sha,))
    conn.execute("DELETE FROM tax_returns WHERE document_sha256 = ?", (sha,))
