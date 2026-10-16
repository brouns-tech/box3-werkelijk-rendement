from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Callable
import sqlite3

from wr.calculations.service import rebuild_portfolio
from wr.calculations.service import rebuild_recommendations
from wr.documents.extraction import extract_text, extraction_profile
from wr.documents.hashing import sha256_file
from wr.reconciliation.service import reconcile_facts
from wr.importing.classification import classify, guess_tax_year
from wr.importing.persistence import persist_parse
from wr.importing.scanner import scan_pdfs
from wr.models.importing import DocumentImportOutcome, ImportReport, ImportStatus, ProgressCallback
from wr.models.settings import HouseholdSettings
from wr.parsers import parse_document
from wr.parsers.base import InstitutionOptions
from wr.storage.connection import connect
from wr.storage.documents import clear_document_records, document_is_current, update_document, upsert_document
from wr.storage.migrations import init_db


def run_import(
    root: str | Path,
    db_path: str | Path,
    limit: int | None = None,
    *,
    household_config: HouseholdSettings | None = None,
    institution_options: InstitutionOptions | None = None,
    progress: ProgressCallback | None = None,
    cancelled: Callable[[], bool] | None = None,
) -> ImportReport:
    root = Path(root)
    if not root.is_dir():
        raise ValueError(f"Import root is not a directory: {root}")
    conn = connect(db_path)
    try:
        return _run_import(root, conn, limit, household_config, institution_options, progress, cancelled)
    finally:
        conn.close()


def _run_import(
    root: Path,
    conn: sqlite3.Connection,
    limit: int | None,
    household_config: HouseholdSettings | None,
    institution_options: InstitutionOptions | None,
    progress: ProgressCallback | None,
    cancelled: Callable[[], bool] | None,
) -> ImportReport:
    init_db(conn)

    report = ImportReport()
    profile = extraction_profile()

    pdfs = scan_pdfs(root, limit)
    for index, path in enumerate(pdfs, start=1):
        if cancelled and cancelled():
            report.cancelled = True
            break
        inserted = False
        try:
            sha = sha256_file(path)
        except OSError as exc:
            _record(
                report,
                DocumentImportOutcome(
                    index, len(pdfs), path, ImportStatus.FAILED, error=f"hash: {exc}"
                ),
                progress,
            )
            continue

        inserted = upsert_document(
            conn,
            content_sha256=sha,
            byte_size=path.stat().st_size,
            page_count=None,
            first_seen_path=str(path),
            imported_at=datetime.now(timezone.utc).isoformat(),
            issuer=None,
            doc_type=None,
            tax_year=None,
            raw_text_excerpt=None,
            parse_status="skipped",
        )
        if not inserted and document_is_current(conn, sha, profile):
            _record(
                report,
                DocumentImportOutcome(
                    index, len(pdfs), path, ImportStatus.DUPLICATE
                ),
                progress,
            )
            continue
        try:
            text, page_count = extract_text(path)
        except Exception as exc:  # noqa: BLE001
            clear_document_records(conn, sha)
            update_document(
                conn,
                sha,
                parse_status="failed",
                raw_text_excerpt=str(exc)[:500],
                processing_profile=profile,
            )
            conn.commit()
            _record(
                report,
                DocumentImportOutcome(
                    index,
                    len(pdfs),
                    path,
                    ImportStatus.FAILED,
                    error=f"extract: {exc}",
                ),
                progress,
                inserted=inserted,
            )
            continue

        excerpt = text[:4000]
        # A refreshed document replaces its complete old parse, including
        # accounts/years that no longer appear. Never accumulate stale holders.
        clear_document_records(conn, sha)
        classification = classify(text)
        if classification is None:
            update_document(
                conn,
                sha,
                page_count=page_count,
                raw_text_excerpt=excerpt,
                parse_status="skipped",
                issuer="unknown",
                doc_type="other",
                processing_profile=profile,
            )
            conn.commit()
            _record(
                report,
                DocumentImportOutcome(index, len(pdfs), path, ImportStatus.SKIPPED),
                progress,
                inserted=inserted,
            )
            continue

        year = guess_tax_year(text, classification.doc_type)
        try:
            conn.execute("SAVEPOINT document_parse")
            result = parse_document(
                classification.issuer,
                classification.doc_type,
                text,
                year,
                institution_options=institution_options,
            )
            persist_parse(conn, sha, classification, result, page_count, excerpt)
            update_document(conn, sha, processing_profile=profile)
            conn.execute("RELEASE document_parse")
            outcome = DocumentImportOutcome(
                index,
                len(pdfs),
                path,
                ImportStatus.PARSED,
                classification.issuer,
                classification.doc_type,
                result.tax_year or year,
            )
        except Exception as exc:  # noqa: BLE001
            conn.execute("ROLLBACK TO document_parse")
            conn.execute("RELEASE document_parse")
            update_document(
                conn,
                sha,
                page_count=page_count,
                issuer=classification.issuer,
                doc_type=classification.doc_type,
                tax_year=year,
                raw_text_excerpt=excerpt,
                parse_status="failed",
                processing_profile=profile,
            )
            outcome = DocumentImportOutcome(
                index,
                len(pdfs),
                path,
                ImportStatus.FAILED,
                classification.issuer,
                classification.doc_type,
                year,
                f"parse: {exc}",
            )
        conn.commit()
        _record(report, outcome, progress, inserted=inserted)

    reconcile_facts(conn, institution_options)
    rebuild_portfolio(conn)
    rebuild_recommendations(conn, household_config)
    return report


def _record(
    report: ImportReport,
    outcome: DocumentImportOutcome,
    callback: ProgressCallback | None,
    *,
    inserted: bool = False,
) -> None:
    report.add(outcome, inserted=inserted)
    if callback:
        callback(outcome)
