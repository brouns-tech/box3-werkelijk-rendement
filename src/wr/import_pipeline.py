from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Callable

from wr.classify import Classification, classify, guess_tax_year
from wr.config import PartnerSettings
from wr.db import (
    clear_canonical_flags,
    connect,
    init_db,
    insert_facts,
    update_document,
    upsert_document,
)
from wr.dedupe import canonicalize_facts
from wr.parsers import parse_document
from wr.parsers.base import InstitutionOptions
from wr.pdf import extract_text, sha256_file
from wr.portfolio import rebuild_portfolio
from wr.recommend import rebuild_recommendations


class ImportStatus(str, Enum):
    PARSED = "parsed"
    SKIPPED = "skipped"
    DUPLICATE = "duplicate"
    FAILED = "failed"


@dataclass(frozen=True)
class DocumentImportOutcome:
    index: int
    total: int
    path: Path
    status: ImportStatus
    issuer: str | None = None
    doc_type: str | None = None
    tax_year: int | None = None
    error: str | None = None


@dataclass
class ImportReport:
    seen: int = 0
    new: int = 0
    duplicate: int = 0
    parsed: int = 0
    skipped: int = 0
    failed: int = 0
    outcomes: list[DocumentImportOutcome] = field(default_factory=list)

    def add(self, outcome: DocumentImportOutcome, *, inserted: bool = False) -> None:
        self.seen += 1
        self.new += int(inserted)
        setattr(self, outcome.status.value, getattr(self, outcome.status.value) + 1)
        self.outcomes.append(outcome)


ProgressCallback = Callable[[DocumentImportOutcome], None]


def run_import(
    root: str | Path,
    db_path: str | Path,
    limit: int | None = None,
    *,
    partner_config: PartnerSettings | None = None,
    institution_options: InstitutionOptions | None = None,
    progress: ProgressCallback | None = None,
) -> ImportReport:
    root = Path(root)
    conn = connect(db_path)
    init_db(conn)

    report = ImportReport()

    pdfs = sorted(root.rglob("*.pdf"))
    if limit is not None:
        pdfs = pdfs[:limit]
    for index, path in enumerate(pdfs, start=1):
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
        if not inserted:
            existing = conn.execute(
                "SELECT parse_status FROM documents WHERE content_sha256 = ?", (sha,)
            ).fetchone()
            if existing is None or existing["parse_status"] != "skipped":
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
            update_document(
                conn,
                sha,
                parse_status="failed",
                raw_text_excerpt=str(exc)[:500],
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
            result = parse_document(
                classification.issuer,
                classification.doc_type,
                text,
                year,
                institution_options=institution_options,
            )
            _persist_parse(conn, sha, classification, result, page_count, excerpt)
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
            update_document(
                conn,
                sha,
                page_count=page_count,
                issuer=classification.issuer,
                doc_type=classification.doc_type,
                tax_year=year,
                raw_text_excerpt=excerpt,
                parse_status="failed",
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

    canonicalize_facts(conn, institution_options)
    rebuild_portfolio(conn)
    rebuild_recommendations(conn, partner_config)

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


def _persist_parse(conn, sha, classification: Classification, result, page_count, excerpt) -> None:
    update_document(
        conn,
        sha,
        page_count=page_count,
        issuer=result.issuer or classification.issuer,
        doc_type=result.doc_type or classification.doc_type,
        tax_year=result.tax_year,
        raw_text_excerpt=excerpt,
        parse_status="parsed",
    )

    fact_rows = []
    for fact in result.facts:
        fact.compute_capital_gain()
        d = asdict(fact)
        d["is_canonical"] = 0
        d.pop("extra", None)
        d["extra"] = fact.extra
        fact_rows.append(d)
    if fact_rows:
        insert_facts(conn, sha, fact_rows)

    if result.tax_return is not None:
        tr = result.tax_return
        alloc_a = tr.allocation_a
        alloc_b = tr.allocation_b
        conn.execute(
            """
            INSERT INTO tax_returns (
                document_sha256, tax_year, filer_name, full_year_fiscal_partners,
                partner_a_name, partner_b_name,
                bezittingen_0101, bezittingen_3112, schulden_0101, schulden_3112,
                heffingsvrij_vermogen, grondslag, grondslag_a, grondslag_b,
                allocation_a, allocation_b, allocation_status,
                voordeel_a, voordeel_b, box3_tax_a, box3_tax_b
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(document_sha256, tax_year) DO UPDATE SET
                filer_name=excluded.filer_name,
                full_year_fiscal_partners=excluded.full_year_fiscal_partners,
                partner_a_name=excluded.partner_a_name,
                partner_b_name=excluded.partner_b_name,
                bezittingen_0101=excluded.bezittingen_0101,
                bezittingen_3112=excluded.bezittingen_3112,
                schulden_0101=excluded.schulden_0101,
                schulden_3112=excluded.schulden_3112,
                heffingsvrij_vermogen=excluded.heffingsvrij_vermogen,
                grondslag=excluded.grondslag,
                grondslag_a=excluded.grondslag_a,
                grondslag_b=excluded.grondslag_b,
                allocation_a=excluded.allocation_a,
                allocation_b=excluded.allocation_b,
                allocation_status=excluded.allocation_status,
                voordeel_a=excluded.voordeel_a,
                voordeel_b=excluded.voordeel_b,
                box3_tax_a=excluded.box3_tax_a,
                box3_tax_b=excluded.box3_tax_b
            """,
            (
                sha,
                tr.tax_year,
                tr.filer_name,
                1 if tr.full_year_fiscal_partners else 0,
                tr.partner_a_name,
                tr.partner_b_name,
                tr.bezittingen_0101,
                tr.bezittingen_3112,
                tr.schulden_0101,
                tr.schulden_3112,
                tr.heffingsvrij_vermogen,
                tr.grondslag,
                tr.grondslag_a,
                tr.grondslag_b,
                alloc_a,
                alloc_b,
                tr.allocation_status,
                tr.voordeel_a,
                tr.voordeel_b,
                tr.box3_tax_a,
                tr.box3_tax_b,
            ),
        )


def recompute(
    db_path: str | Path,
    *,
    partner_config: PartnerSettings | None = None,
    institution_options: InstitutionOptions | None = None,
) -> None:
    conn = connect(db_path)
    init_db(conn)
    clear_canonical_flags(conn)
    canonicalize_facts(conn, institution_options)
    rebuild_portfolio(conn)
    rebuild_recommendations(conn, partner_config)
