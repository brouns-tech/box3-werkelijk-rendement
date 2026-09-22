from wr.money import add, multiply, subtract


def test_money_arithmetic_rounds_at_currency_boundary():
    assert add(0.1, 0.2) == 0.3
    assert subtract(10.0, 3.335) == 6.67
    assert multiply(10.01, 0.36) == 3.60
