import sqlite3

from wr.models.settings import PartnerSettings
from wr.storage.migrations import init_db
from wr.calculations.service import results_for_year


def test_individual_return_uses_taxpayer_from_return_without_configuration():
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

    result = results_for_year(conn, 2023, PartnerSettings())

    assert len(result) == 1
    assert result[0].partner_name == "Alex Example"
    assert result[0].allocation_ratio == 1.0
    assert result[0].recommendation == "ACTUAL_BETTER"


def test_single_configured_taxpayer_does_not_create_empty_partner_result():
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
        ) VALUES ('return', 2023, 'Sophie de Vries', 0, 100, 32)
        """
    )
    conn.execute(
        """
        INSERT INTO account_year_facts (
            document_sha256, tax_year, issuer, account_key, holder_names,
            capital_gain, gain_method, is_canonical
        ) VALUES ('return', 2023, 'bank', 'example', '["S. de Vries"]',
                  50, 'explicit', 1)
        """
    )
    conn.commit()

    result = results_for_year(
        conn,
        2023,
        PartnerSettings(
            partner_a="Sophie de Vries",
            partner_a_aliases=("S. de Vries",),
        ),
    )

    assert len(result) == 1
    assert result[0].partner == "a"
    assert result[0].partner_name == "Sophie de Vries"


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

    result = results_for_year(conn, 2025, PartnerSettings())

    assert result[0].fictitious_return == 100


def test_missing_base_keeps_both_partner_decisions_without_zero_tax_claim(tmp_path):
    from wr.workspace.settings import load_settings
    from wr.storage.connection import connect
    from wr.demo import create_demo_workspace

    create_demo_workspace(tmp_path)
    cfg = load_settings(tmp_path)
    with connect(cfg.resolved_db_path) as conn:
        # A stale ZERO_BASE marker must not override an absent input figure.
        conn.execute("UPDATE tax_returns SET grondslag = NULL, allocation_a = NULL, allocation_b = NULL, allocation_status = 'ZERO_BASE'")
        results = results_for_year(conn, 2024, cfg.partners)
    assert [r.partner for r in results] == ['a', 'b']
    assert [r.partner_name for r in results] == [cfg.partners.partner_a, cfg.partners.partner_b]
    assert all(r.recommendation == 'NEEDS_MANUAL_RSAMW' for r in results)
    assert all(r.estimated_box3_tax_actual is None and r.estimated_tax_savings is None for r in results)


def test_explicit_zero_base_keeps_both_partners_without_allocating_combined_return_twice(tmp_path):
    from wr.workspace.settings import load_settings
    from wr.storage.connection import connect
    from wr.demo import create_demo_workspace

    create_demo_workspace(tmp_path)
    cfg = load_settings(tmp_path)
    with connect(cfg.resolved_db_path) as conn:
        conn.execute("UPDATE tax_returns SET grondslag = 0, allocation_a = NULL, allocation_b = NULL, allocation_status = 'ZERO_BASE'")
        # The filed ordering is the reverse of the configured taxpayer ordering.
        conn.execute("UPDATE tax_returns SET partner_a_name = ?, partner_b_name = ?", (cfg.partners.partner_b, cfg.partners.partner_a))
        results = results_for_year(conn, 2024, cfg.partners)
    assert [r.partner_name for r in results] == [cfg.partners.partner_a, cfg.partners.partner_b]
    assert all(r.recommendation == 'NOT_APPLICABLE' for r in results)
    assert all(r.estimated_box3_tax_actual == 0 and r.estimated_tax_savings == 0 for r in results)
    assert all(r.allocated_actual_return is None and r.allocation_ratio is None for r in results)


def test_statements_without_returns_keep_all_configured_taxpayers_visible(tmp_path):
    from wr.workspace.settings import load_settings
    from wr.storage.connection import connect
    from wr.demo import create_demo_workspace

    create_demo_workspace(tmp_path)
    cfg = load_settings(tmp_path)
    with connect(cfg.resolved_db_path) as conn:
        conn.execute('DELETE FROM tax_returns')
        results = results_for_year(conn, 2024, cfg.partners)
    assert [r.partner for r in results] == ['a', 'b']
    assert all(r.recommendation == 'NEEDS_MANUAL_RSAMW' for r in results)
    assert all(r.fictitious_return is None and r.estimated_tax_savings is None for r in results)
