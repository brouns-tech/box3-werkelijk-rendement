import sqlite3

from wr.db import init_db
from wr.recommend import _results_for_year


def test_non_full_year_return_compares_main_issuer():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_db(conn)
    conn.execute(
        """
        INSERT INTO documents (content_sha256, byte_size, imported_at, parse_status)
        VALUES ('return', 1, '2026-01-01T00:00:00+00:00', 'parsed')
        """
    )
    conn.execute(
        """
        INSERT INTO tax_returns (
            document_sha256, tax_year, filer_name, full_year_fiscal_partners,
            voordeel_a, box3_tax_a
        ) VALUES ('return', 2023, 'Alex Example', 0, 100, 32)
        """
    )
    conn.execute(
        """
        INSERT INTO yearly_portfolio (
            tax_year, coverage_status, known_combined_actual_return,
            start_balance, end_balance, deposits, withdrawals,
            interest_received, dividends_net, capital_gain, source_fact_count
        ) VALUES (2023, 'COMPLETE', 50, 0, 0, 0, 0, 0, 0, 0, 1)
        """
    )
    conn.execute(
        """
        INSERT INTO account_year_facts (
            document_sha256, tax_year, issuer, account_key, holder_names,
            capital_gain, gain_method, is_canonical
        ) VALUES ('return', 2023, 'bank', 'example', '["Alex Example"]',
                  50, 'explicit', 1)
        """
    )
    conn.commit()

    result = _results_for_year(conn, 2023, {})

    assert len(result) == 1
    assert result[0].partner_name == "Alex Example"
    assert result[0].allocation_ratio == 1.0
    assert result[0].recommendation == "ACTUAL_BETTER"


def test_prefers_sent_tax_return_over_unsent_draft():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_db(conn)
    for sha, status, benefit in (
        ("sent", "Verzonden: Aangifte Inkomstenbelasting 2025", 100),
        ("draft", "Nog niet verstuurd: Aangifte Inkomstenbelasting 2025", 200),
    ):
        conn.execute(
            """
            INSERT INTO documents (content_sha256, byte_size, imported_at, parse_status, raw_text_excerpt)
            VALUES (?, 1, '2026-01-01T00:00:00+00:00', 'parsed', ?)
            """,
            (sha, status),
        )
        conn.execute(
            """
            INSERT INTO tax_returns (
                document_sha256, tax_year, filer_name, full_year_fiscal_partners,
                voordeel_a, box3_tax_a
            ) VALUES (?, 2025, 'Alex Example', 0, ?, 32)
            """,
            (sha, benefit),
        )
    conn.execute(
        """
        INSERT INTO yearly_portfolio (
            tax_year, coverage_status, known_combined_actual_return,
            start_balance, end_balance, deposits, withdrawals,
            interest_received, dividends_net, capital_gain, source_fact_count
        ) VALUES (2025, 'COMPLETE', 50, 0, 0, 0, 0, 0, 0, 0, 1)
        """
    )
    conn.commit()

    result = _results_for_year(conn, 2025, {})

    assert result[0].fictitious_return == 100
