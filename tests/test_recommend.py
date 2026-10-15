import sqlite3

import pytest

from wr.config import PartnerSettings
from wr.db import init_db
from wr.recommend import _results_for_year


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

    result = _results_for_year(conn, 2023, PartnerSettings())

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

    result = _results_for_year(
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

    result = _results_for_year(conn, 2025, PartnerSettings())

    assert result[0].fictitious_return == 100


def test_missing_base_keeps_both_partner_decisions_without_zero_tax_claim(tmp_path):
    from wr.config import load_settings
    from wr.db import connect
    from wr.demo import create_demo_workspace

    create_demo_workspace(tmp_path)
    cfg = load_settings(tmp_path)
    with connect(cfg.resolved_db_path) as conn:
        # A stale ZERO_BASE marker must not override an absent input figure.
        conn.execute("UPDATE tax_returns SET grondslag = NULL, allocation_a = NULL, allocation_b = NULL, allocation_status = 'ZERO_BASE'")
        results = _results_for_year(conn, 2024, cfg.partners)
    assert [r.partner for r in results] == ['a', 'b']
    assert [r.partner_name for r in results] == [cfg.partners.partner_a, cfg.partners.partner_b]
    assert all(r.recommendation == 'NEEDS_MANUAL_RSAMW' for r in results)
    assert all(r.estimated_box3_tax_actual is None and r.estimated_tax_savings is None for r in results)


def test_explicit_zero_base_keeps_both_partners_without_allocating_combined_return_twice(tmp_path):
    from wr.config import load_settings
    from wr.db import connect
    from wr.demo import create_demo_workspace

    create_demo_workspace(tmp_path)
    cfg = load_settings(tmp_path)
    with connect(cfg.resolved_db_path) as conn:
        conn.execute("UPDATE tax_returns SET grondslag = 0, allocation_a = NULL, allocation_b = NULL, allocation_status = 'ZERO_BASE'")
        # The filed ordering is the reverse of the configured taxpayer ordering.
        conn.execute("UPDATE tax_returns SET partner_a_name = ?, partner_b_name = ?", (cfg.partners.partner_b, cfg.partners.partner_a))
        results = _results_for_year(conn, 2024, cfg.partners)
    assert [r.partner_name for r in results] == [cfg.partners.partner_a, cfg.partners.partner_b]
    assert all(r.recommendation == 'NOT_APPLICABLE' for r in results)
    assert all(r.estimated_box3_tax_actual == 0 and r.estimated_tax_savings == 0 for r in results)
    assert all(r.allocated_actual_return is None and r.allocation_ratio is None for r in results)


def test_statements_without_returns_keep_all_configured_taxpayers_visible(tmp_path):
    from wr.config import load_settings
    from wr.db import connect
    from wr.demo import create_demo_workspace

    create_demo_workspace(tmp_path)
    cfg = load_settings(tmp_path)
    with connect(cfg.resolved_db_path) as conn:
        conn.execute('DELETE FROM tax_returns')
        results = _results_for_year(conn, 2024, cfg.partners)
    assert [r.partner for r in results] == ['a', 'b']
    assert all(r.recommendation == 'PRE_FILING' for r in results)
    assert all(r.coverage_status == 'COMPLETE' for r in results)
    assert all(r.allocation_ratio is None and r.allocated_actual_return is None for r in results)
    assert all(r.fictitious_return is None and r.estimated_tax_savings is None for r in results)


def test_pre_filing_separate_taxpayers_keep_statement_returns_without_tax_allocation(tmp_path):
    from dataclasses import replace
    from wr.config import load_settings
    from wr.db import connect
    from wr.demo import create_demo_workspace

    create_demo_workspace(tmp_path)
    cfg = load_settings(tmp_path)
    with connect(cfg.resolved_db_path) as conn:
        conn.execute('DELETE FROM tax_returns')
        results = _results_for_year(conn, 2024, replace(cfg.partners, assume_fiscal_partnership=False))
        combined = conn.execute('SELECT known_combined_actual_return FROM yearly_portfolio WHERE tax_year = 2024').fetchone()[0]
    assert all(r.recommendation == 'PRE_FILING' for r in results)
    assert all(r.allocation_ratio is None for r in results)
    assert all(r.estimated_box3_tax_actual is None for r in results)
    assert round(sum(r.allocated_actual_return for r in results), 2) == round(combined, 2)


def test_pre_filing_does_not_hide_missing_statement_data(tmp_path):
    from wr.config import load_settings
    from wr.db import connect
    from wr.demo import create_demo_workspace
    from wr.portfolio import rebuild_portfolio

    create_demo_workspace(tmp_path)
    cfg = load_settings(tmp_path)
    with connect(cfg.resolved_db_path) as conn:
        conn.execute('DELETE FROM tax_returns')
        conn.execute("UPDATE account_year_facts SET currency = 'USD' WHERE tax_year = 2024")
        rebuild_portfolio(conn)
        results = _results_for_year(conn, 2024, cfg.partners)
    assert all(r.recommendation == 'INDETERMINATE_MISSING_DATA' for r in results)
    assert all(r.coverage_status == 'PARTIAL' for r in results)


def test_filed_partnership_overrides_pre_filing_setting(tmp_path):
    from dataclasses import replace
    from wr.config import load_settings
    from wr.db import connect
    from wr.demo import create_demo_workspace

    create_demo_workspace(tmp_path)
    cfg = load_settings(tmp_path)
    with connect(cfg.resolved_db_path) as conn:
        assert _results_for_year(conn, 2024, cfg.partners) == _results_for_year(
            conn, 2024, replace(cfg.partners, assume_fiscal_partnership=False)
        )


@pytest.mark.parametrize('actual', [0, -50, 50])
def test_single_taxpayer_can_prepare_actual_return_without_filing(actual):
    from wr.portfolio import rebuild_portfolio
    from wr.recommend import rebuild_recommendations

    conn = sqlite3.connect(':memory:')
    conn.row_factory = sqlite3.Row
    init_db(conn)
    conn.execute("INSERT INTO documents (content_sha256, byte_size, imported_at, parse_status) VALUES ('statement', 1, '2026-01-01', 'parsed')")
    conn.execute('''
        INSERT INTO account_year_facts (
            document_sha256, tax_year, issuer, account_key, holder_names,
            capital_gain, gain_method, is_canonical
        ) VALUES ('statement', 2025, 'bank', 'savings', '["Alex Example"]', ?, 'explicit', 1)
    ''', (actual,))
    rebuild_portfolio(conn)
    # Infer the single taxpayer from statements, exercising the whole rebuild.
    rebuild_recommendations(conn, PartnerSettings(assume_fiscal_partnership=False))
    result = conn.execute('SELECT * FROM partner_tax_results').fetchone()
    assert result['partner_name'] == 'Alex Example'
    assert result['recommendation'] == 'PRE_FILING'
    assert result['allocated_actual_return'] == actual
    assert result['allocation_ratio'] is None
    assert result['fictitious_return'] is None
    assert result['estimated_box3_tax_actual'] is None
