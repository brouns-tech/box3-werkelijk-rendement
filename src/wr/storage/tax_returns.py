from __future__ import annotations

import sqlite3

from wr.models.storage import TaxReturnRecord
from wr.models.tax import TaxReturnData


def insert_tax_return(conn: sqlite3.Connection, sha: str, tr: TaxReturnData) -> None:
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


def returns_for_year(conn: sqlite3.Connection, year: int) -> list[TaxReturnRecord]:
    rows = conn.execute(
        """
        SELECT t.*, d.raw_text_excerpt
        FROM tax_returns t JOIN documents d ON d.content_sha256 = t.document_sha256
        WHERE t.tax_year = ? ORDER BY t.id
        """, (year,)
    ).fetchall()
    return [TaxReturnRecord.model_validate(dict(row)) for row in rows]


def primary_return(conn: sqlite3.Connection, year: int) -> TaxReturnRecord | None:
    row = conn.execute(
        "SELECT * FROM tax_returns WHERE tax_year = ? "
        "ORDER BY full_year_fiscal_partners DESC, grondslag DESC LIMIT 1", (year,)
    ).fetchone()
    return TaxReturnRecord.model_validate(dict(row)) if row is not None else None
