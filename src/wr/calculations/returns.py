from __future__ import annotations

from wr.models.storage import FactRecord
from wr.money import add, subtract


def is_excluded_box3_fact(fact: FactRecord) -> bool:
    key = (fact.account_key or "").lower()
    label = (fact.account_label or "").lower()
    if key.endswith("-pensioen") or "pensioen" in label:
        return True
    return fact.extra.box3 is False


def is_box3_fact(fact: FactRecord) -> bool:
    return not is_excluded_box3_fact(fact)


def has_actual_return(fact: FactRecord) -> bool:
    if fact.currency != "EUR":
        return False
    if native_fact_return(fact) is None:
        return False
    if fact.interest_received is not None:
        return True
    if fact.dividends_gross is not None:
        return True
    if fact.capital_gain is not None and fact.gain_method in {
        "balance_flow",
        "earned_return",
        "interest_only",
        "explicit",
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


def fact_return(fact: FactRecord) -> float | None:
    """Return usable in EUR totals; native-currency evidence stays separate."""
    if fact.currency != "EUR":
        return None
    return native_fact_return(fact)


def native_fact_return(fact: FactRecord) -> float | None:
    method = fact.gain_method or ""
    if method == "earned_return" and fact.capital_gain is not None:
        return fact.capital_gain
    if method == "balance_flow":
        required = ("start_balance", "end_balance", "deposits", "withdrawals")
        if all(getattr(fact, field) is not None for field in required):
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
    if method == "interest_only":
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
    if fact.capital_gain is not None and method not in {"interest_only", "balance_delta_incomplete"}:
        if not has:
            total = add(total, fact.capital_gain)
            has = True
    return total if has else None
