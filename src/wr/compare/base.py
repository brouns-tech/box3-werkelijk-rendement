from __future__ import annotations

from dataclasses import dataclass

from wr.models import Recommendation

# Box 3 tax rate on voordeel (simplified). Extend per year as needed.
BOX3_RATE_BY_YEAR = {
    2017: 0.30,
    2018: 0.30,
    2019: 0.30,
    2020: 0.30,
    2021: 0.31,
    2022: 0.31,
    2023: 0.32,
    2024: 0.36,
    2025: 0.36,
}


@dataclass
class CompareOutcome:
    recommendation: str
    estimated_tax_actual: float | None
    notes: str


def compare_partner(
    tax_year: int,
    allocated_actual: float | None,
    fictitious: float | None,
    filed_box3_tax: float | None = None,
) -> CompareOutcome:
    """Year-agnostic comparison shell; OWR (2017-2024) and 2025+ share partner logic."""
    if allocated_actual is None or fictitious is None:
        return CompareOutcome(
            Recommendation.NEEDS_MANUAL_RSAMW.value,
            None,
            "Missing actual or fictitious return figure",
        )

    rate = BOX3_RATE_BY_YEAR.get(tax_year, 0.36)
    # Actual taxable Box 3 income cannot be negative for this simplified model.
    taxable_actual = max(0.0, allocated_actual)
    tax_actual = taxable_actual * rate
    tax_fict = filed_box3_tax if filed_box3_tax is not None else max(0.0, fictitious) * rate

    if abs(tax_actual - tax_fict) < 0.5:
        rec = Recommendation.EQUAL.value
    elif tax_actual < tax_fict:
        rec = Recommendation.ACTUAL_BETTER.value
    else:
        rec = Recommendation.FICTITIOUS_BETTER.value

    era = "OWR/herstel (2017-2024)" if tax_year <= 2024 else "aangifte-era (2025+)"
    notes = (
        f"{era}: allocated actual {allocated_actual:.2f} vs fictitious {fictitious:.2f}; "
        f"est. tax actual {tax_actual:.2f} vs fictitious {tax_fict:.2f}"
    )
    return CompareOutcome(rec, tax_actual, notes)
