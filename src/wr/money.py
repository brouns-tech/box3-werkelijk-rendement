from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from enum import Enum
from typing import Iterable


class Currency(str, Enum):
    EUR = "EUR"
    USD = "USD"
    GBP = "GBP"

    @property
    def symbol(self) -> str:
        return {Currency.EUR: "€", Currency.USD: "$", Currency.GBP: "£"}[self]


CENT = Decimal("0.01")


def decimal_value(value: float | int | str | Decimal) -> Decimal:
    return value if isinstance(value, Decimal) else Decimal(str(value))


def amount(value: float | int | str | Decimal) -> float:
    return float(decimal_value(value).quantize(CENT, rounding=ROUND_HALF_UP))


def add(*values: float | int | str | Decimal) -> float:
    return amount(sum((decimal_value(value) for value in values), Decimal("0")))


def subtract(
    value: float | int | str | Decimal,
    *subtrahends: float | int | str | Decimal,
) -> float:
    result = decimal_value(value)
    for subtrahend in subtrahends:
        result -= decimal_value(subtrahend)
    return amount(result)


def multiply(
    left: float | int | str | Decimal, right: float | int | str | Decimal
) -> float:
    return amount(decimal_value(left) * decimal_value(right))


def total(values: Iterable[float | int | str | Decimal]) -> float:
    return amount(sum((decimal_value(value) for value in values), Decimal("0")))
