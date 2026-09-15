import csv
import io
import json
import sqlite3
import zipfile

from wr.db import init_db
from wr.export import create_audit_export


def _csv_rows(bundle: zipfile.ZipFile, name: str) -> list[dict[str, str]]:
    text = bundle.read(name).decode("utf-8-sig")
    return list(csv.DictReader(io.StringIO(text)))


def test_audit_export_traces_asset_return_to_source_document():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_db(conn)
    conn.execute(
        """
        INSERT INTO documents (content_sha256, byte_size, first_seen_path, imported_at,
                               issuer, doc_type, tax_year, parse_status)
        VALUES ('source-sha', 10, '/statements/account.pdf', 'now',
                'bank', 'annual_statement', 2023, 'parsed')
        """
    )
    conn.execute(
        """
        INSERT INTO account_year_facts (document_sha256, tax_year, issuer, account_key, account_label,
                                        currency, start_balance, end_balance, deposits, withdrawals,
                                        interest_received, interest_paid, gain_method, is_canonical)
        VALUES ('source-sha', 2023, 'bank', 'NL01BANK', 'Savings',
                'EUR', 1000, 1200, 150, 0, 50, 0, 'interest_only', 1)
        """
    )
    fact_id = conn.execute("SELECT id FROM account_year_facts").fetchone()[0]
    conn.execute(
        """
        INSERT INTO declared_box3_assets (tax_year, category, institution, account_id, label,
                                          balance_0101, balance_3112, coverage_status, matched_fact_ids)
        VALUES (2023, 'bank', 'Bank', 'NL01BANK', 'Savings',
                1000, 1200, 'COMPLETE', ?)
        """,
        (json.dumps([fact_id]),),
    )
    conn.execute(
        """
        INSERT INTO yearly_portfolio (tax_year, coverage_status, known_combined_actual_return,
                                      start_balance, end_balance, deposits, withdrawals,
                                      interest_received, dividends_net, capital_gain,
                                      source_fact_count, missing_asset_summary)
        VALUES (2023, 'COMPLETE', 50, 1000, 1200, 150, 0, 50, 0, 50, 1, NULL)
        """
    )

    payload = create_audit_export(conn, [2023])

    with zipfile.ZipFile(io.BytesIO(payload)) as bundle:
        assert set(bundle.namelist()) == {
            "manifest.json",
            "yearly_summary.csv",
            "assets.csv",
            "source_facts.csv",
            "partner_tax_results.csv",
        }
        asset = _csv_rows(bundle, "assets.csv")[0]
        fact = _csv_rows(bundle, "source_facts.csv")[0]
        summary = _csv_rows(bundle, "yearly_summary.csv")[0]

    assert asset["declared_start_capital"] == "1000.0"
    assert asset["source_end_capital"] == "1200.0"
    assert asset["return_used"] == "50.0"
    assert asset["source_document_sha256s"] == "source-sha"
    assert fact["source_path"] == "/statements/account.pdf"
    assert fact["included_in_year_total"] == "True"
    assert summary["actual_return_used"] == "50.0"


def test_audit_export_makes_missing_asset_zero_return_assumption_explicit():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_db(conn)
    conn.execute(
        """
        INSERT INTO declared_box3_assets (tax_year, category, institution, account_id, label,
                                          balance_0101, balance_3112, coverage_status, matched_fact_ids)
        VALUES (2022, 'investment', 'Broker', 'missing', 'Portfolio',
                5000, 4500, 'MISSING', '[]')
        """
    )

    with zipfile.ZipFile(io.BytesIO(create_audit_export(conn, [2022]))) as bundle:
        asset = _csv_rows(bundle, "assets.csv")[0]

    assert asset["return_used"] == "0.0"
    assert "0% assumption" in asset["return_basis"]
    assert asset["coverage_status"] == "MISSING"
