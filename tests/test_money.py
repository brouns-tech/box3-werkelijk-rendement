import json

import pytest

from wr.models import AccountYearFact
from wr.models.storage import FactRecord, MoneyField
from wr.money import Currency, add, multiply, subtract
from wr.calculations.coverage import _sum
from wr.export import _optional_net, _optional_sum


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


@pytest.mark.parametrize("field", list(MoneyField))
def test_money_field_aggregations_preserve_zero_and_missing_values(field):
    rows = [FactRecord.model_validate({field.value: amount}) for amount in (1.25, None, 0, -0.25)]
    assert _sum(rows, field) == 1.0
    assert _optional_sum(rows, field) == 1.0
    assert _sum([FactRecord()], field) == 0.0
    assert _optional_sum([FactRecord()], field) is None
    assert _optional_sum([FactRecord.model_validate({field.value: 0})], field) == 0.0


@pytest.mark.parametrize("positive,negative", [
    (MoneyField.INTEREST_RECEIVED, MoneyField.INTEREST_PAID),
    (MoneyField.DIVIDENDS_GROSS, MoneyField.WITHHOLDING_TAX),
])
@pytest.mark.parametrize("income,expense,expected", [
    (10, 2, 8), (10, None, 10), (None, 2, -2), (None, None, None), (0, 0, 0),
])
def test_net_income_uses_enum_fields_and_preserves_missing_values(positive, negative, income, expense, expected):
    rows = [FactRecord.model_validate({positive.value: income, negative.value: expense})]
    assert _optional_net(iter(rows), positive, negative) == expected
