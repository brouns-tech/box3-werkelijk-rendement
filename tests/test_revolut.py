
from wr.storage.adapters import fact_from_row

from wr.storage.facts import canonical_facts
import sqlite3

import pytest

from wr.storage.migrations import init_db
from wr.storage.facts import insert_facts
from wr.i18n import currency
from wr.money import Currency
from wr.models import GainMethod, Ownership
from wr.parsers.revolut import parse_revolut
from wr.calculations.coverage import coverage_for_year
from wr.calculations.returns import has_actual_return, fact_return, native_fact_return


@pytest.mark.parametrize("code,symbol", [("EUR", "€"), ("USD", "$"), ("GBP", "£")])
def test_deposit_interest_is_separate_from_money_in_and_current_account(code, symbol):
    text = f"""
{code} Statement
Revolut Bank UAB (Netherlands Branch)
ALEX EXAMPLE
IBAN NL00REVO0000000000
Balance summary
Account (Current Account) {symbol}0.00 {symbol}1,000.00 {symbol}1,000.00 {symbol}0.00
Deposit {symbol}0.00 {symbol}100.00 {symbol}1,005.00 {symbol}905.00
Total {symbol}0.00 {symbol}1,100.00 {symbol}2,005.00 {symbol}905.00
Account transactions from January 1, 2025 to December 31, 2025
Jan 1, 2025 To Instant Access Savings {symbol}1,000.00 {symbol}0.00
Deposit transactions from January 1, 2025 to December 31, 2025
Jan 1, 2025 To Instant Access Savings {symbol}1,000.00 {symbol}1,000.00
Jan 2, 2025 Net Interest Paid to 'Instant Access Savings' for Jan 2, {symbol}2.00 {symbol}1,002.00
2025
\f
{code} Statement
Jan 3, 2025 Net Interest Paid to 'Instant Access Savings' for Jan 3, {symbol}3.00 {symbol}1,005.00
2025
Jan 4, 2025 From Instant Access Savings {symbol}100.00 {symbol}905.00
"""
    current, deposit = parse_revolut(text, 2025, "account_statement").facts
    assert current.holder_names == deposit.holder_names == ["ALEX EXAMPLE"]
    assert current.currency == deposit.currency == code
    assert current.currency is deposit.currency is Currency(code)
    suffix = "" if code == "EUR" else f":{code}"
    assert current.account_key == f"NL00REVO0000000000{suffix}"
    assert current.account_key != deposit.account_key
    assert current.interest_received == 0
    assert deposit.interest_received == 5
    assert deposit.deposits == 1000
    assert deposit.withdrawals == 100
    assert deposit.end_balance == 905
    assert native_fact_return(fact_from_row(deposit.__dict__)) == 5
    assert fact_return(fact_from_row(deposit.__dict__)) == (5 if code == "EUR" else None)
    assert currency(deposit.interest_received, "en", code) == f"{symbol} 5.00"
    assert currency(1000, "nl", code) == f"{symbol} 1.000,00"


def test_summary_alone_does_not_prove_zero_deposit_interest():
    result = parse_revolut("""
EUR Statement
IBAN NL00REVO0000000000
Account (Current Account) €0.00 €100.00 €100.00 €0.00
Deposit €0.00 €0.00 €105.00 €105.00
""", 2025, "account_statement")
    assert result.facts[1].interest_received is None
    assert fact_return(fact_from_row(result.facts[1].__dict__)) is None
    assert not has_actual_return(fact_from_row(result.facts[1].__dict__))


def test_foreign_currency_never_enters_eur_rollup():
    from wr.models import AccountYearFact
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_db(conn)
    conn.execute("INSERT INTO documents (content_sha256, byte_size, imported_at, parse_status) VALUES ('test', 1, 'now', 'parsed')")
    insert_facts(conn, 'test', [fact.__dict__ for fact in [
        AccountYearFact(2025, 'bank', 'eur', 'EUR', interest_received=10, gain_method='interest_only'),
        AccountYearFact(2025, 'bank', 'usd', 'USD', currency='USD', end_balance=1000, interest_received=20, gain_method='interest_only'),
    ]])
    conn.execute("UPDATE account_year_facts SET is_canonical=1")
    result = coverage_for_year(2025, canonical_facts(conn, 2025))
    assert result.known_combined_actual_return == result.interest_received == 10
    assert result.end_balance == 0
    assert result.coverage_status == 'PARTIAL'
    assert any('requires EUR conversion' in message for message in result.missing)
    from wr.export import _asset_and_fact_rows
    assets, sources = _asset_and_fact_rows(conn, 2025)
    usd = next(row for row in sources if row.currency == 'USD')
    assert usd.currency is Currency.USD
    assert usd.ownership is Ownership.UNKNOWN
    assert usd.gain_method is GainMethod.INTEREST_ONLY
    assert usd.model_dump(mode="json")["ownership"] == "unknown"
    assert usd.model_dump(mode="json")["gain_method"] == "interest_only"
    assert usd.model_dump(mode="json")["currency"] == "USD"
    assert usd.native_actual_return == 20
    assert usd.calculated_actual_return is None
    assert not usd.included_in_year_total
    assert usd.exclusion_reason == 'requires EUR conversion'


def test_database_rejects_unsupported_currency():
    from wr.models import AccountYearFact

    conn = sqlite3.connect(":memory:")
    init_db(conn)
    fact = AccountYearFact(2025, "bank", "account", "Account").__dict__
    fact["currency"] = "XYZ"
    with pytest.raises(ValueError, match="currency"):
        insert_facts(conn, "test", [fact])


def test_currency_formatter_rejects_unsupported_currency():
    with pytest.raises(ValueError, match="not a valid Currency"):
        currency(5, currency_code="XYZ")


def test_decision_table_distinguishes_holder_return_from_zero_tax_allocation():
    from dashboard.app import _decision_rows
    rows = _decision_rows([{
        'taxpayer_position': 'a', 'taxpayer_name': 'Alex Example', 'allocation_ratio': 0,
        'allocated_actual_return': 0, 'fictitious_return': 0,
        'estimated_box3_tax_actual': 0, 'estimated_box3_tax_fictitious': 0,
        'recommendation': 'EQUAL',
    }], statement_returns={'a': 1500})
    assert rows[0]['Statement return by holder'] == '€ 1,500.00'
    assert rows[0]['Allocated actual return'] == '€ 0.00'
    assert rows[0]['Tax allocation'] == '0%'
