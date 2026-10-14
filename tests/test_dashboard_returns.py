import json
from dataclasses import asdict
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from dashboard.app import _overview_return_totals, _return_components
from wr.config import PartnerSettings, Settings, save_settings
from wr.db import connect, init_db, insert_facts
from wr.models import AccountYearFact
from wr.portfolio import rebuild_portfolio


def fund(code, income, fx):
    return AccountYearFact(
        2025, "example", f"example:fund:{code.lower()}", f"Example fund ({code})",
        holder_names=["Alex Example"], ownership="individual", currency="EUR",
        capital_gain=income + fx, gain_method="earned_return",
        extra={"earned_return": income, "fx_gain": fx, "fund_currency": code},
    )


def test_income_and_currency_components_reconcile_without_deducting_fees():
    usd = fund("USD", 40.9876, -60)
    usd.extra["fees"] = -13.9876
    assert _return_components(asdict(usd)) == {
        "earned": 40.9876, "currency": -60, "other": 0,
        "effective": pytest.approx(-19.0124),
    }
    eur = fund("EUR", 33.1234, 0)
    # SQLite stores extras as JSON; dataclasses carry the same evidence as a dict.
    stored = asdict(eur)
    stored["extra"] = json.dumps(stored["extra"])
    assert _return_components(stored)["currency"] == 0
    assert _overview_return_totals([asdict(usd), stored]) == {
        "earned": 74.11, "currency": -60, "other": 0, "effective": 14.11,
    }


def test_eur_accounts_never_report_currency_loss():
    for fact in [AccountYearFact(2025, "example", "cash", "Cash", interest_received=20, gain_method="interest_only"),
                 AccountYearFact(2025, "example", "unknown", "Unknown")]:
        assert _return_components(asdict(fact))["currency"] == 0


def test_market_value_changes_are_separate_from_income():
    fact = AccountYearFact(
        2025, "example", "shares", "Shares", dividends_gross=5,
        start_balance=100, end_balance=125, deposits=0, withdrawals=0,
        capital_gain=20, gain_method="balance_flow",
    )
    result = _return_components(asdict(fact))
    assert result == {"earned": 5, "currency": 0, "other": 25, "effective": 30}


def test_unconverted_foreign_income_is_not_mislabelled_as_eur_or_zero_fx():
    foreign = AccountYearFact(
        2025, "example", "usd", "USD cash", currency="USD",
        interest_received=10, gain_method="interest_only",
    )
    result = _return_components(asdict(foreign))
    assert result == {"earned": 10, "currency": None, "other": None, "effective": None}
    excluded = fund("EUR", 999, 0)
    excluded.extra["box3"] = False
    assert _overview_return_totals([asdict(foreign), asdict(excluded)]) == {
        "earned": 0, "currency": 0, "other": 0, "effective": 0,
    }


@pytest.mark.parametrize("language,labels,amounts", [
    ("en", ["Earned return", "Currency gain / loss", "Effective return"],
     ["€ 74.11", "€ -60.00", "€ 14.11"]),
    ("nl", ["Verdiend rendement", "Valutawinst / -verlies", "Effectief rendement"],
     ["€ 74,11", "€ -60,00", "€ 14,11"]),
])
def test_dashboard_shows_separate_totals_and_account_components(tmp_path, monkeypatch, language, labels, amounts):
    import sys
    from wr.desktop_storage import remember_language

    settings = Settings(project_root=tmp_path, partners=PartnerSettings(partner_a="Alex Example"))
    save_settings(settings)
    remember_language(tmp_path, language)
    with connect(settings.resolved_db_path) as conn:
        init_db(conn)
        conn.execute("INSERT INTO documents(content_sha256,byte_size,imported_at,parse_status,processing_profile) VALUES('synthetic',1,'now','parsed','synthetic-demo-v1')")
        insert_facts(conn, "synthetic", [asdict(f) for f in [fund("USD", 40.9876, -60), fund("EUR", 33.1234, 0)]])
        conn.execute("UPDATE account_year_facts SET is_canonical=1")
        rebuild_portfolio(conn)
    monkeypatch.setattr(sys, "argv", ["app.py", "--workspace", str(tmp_path)])
    monkeypatch.delenv("WR_CONTROL_URL", raising=False)
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "dashboard/app.py")).run()
    assert not app.exception
    metrics = {metric.label: metric.value for metric in app.metric}
    assert [metrics[label] for label in labels] == amounts
    frame = next(frame.value for frame in app.dataframe if ("Account label" if language == "en" else "Rekeningnaam") in frame.value.columns)
    name = "Account label" if language == "en" else "Rekeningnaam"
    fx_label = "Currency gain / loss (EUR)" if language == "en" else "Valutawinst / -verlies (EUR)"
    effective_label = "Effective return (EUR)" if language == "en" else "Effectief rendement (EUR)"
    usd = frame[frame[name] == "Example fund (USD)"].iloc[0]
    eur = frame[frame[name] == "Example fund (EUR)"].iloc[0]
    assert usd[labels[0]] == ("€ 40.99" if language == "en" else "€ 40,99")
    assert usd[fx_label] == amounts[1]
    assert usd[effective_label] == ("€ -19.01" if language == "en" else "€ -19,01")
    assert eur[fx_label] == ("€ 0.00" if language == "en" else "€ 0,00")
