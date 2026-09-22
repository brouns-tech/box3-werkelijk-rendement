from wr.compare.base import compare_partner


def test_unknown_tax_year_requires_manual_rSAMw():
    result = compare_partner(2026, 100.0, 200.0)

    assert result.recommendation == "NEEDS_MANUAL_RSAMW"
    assert result.estimated_tax_actual is None
    assert "not supported" in result.notes
