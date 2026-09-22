from wr.classify import classify
from wr.parsers.rabobank import parse_rabobank


RABOBANK_2024 = """
Example User
Onderwerp Financieel Jaaroverzicht 2024

Betalen
NL00 RABO 0000 0000 01 EUR Rabo BasisRekening
Saldo 01-01-2024 1.000,00 C
Saldo 31-12-2024 1.100,00 C
Door u ontvangen rente in 2024 0,00
Door u betaalde rente in 2024 0,00

Creditcards
NL00 RABO 0000 0000 01 EUR Rabobank creditcard(s)
Saldo 01-01-2024 500,00 D
Saldo 31-12-2024 0,00

Sparen
NL00 RABO 0000 0000 02 EUR Rabo SpaarRekening
Saldo 01-01-2024 20.000,00 C
Saldo 31-12-2024 21.000,00 C
Door u ontvangen rente in 2024 200,00
"""


def test_classifies_rabobank_financial_overview():
    classification = classify(RABOBANK_2024)
    assert classification is not None
    assert (classification.issuer, classification.doc_type) == ("rabobank", "jaaroverzicht")


def test_parses_deposit_accounts_and_excludes_credit_card():
    result = parse_rabobank(RABOBANK_2024)

    assert result.tax_year == 2024
    assert [(fact.account_key, fact.account_label) for fact in result.facts] == [
        ("NL00RABO0000000001", "Rabobank Rabo BasisRekening"),
        ("NL00RABO0000000002", "Rabobank Rabo SpaarRekening"),
    ]
    assert result.facts[0].start_balance == 1000.0
    assert result.facts[0].end_balance == 1100.0
    assert result.facts[0].interest_received == 0.0
    assert result.facts[1].interest_received == 200.0
