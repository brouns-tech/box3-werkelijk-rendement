from __future__ import annotations

import sqlite3

from wr.importing.classification import Classification
from wr.models.parsing import ParseResult
from wr.storage.documents import update_document
from wr.storage.facts import insert_facts
from wr.storage.tax_returns import insert_tax_return


def persist_parse(conn: sqlite3.Connection, sha: str, classification: Classification, result: ParseResult, page_count: int, excerpt: str) -> None:
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

    for fact in result.facts:
        fact.compute_capital_gain()
    if result.facts:
        insert_facts(conn, sha, result.facts)

    if result.tax_return is not None:
        insert_tax_return(conn, sha, result.tax_return)
