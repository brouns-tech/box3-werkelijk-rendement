import json

import pytest

from wr.models import AccountYearFact
from wr.money import Currency, add, multiply, subtract


def test_money_arithmetic_rounds_at_currency_boundary():
    assert add(0.1, 0.2) == 0.3
    assert subtract(10.0, 3.335) == 6.67
    assert multiply(10.01, 0.36) == 3.60


@pytest.mark.parametrize("code,symbol", [("EUR", "€"), ("USD", "$"), ("GBP", "£")])
def test_currency_enum_validates_facts_and_preserves_serialized_codes(code, symbol):
    currency = Currency(code)
    fact = AccountYearFact(2025, "bank", "account", "Account", currency=code)
    assert fact.currency is currency
    assert currency.symbol == symbol
    assert json.dumps({"currency": fact.currency}) == f'{{"currency": "{code}"}}'


def test_account_currency_defaults_to_eur_and_rejects_unsupported_codes():
    assert AccountYearFact(2025, "bank", "account", "Account").currency is Currency.EUR
    with pytest.raises(ValueError, match="not a valid Currency"):
        AccountYearFact(2025, "bank", "account", "Account", currency="XYZ")
