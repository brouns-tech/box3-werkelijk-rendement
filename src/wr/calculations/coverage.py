from __future__ import annotations

from wr.calculations.returns import fact_return, has_actual_return
from wr.models import CoverageStatus
from wr.models.calculations import CoverageResult
from wr.models.storage import FactRecord, MoneyField
from wr.money import Currency, add, subtract, total


def coverage_for_year(year: int, facts: list[FactRecord]) -> CoverageResult:
    missing: list[str] = []
    eligible_facts = [f for f in facts if f.extra.box3]

    for fact in eligible_facts:
        if (fact.currency or Currency.EUR) != Currency.EUR:
            missing.append(f"{fact.issuer} {fact.account_key} (requires EUR conversion and currency gain/loss)")
        elif not has_actual_return(fact):
            missing.append(
                f"{fact.issuer} {fact.account_key} (no actual-return fields)"
            )

    used_facts = [f for f in eligible_facts if (f.currency or Currency.EUR) == Currency.EUR]
    start = _sum(used_facts, MoneyField.START_BALANCE)
    end = _sum(used_facts, MoneyField.END_BALANCE)
    deposits = _sum(used_facts, MoneyField.DEPOSITS)
    withdrawals = _sum(used_facts, MoneyField.WITHDRAWALS)
    interest = subtract(
        _sum(used_facts, MoneyField.INTEREST_RECEIVED), _sum(used_facts, MoneyField.INTEREST_PAID)
    )
    dividends = subtract(
        _sum(used_facts, MoneyField.DIVIDENDS_GROSS), _sum(used_facts, MoneyField.WITHHOLDING_TAX)
    )
    capital = 0.0
    known_return = 0.0
    for f in used_facts:
        known_return = add(known_return, fact_return(f) or 0.0)
        if f.capital_gain is not None:
            capital = add(capital, f.capital_gain)

    if not eligible_facts:
        coverage = CoverageStatus.UNKNOWN.value
        missing.append("no canonical Box 3 statements for this year")
    elif missing:
        coverage = CoverageStatus.PARTIAL.value
    else:
        coverage = CoverageStatus.COMPLETE.value

    return CoverageResult(
        tax_year=year,
        coverage_status=coverage,
        known_combined_actual_return=known_return if used_facts else None,
        start_balance=start,
        end_balance=end,
        deposits=deposits,
        withdrawals=withdrawals,
        interest_received=interest,
        dividends_net=dividends,
        capital_gain=capital,
        source_fact_count=len(used_facts),
        missing=missing,
    )


def _sum(rows: list[FactRecord], col: MoneyField) -> float:
    return total((getattr(row, col.value) or 0) for row in rows)
