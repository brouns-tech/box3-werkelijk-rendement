from __future__ import annotations

from wr.models.facts import GainMethod
from wr.models.storage import FactValues, MoneyField
from wr.money import Currency, add, subtract


def has_actual_return(fact: FactValues) -> bool:
    if fact.currency != Currency.EUR:
        return False
    if native_fact_return(fact) is None:
        return False
    if fact.interest_received is not None:
        return True
    if fact.dividends_gross is not None:
        return True
    if fact.capital_gain is not None and fact.gain_method in {
        GainMethod.BALANCE_FLOW,
        GainMethod.EARNED_RETURN,
        GainMethod.INTEREST_ONLY,
        GainMethod.EXPLICIT,
    }:
        return True
    # Start/end alone without flows is not enough for investments
    if (
        fact.start_balance is not None
        and fact.end_balance is not None
        and fact.deposits is not None
        and fact.withdrawals is not None
    ):
        return True
    return False


def fact_return(fact: FactValues) -> float | None:
    """Return usable in EUR totals; native-currency evidence stays separate."""
    if fact.currency != Currency.EUR:
        return None
    return native_fact_return(fact)


def native_fact_return(fact: FactValues) -> float | None:
    if fact.has_conflicts:
        return None
    method = fact.gain_method or GainMethod.UNKNOWN
    if method == GainMethod.EARNED_RETURN and fact.capital_gain is not None:
        return fact.capital_gain
    if method == GainMethod.BALANCE_FLOW:
        required = (
            MoneyField.START_BALANCE,
            MoneyField.END_BALANCE,
            MoneyField.DEPOSITS,
            MoneyField.WITHDRAWALS,
        )
        if all(getattr(fact, field.value) is not None for field in required):
            balance_return = add(
                subtract(
                    fact.end_balance, fact.start_balance, fact.deposits
                ),
                fact.withdrawals,
            )
            return add(
                balance_return,
                fact.dividends_gross or 0,
                fact.interest_received or 0,
                -(fact.interest_paid or 0),
            )
        return fact.capital_gain
    if method == GainMethod.INTEREST_ONLY:
        return subtract(fact.interest_received or 0, fact.interest_paid or 0)
    total = 0.0
    has = False
    if fact.interest_received is not None or fact.interest_paid is not None:
        total = add(
            total,
            subtract(fact.interest_received or 0, fact.interest_paid or 0),
        )
        has = True
    if fact.dividends_gross is not None:
        total = add(
            total,
            subtract(fact.dividends_gross, fact.withholding_tax or 0),
        )
        has = True
    if fact.capital_gain is not None and method not in {GainMethod.INTEREST_ONLY, GainMethod.BALANCE_DELTA_INCOMPLETE}:
        if not has or method == GainMethod.EXPLICIT:
            total = add(total, fact.capital_gain)
            has = True
    return total if has else None
