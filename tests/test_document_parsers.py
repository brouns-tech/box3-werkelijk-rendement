from wr.classify import classify
from wr.models import AccountYearFact
from wr.parsers.degiro import parse_degiro
from wr.parsers.ing import parse_ing
from wr.parsers.revolut import parse_revolut
from wr.parsers.sns import parse_sns
from wr.portfolio import _fact_return


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
EUR (DE00100100000000000000)                               100,00 EUR 15,00 EUR
"""

    fact = parse_degiro(text, 2022).facts[0]

    assert fact.account_key == "masked-mpl"
    assert fact.start_balance == 53173.49
    assert fact.end_balance == 56447.12
    assert fact.deposits == 13800.0
    assert fact.withdrawals == 0.0
    assert abs(fact.capital_gain - -10526.37) < 0.001
    assert fact.gain_method == "balance_flow"


def test_balance_flow_separates_gross_dividend_and_market_value_change():
    fact = AccountYearFact(
        tax_year=2024,
        issuer="broker",
        account_key="account",
        account_label="Broker account",
        start_balance=100.0,
        end_balance=110.0,
        deposits=0.0,
        withdrawals=0.0,
        dividends_gross=5.0,
        withholding_tax=1.0,
    )

    fact.compute_capital_gain()

    assert fact.capital_gain == 6.0
    assert fact.actual_return_component == 11.0
    assert _fact_return(fact.__dict__) == 6.0


def test_sns_total_overview_parses_wrapped_holder_names():
    text = """
Totaaloverzicht Rekeningen 2025
 Rekening                        Rekeninghouder                    Saldo per 01-01-2025 (€)        Saldo per 31-12-2025 (€)
 Shared checking                 ALEX EXAMPLE e/o SAM EXAMPLE                           1.000,00                          900,00
 NL00SNSB0000000000              EXAMPLE
 Shared savings (Sparen)         SAM EXAMPLE e/o ALEX EXAMPLE                            2.000,00                             0,00
 NL00SNSB0000000001              EXAMPLE
"""

    result = parse_sns(text, 2025, "totaaloverzicht")

    assert len(result.facts) == 2
    assert result.facts[0].account_key == "NL00SNSB0000000000"
    assert result.facts[0].account_label == "Shared checking"
    assert result.facts[0].start_balance == 1600.05
    assert result.facts[0].end_balance == 408.18
    assert result.facts[0].ownership == "joint"
    assert result.facts[0].interest_received == 0.0
    assert result.facts[0].actual_return_component == 0.0
    assert result.facts[0].extra["account_type"] == "payment"
    assert result.facts[0].extra["interest_source"] == "inferred_zero_non_savings_account"
    assert result.facts[1].account_key == "NL00SNSB0000000001"
    assert result.facts[1].account_label == "Shared savings (Sparen)"
    assert result.facts[1].interest_received is None
    assert result.facts[1].actual_return_component is None
    assert result.facts[1].extra["account_type"] == "savings"


def test_sns_jaaroverzicht_recovers_ocr_mangled_iban():
    text = """
Financieel overzicht 2024
SNS Bank
NL9ð SNSB 12ó4 56õò óô SNS Internet Sparen * 0,00 1.100,00 0,00 12,34
"""

    result = parse_sns(text, 2024, "jaaroverzicht")

    assert len(result.facts) == 1
    fact = result.facts[0]
    assert fact.account_key == "NL90SNSB1234565234"
    assert fact.interest_received == 127.70


def test_sns_jaaroverzicht_recovers_ocr_mangled_nine():
    text = """
Financieel overzicht 2023
SNS Bank
NL9ð SNSB 12óø ùöõò óô SNS Internet Sparen * 1.000,00 2.000,00 0,00 9,99
"""

    result = parse_sns(text, 2023, "jaaroverzicht")

    assert len(result.facts) == 1
    fact = result.facts[0]
    assert fact.account_key == "NL90SNSB1238965234"
    assert fact.interest_received == 30.69


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
ING Betaalrekening: NL00 INGB 0000 0000 00 Hr ALEX EXAMPLE
Saldo op 01-01-2022                                            1.000,00
Saldo op 31-12-2022                                            900,00

ING Oranje Spaarrekening: H 000-00000 Hr ALEX EXAMPLE
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
    assert payment.gain_method == "explicit"
    assert payment.extra["return_assumption"] == "zero_by_product"
    assert savings.interest_received == 0.0
    assert savings.extra["interest_source"] == "reported_received"
