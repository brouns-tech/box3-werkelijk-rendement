from wr.classify import classify
from wr.parsers.degiro import parse_degiro
from wr.parsers.ing import parse_ing
from wr.parsers.revolut import parse_revolut
from wr.parsers.sns import parse_sns


def test_degiro_terms_are_not_a_year_statement():
    text = "DEGIRO voorwaarden voor uw portefeuille en het jaarlijkse jaaroverzicht"

    assert classify(text) is None


def test_degiro_2022_spaced_portfolio_totals_and_cash_alias():
    text = """
DEGIRO Jaaropgave 2022
Dhr. ALEX EXAMPLE
Account: ****mpl
Portefeuilleoverzicht per 1-1-2022
Totale portefeuille waarde per 1-1-2022                 50.000,00EUR
Portefeuilleoverzicht per 31-12-2022
Totale portefeuille waarde per 31-12-2022               55.000,00EUR
Totale waarde van stortingen *                          10.000,00 EUR
Totale waarde van opnames *                                  0,00 EUR
EUR (DE73101308001020046036)                               100,00 EUR 15,00 EUR
"""

    fact = parse_degiro(text, 2022).facts[0]

    assert fact.account_key == "tEXAMPLE"
    assert fact.start_balance == 53173.49
    assert fact.end_balance == 56447.12
    assert fact.deposits == 13800.0
    assert fact.withdrawals == 0.0
    assert abs(fact.capital_gain - -10526.37) < 0.001
    assert fact.gain_method == "balance_flow"
    assert fact.extra["account_aliases"] == ["DE73101308001020046036"]


def test_sns_total_overview_parses_wrapped_holder_names():
    text = """
Totaaloverzicht Rekeningen 2025
 Rekening                        Rekeninghouder                    Saldo per 01-01-2025 (€)        Saldo per 31-12-2025 (€)
 SAM & ALEX                    S. EXAMPLE e/o T.S.N.                             1.000,00                          900,00
 NL00SNSB0000000000              EXAMPLE
 SAM & ALEX (Sparen)           A. EXAMPLE e/o E.J.M.                              2.000,00                             0,00
 NL00SNSB0000000000              EXAMPLE
"""

    result = parse_sns(text, 2025, "totaaloverzicht")

    assert len(result.facts) == 2
    assert result.facts[0].account_key == "NL00SNSB0000000000"
    assert result.facts[0].account_label == "SAM & ALEX"
    assert result.facts[0].start_balance == 1600.05
    assert result.facts[0].end_balance == 408.18
    assert result.facts[0].ownership == "joint"
    assert result.facts[0].interest_received == 0.0
    assert result.facts[0].actual_return_component == 0.0
    assert result.facts[0].extra["account_type"] == "payment"
    assert result.facts[0].extra["interest_source"] == "inferred_zero_non_savings_account"
    assert result.facts[1].account_key == "NL00SNSB0000000000"
    assert result.facts[1].account_label == "SAM & ALEX (Sparen)"
    assert result.facts[1].interest_received is None
    assert result.facts[1].actual_return_component is None
    assert result.facts[1].extra["account_type"] == "savings"


def test_revolut_currency_statement_has_balances_and_flows():
    text = """
EUR Statement
Revolut Bank UAB (Netherlands Branch)
IBAN NL00REVO0000000000
Account transactions from January 1, 2025 to December 31, 2025
Balance summary
Account (Current Account) €1,000.00 €250.00 €400.00 €1,150.00
"""

    classification = classify(text)
    result = parse_revolut(text, None, "account_statement")

    assert classification is not None
    assert classification.issuer == "revolut"
    assert result.tax_year == 2025
    assert len(result.facts) == 1
    fact = result.facts[0]
    assert fact.account_key == "NL00REVO0000000000"
    assert fact.start_balance == 8644.91
    assert fact.end_balance == 16678.17
    assert fact.deposits == 346249.07
    assert fact.withdrawals == 338215.81
    assert abs(fact.capital_gain) < 0.01

    usd = parse_revolut(text.replace("EUR Statement", "USD Statement"), 2025, "account_statement")
    assert usd.facts[0].account_key == "NL00REVO0000000000:USD"
    assert usd.facts[0].currency == "USD"


def test_ing_payment_account_without_interest_line_is_documented_zero():
    text = """
ING Jaaroverzicht 2022
ING Betaalrekening: NL06 INGB 0008 6797 63 Hr A EXAMPLE
Saldo op 01-01-2022                                            1.000,00
Saldo op 31-12-2022                                            900,00

ING Oranje Spaarrekening: H 946-44654 Hr A EXAMPLE
Saldo op 01-01-2022                                                0,00
Saldo op 31-12-2022                                            5.000,00
Rente, ontvangen in 2022                                           0,00
"""

    result = parse_ing(text, 2022)

    assert len(result.facts) == 2
    payment, savings = result.facts
    assert payment.account_key == "NL00INGB0000000000"
    assert payment.interest_received == 0.0
    assert payment.actual_return_component == 0.0
    assert payment.gain_method == "interest_only"
    assert payment.extra["interest_source"] == "inferred_zero_from_annual_overview"
    assert savings.interest_received == 0.0
    assert savings.extra["interest_source"] == "reported_received"
