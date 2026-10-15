import json
import sqlite3

import pytest

from wr.classify import classify
from wr.import_pipeline import recompute, run_import
from wr.parsers import parse_document
from wr.parsers.brand_new_day import parse_brand_new_day


def statement(quarter=1, year=2024):
    return f"""Brand New Day
Kwartaaloverzicht
Overzicht {quarter}e kwartaal {year}
Klantnummer 0000000
Beleggingsrekening NL00BNDA******0000
De heer A. Example
Samenstelling en waarde
Totaal € 100,00 € 135,25
Rendement
Totale waarde Inleg en Totale waarde Netto rendement
begin onttrekkingen einde
Totaal € 100,00 € 25,00 € 135,25 € 10,25 8,20 %
Kosten
Servicekosten € 0,25 0,20 %
Kosten Brand New Day Bank € 0,25 0,20 %
Bruto rendement € 10,60 8,48 %
Netto rendement € 10,25 8,20 %
Totale Kosten {year}
Netto rendement € 999,99
"""


@pytest.mark.parametrize("quarter,start,end", [
    (1, "2024-01-01", "2024-03-31"), (2, "2024-04-01", "2024-06-30"),
    (3, "2024-07-01", "2024-09-30"), (4, "2024-10-01", "2024-12-31"),
])
def test_parses_quarterly_evidence_without_annual_page_double_count(quarter, start, end):
    text = statement(quarter)
    classification = classify(text)
    assert classification.issuer == "brand_new_day"
    result = parse_document(classification.issuer, classification.doc_type, text, 1999)
    assert result.tax_year == 2024
    assert result.facts == []
    fact, = result.period_facts
    assert (fact.period_start, fact.period_end) == (start, end)
    assert fact.holder_names == ["A. Example"]
    assert fact.account_key == "NL00BNDA******0000"
    assert (fact.start_balance, fact.end_balance) == (100, 135.25)
    assert fact.capital_gain == 10.50
    assert fact.extra["reported_net_return"] == 10.25
    assert fact.extra["net_cashflow"] == 25
    assert fact.deposits is None and fact.withdrawals is None


@pytest.mark.parametrize("old,new", [
    ("Beleggingsrekening", "Pensioenrekening"),
    ("Overzicht 1e kwartaal 2024", "Overzicht 2024"),
    ("Brand New Day", "Other Bank"),
])
def test_rejects_other_products_and_missing_period(old, new):
    assert classify(statement().replace(old, new)) is None


def test_malformed_return_table_fails_closed():
    with pytest.raises(ValueError, match="totals"):
        parse_brand_new_day(statement().replace("€ 10,25 8,20 %", ""))


def test_inconsistent_totals_and_missing_costs_fail_closed():
    with pytest.raises(ValueError, match="reconcile"):
        parse_brand_new_day(statement().replace("€ 135,25", "€ 999,99"))
    with pytest.raises(ValueError, match="bank costs"):
        parse_brand_new_day(statement().replace("Kosten Brand New Day Bank € 0,25 0,20 %", ""))


def test_signed_return_and_net_flow():
    result = parse_brand_new_day(statement().replace("€ 25,00", "€ -25,00").replace("€ 10,25", "€ -10,25").replace("€ 135,25", "€ 64,75"))
    assert result.period_facts[0].capital_gain == -10
    assert result.period_facts[0].extra["net_cashflow"] == -25


def test_import_persists_periods_and_reprocesses_idempotently(tmp_path, monkeypatch):
    source = tmp_path / "reports"
    source.mkdir()
    for quarter in (2, 3, 4):
        (source / f"q{quarter}.pdf").write_bytes(f"quarter {quarter}".encode())
    monkeypatch.setattr("wr.import_pipeline.extract_text", lambda path: (statement(int(path.stem[1:])), 1))
    db = tmp_path / "wr.sqlite"
    report = run_import(source, db)
    assert (report.parsed, report.failed) == (3, 0)
    assert run_import(source, db).duplicate == 3
    recompute(db)
    with sqlite3.connect(db) as conn:
        conn.row_factory = sqlite3.Row
        assert conn.execute("SELECT COUNT(*) FROM account_period_facts").fetchone()[0] == 3
        fact, = conn.execute("SELECT * FROM account_year_facts")
        assert fact["capital_gain"] == 31.50
        assert fact["start_balance"] is None
        assert fact["end_balance"] == 135.25
        assert len(json.loads(fact["extra"])["period_aggregation"]["sources"]) == 3
        portfolio = conn.execute("SELECT * FROM yearly_portfolio").fetchone()
        assert portfolio["coverage_status"] == "PARTIAL"
        assert "2024-01-01/2024-03-31" in portfolio["missing_asset_summary"]


def test_reprocessing_replaces_old_source_period(tmp_path, monkeypatch):
    source = tmp_path / "reports"
    source.mkdir()
    (source / "q.pdf").write_bytes(b"quarter")
    monkeypatch.setattr("wr.import_pipeline.extract_text", lambda path: (statement(1), 1))
    db = tmp_path / "wr.sqlite"
    run_import(source, db)
    with sqlite3.connect(db) as conn:
        conn.execute("UPDATE documents SET processing_profile = 'obsolete'")
    monkeypatch.setattr("wr.import_pipeline.extract_text", lambda path: (statement(2), 1))
    assert run_import(source, db).parsed == 1
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT period_start FROM account_period_facts").fetchall() == [("2024-04-01",)]
        assert conn.execute("SELECT COUNT(*) FROM account_year_facts").fetchone()[0] == 1
