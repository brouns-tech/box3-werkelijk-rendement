from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from wr.classify import Classification, classify, guess_tax_year
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
from wr.pdf import extract_text, sha256_file
from wr.portfolio import rebuild_portfolio
from wr.recommend import rebuild_recommendations
from wr.source_rules import has_zero_return_by_product


def run_import(root: str | Path, db_path: str | Path, limit: int | None = None) -> dict:
    root = Path(root)
    conn = connect(db_path)
    init_db(conn)

    stats = {
        "seen": 0,
        "new": 0,
        "duplicate": 0,
        "parsed": 0,
        "skipped": 0,
        "failed": 0,
    }

    pdfs = sorted(root.rglob("*.pdf"))
    if limit is not None:
        pdfs = pdfs[:limit]
    print(f"Scanning {len(pdfs)} PDF(s)")

    for index, path in enumerate(pdfs, start=1):
        progress = f"[{index}/{len(pdfs)}]"
        stats["seen"] += 1
        try:
            sha = sha256_file(path)
        except OSError as exc:
            stats["failed"] += 1
            print(f"{progress} failed to hash {path}: {exc}")
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
                stats["duplicate"] += 1
                print(f"{progress} duplicate {path}")
                continue

        if inserted:
            stats["new"] += 1
        try:
            text, page_count = extract_text(path)
        except Exception as exc:  # noqa: BLE001
            update_document(
                conn,
                sha,
                parse_status="failed",
                raw_text_excerpt=str(exc)[:500],
            )
            stats["failed"] += 1
            print(f"{progress} failed to extract {path}: {exc}")
            conn.commit()
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
            stats["skipped"] += 1
            print(f"{progress} skipped {path}")
            conn.commit()
            continue

        year = guess_tax_year(text, classification.doc_type)
        try:
            result = parse_document(
                classification.issuer, classification.doc_type, text, year
            )
            # Soft path hint: Degiro pension jaaropgaves are Box 1.
            if "pensioen" in path.name.lower() and classification.issuer == "degiro":
                for fact in result.facts:
                    if "-pensioen" not in fact.account_key:
                        fact.account_key = f"{fact.account_key}-pensioen"
                    fact.account_label = fact.account_label.replace(
                        "Beleggingsrekening", "Pensioen"
                    )
                    fact.logical_group = None
                    fact.extra = {**(fact.extra or {}), "box3": False}
                    result.notes.append("pensioen filename hint")
            _persist_parse(conn, sha, classification, result, page_count, excerpt)
            stats["parsed"] += 1
            print(
                f"{progress} parsed {classification.issuer}/{classification.doc_type} "
                f"{result.tax_year or year or 'unknown'} {path}"
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
            stats["failed"] += 1
            print(f"{progress} failed to parse {path}: {exc}")
        conn.commit()

    _apply_source_return_rules(conn)
    canonicalize_facts(conn)
    rebuild_portfolio(conn)
    rebuild_recommendations(conn)

    return stats


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


def recompute(db_path: str | Path) -> None:
    conn = connect(db_path)
    init_db(conn)
    _apply_source_return_rules(conn)
    clear_canonical_flags(conn)
    canonicalize_facts(conn)
    rebuild_portfolio(conn)
    rebuild_recommendations(conn)


def _apply_source_return_rules(conn) -> None:
    rows = conn.execute(
        "SELECT id, issuer, account_label, extra FROM account_year_facts"
    ).fetchall()
    for row in rows:
        if not has_zero_return_by_product(row["issuer"], row["account_label"] or ""):
            continue
        extra = json.loads(row["extra"]) if row["extra"] else {}
        extra["return_assumption"] = "zero_by_product"
        conn.execute(
            """
            UPDATE account_year_facts
            SET capital_gain = 0, gain_method = 'explicit', extra = ?
            WHERE id = ?
            """,
            (json.dumps(extra), row["id"]),
        )
    conn.commit()
