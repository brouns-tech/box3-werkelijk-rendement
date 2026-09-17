from wr.parsers.ing import parse_ing


ING_2023 = """
Jaaroverzicht 2023
ING Betaalrekening: NL00 INGB 0000 0000 00 Hr Example User
Saldo op 01-01-2023 900,00
Saldo op 31-12-2023 2.318,06
ING Creditcardrekening: 210000000000 Hr Example User*
Saldo op 01-01-2023 -0,99
Saldo op 31-12-2023 0,00
Rente, betaald in 2023 0,00
"""


def test_payment_and_credit_card_accounts_have_explicit_zero_return():
    result = parse_ing(ING_2023)

    assert [(fact.account_key, fact.capital_gain, fact.gain_method) for fact in result.facts] == [
        ("NL00INGB0000000000", 0.0, "explicit"),
        ("210000000000", 0.0, "explicit"),
    ]
    assert all(fact.extra == {"return_assumption": "zero_by_product"} for fact in result.facts)
