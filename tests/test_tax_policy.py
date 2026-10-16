from decimal import Decimal

import pytest

from wr.calculations.tax import BOX3_RATE_BY_YEAR, TAX_POLICIES, compare_partner


@pytest.mark.parametrize("year,expected", [
    (2017, "0.30"),
    (2018, "0.30"),
    (2019, "0.30"),
    (2020, "0.30"),
    (2021, "0.31"),
    (2022, "0.31"),
    (2023, "0.32"),
    (2024, "0.36"),
    (2025, "0.36"),
])
def test_policy_rates_and_lookup_preserve_decimal_values(year, expected):
    rate = TAX_POLICIES[year].box3_rate
    assert isinstance(rate, Decimal)
    assert rate == Decimal(expected)
    assert BOX3_RATE_BY_YEAR[year] is rate


def test_decimal_policy_rates_preserve_half_up_cent_rounding():
    result = compare_partner(2024, 125.125, 250.125)

    assert result.estimated_tax_actual == 45.05
    assert result.estimated_tax_savings == 45.0
    assert result.recommendation == "ACTUAL_BETTER"


def test_unknown_tax_year_requires_manual_rSAMw():
    result = compare_partner(2026, 100.0, 200.0)

    assert result.recommendation == "NEEDS_MANUAL_RSAMW"
    assert result.estimated_tax_actual is None
    assert "not supported" in result.notes
