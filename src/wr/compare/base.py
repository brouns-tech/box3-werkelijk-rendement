from __future__ import annotations

from dataclasses import dataclass

from wr.money import multiply, subtract
from wr.models import Recommendation


@dataclass(frozen=True)
class TaxPolicy:
    year: int
    box3_rate: str
    era: str


TAX_POLICIES = {
    year: TaxPolicy(year, rate, "OWR/herstel (2017-2024)")
    for year, rate in {
        2017: "0.30",
        2018: "0.30",
        2019: "0.30",
        2020: "0.30",
        2021: "0.31",
        2022: "0.31",
        2023: "0.32",
        2024: "0.36",
    }.items()
}
TAX_POLICIES[2025] = TaxPolicy(2025, "0.36", "aangifte-era (2025)")
BOX3_RATE_BY_YEAR = {
    year: float(policy.box3_rate) for year, policy in TAX_POLICIES.items()
}


@dataclass
class CompareOutcome:
    recommendation: str
    estimated_tax_actual: float | None
    estimated_tax_savings: float | None
    notes: str


def compare_partner(
    tax_year: int,
    allocated_actual: float | None,
    fictitious: float | None,
    filed_box3_tax: float | None = None,
) -> CompareOutcome:
    """Compare actual and filed return using an explicit 2017-2025 policy."""
    if allocated_actual is None or fictitious is None:
        return CompareOutcome(
            Recommendation.NEEDS_MANUAL_RSAMW.value,
            None,
            None,
            "Missing actual or fictitious return figure",
        )

    policy = TAX_POLICIES.get(tax_year)
    if policy is None:
        return CompareOutcome(
            Recommendation.NEEDS_MANUAL_RSAMW.value,
            None,
            None,
            f"Tax year {tax_year} is not supported; supported years are "
            f"{min(TAX_POLICIES)}-{max(TAX_POLICIES)}",
        )

    # Actual taxable Box 3 income cannot be negative for this simplified model.
    taxable_actual = max(0.0, allocated_actual)
    tax_actual = multiply(taxable_actual, policy.box3_rate)
    tax_fict = (
        filed_box3_tax
        if filed_box3_tax is not None
        else multiply(max(0.0, fictitious), policy.box3_rate)
    )

    if abs(tax_actual - tax_fict) < 0.5:
        rec = Recommendation.EQUAL.value
    elif tax_actual < tax_fict:
        rec = Recommendation.ACTUAL_BETTER.value
    else:
        rec = Recommendation.FICTITIOUS_BETTER.value

    savings = abs(subtract(tax_actual, tax_fict))

    notes = (
        f"{policy.era}: allocated actual {allocated_actual:.2f} vs fictitious {fictitious:.2f}; "
        f"est. tax actual {tax_actual:.2f} vs fictitious {tax_fict:.2f}; "
        f"est. savings from recommended option {savings:.2f}"
    )
    return CompareOutcome(rec, tax_actual, savings, notes)
