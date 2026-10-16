from __future__ import annotations

from wr.calculations.allocation import individual_portfolio
from wr.calculations.tax import BOX3_RATE_BY_YEAR, compare_partner
from wr.identities.matching import resolve_identity, same_person
from wr.models import CoverageStatus, TaxpayerTaxResult, Recommendation
from wr.models.identities import HouseholdSettings, TaxpayerIdentity, TaxpayerPosition
from wr.models.storage import FactValues, PortfolioRecord, TaxReturnRecord
from wr.money import multiply, subtract


def recommendations_for_year(
    year: int,
    portfolio: PortfolioRecord | None,
    returns: list[TaxReturnRecord],
    facts: list[FactValues],
    household: HouseholdSettings,
) -> list[TaxpayerTaxResult]:
    coverage = portfolio.coverage_status if portfolio else CoverageStatus.UNKNOWN.value
    known_actual = portfolio.known_combined_actual_return if portfolio else None
    missing = portfolio.missing_asset_summary if portfolio else "no portfolio"

    if not returns:
        if household.taxpayers:
            return _individual_results(year, returns, facts, household)
        return [
            TaxpayerTaxResult(
                tax_year=year,
                taxpayer_position=TaxpayerPosition.PRIMARY,
                taxpayer_name="unknown",
                allocation_ratio=None,
                allocated_actual_return=known_actual,
                fictitious_return=None,
                estimated_box3_tax_actual=None,
                estimated_box3_tax_fictitious=None,
                estimated_tax_savings=None,
                recommendation=Recommendation.NEEDS_MANUAL_RSAMW.value,
                coverage_status=coverage,
                notes="No tax return parsed for this year",
            )
        ]

    primary = max(
        returns,
        key=lambda r: (
            _submission_rank(r.raw_text_excerpt),
            r.full_year_fiscal_partners or 0,
            1 if r.grondslag else 0,
            1 if r.allocation_a is not None else 0,
            1 if r.filer_name and "unknown" not in (r.filer_name or "").lower() else 0,
            1 if r.filer_name and "datum" not in (r.filer_name or "").lower() else 0,
            1 if _position_for(r.filer_name, household) is TaxpayerPosition.PRIMARY else 0,
            abs(r.grondslag or 0),
        ),
    )

    full_year = bool(primary.full_year_fiscal_partners)
    if not full_year:
        return _individual_results(year, returns, facts, household)

    # Absence of a parsed base is not evidence of a zero base. Keep both
    # partners visible even when allocation or comparison cannot be established.
    zero_base = primary.grondslag == 0
    name_a = primary.partner_a_name
    name_b = primary.partner_b_name
    alloc_a = primary.allocation_a
    alloc_b = primary.allocation_b
    g = primary.grondslag or 0
    if (
        alloc_a is None
        and g
        and primary.grondslag_a is not None
        and primary.grondslag_b is not None
    ):
        alloc_a = abs(primary.grondslag_a) / abs(g)
        alloc_b = abs(primary.grondslag_b) / abs(g)

    fict_a, fict_b = primary.voordeel_a, primary.voordeel_b
    tax_a, tax_b = primary.box3_tax_a, primary.box3_tax_b
    if _position_for(name_b, household) is TaxpayerPosition.PRIMARY and _position_for(name_a, household) is not TaxpayerPosition.PRIMARY:
        name_a, name_b = name_b, name_a
        alloc_a, alloc_b = alloc_b, alloc_a
        fict_a, fict_b = fict_b, fict_a
        tax_a, tax_b = tax_b, tax_a

    incomplete = coverage != CoverageStatus.COMPLETE.value
    results = []
    for position, name, ratio, fict, filed_tax in (
        (TaxpayerPosition.PRIMARY, name_a, alloc_a, fict_a, tax_a),
        (TaxpayerPosition.SECONDARY, name_b, alloc_b, fict_b, tax_b),
    ):
        configured_identity = household.taxpayer(position)
        name = name or (configured_identity.name if configured_identity else None)
        allocated = (
            None if known_actual is None or ratio is None else multiply(known_actual, ratio)
        )
        if zero_base:
            ratio, allocated, fict, filed_tax = None, None, 0.0, 0.0
            rec = Recommendation.NOT_APPLICABLE.value
            notes = "Grondslag sparen en beleggen is zero; actual return cannot reduce Box 3 further"
            tax_actual = 0.0
        elif incomplete:
            rec = Recommendation.INDETERMINATE_MISSING_DATA.value
            notes = f"Partial coverage. Missing: {missing or 'unknown'}"
            tax_actual = None
        elif primary.grondslag is None or ratio is None:
            rec = Recommendation.NEEDS_MANUAL_RSAMW.value
            notes = "Missing combined taxable base or fiscal-partner allocation; review tax-return evidence"
            tax_actual = None
        else:
            cmp = compare_partner(year, allocated, fict, filed_tax)
            rec = cmp.recommendation
            notes = cmp.notes
            tax_actual = cmp.estimated_tax_actual

        rate = BOX3_RATE_BY_YEAR.get(year)
        tax_fict = filed_tax
        if tax_fict is None and fict is not None and rate is not None:
            tax_fict = multiply(fict, rate)

        matched_identity = resolve_identity(name, household)
        results.append(
            TaxpayerTaxResult(
                tax_year=year,
                taxpayer_position=position,
                taxpayer_name=(matched_identity.name if matched_identity else name) or position.value,
                allocation_ratio=ratio,
                allocated_actual_return=allocated,
                fictitious_return=fict,
                estimated_box3_tax_actual=tax_actual,
                estimated_box3_tax_fictitious=tax_fict,
                estimated_tax_savings=(
                    subtract(tax_fict, tax_actual)
                    if tax_fict is not None and tax_actual is not None
                    else None
                ),
                recommendation=rec,
                coverage_status=coverage,
                notes=notes,
            )
        )
    return results


def _submission_rank(excerpt: str | None) -> int:
    text = (excerpt or "").lower()
    if "verzonden: aangifte inkomstenbelasting" in text:
        return 2
    if "nog niet verstuurd" in text:
        return 0
    return 1


def _individual_results(
    year: int, returns: list[TaxReturnRecord], facts: list[FactValues], household: HouseholdSettings
) -> list[TaxpayerTaxResult]:
    configured = [(identity.position, identity.name) for identity in household.taxpayers]
    if not configured:
        configured = [(position, row.filer_name) for position, row in zip(TaxpayerPosition, returns)]
    results = []
    for position, name in configured:
        matching = [row for row in returns if (
            _position_for(row.filer_name, household) == position
            if household.taxpayers
            else same_person(row.filer_name, name)
        )]
        tax_return = max(matching, key=lambda row: _submission_rank(row.raw_text_excerpt)) if matching else None
        known_actual, coverage, missing = individual_portfolio(facts, year, name, household)
        if tax_return is None:
            results.append(TaxpayerTaxResult(
                tax_year=year, taxpayer_position=position, taxpayer_name=name or position.value, allocation_ratio=1.0,
                allocated_actual_return=known_actual, fictitious_return=None,
                estimated_box3_tax_actual=None, estimated_box3_tax_fictitious=None,
                estimated_tax_savings=None, recommendation=Recommendation.NEEDS_MANUAL_RSAMW.value,
                coverage_status=coverage, notes="No tax return parsed for this filer",
            ))
            continue
        fictitious, filed_tax = tax_return.voordeel_a, tax_return.box3_tax_a
        if coverage != CoverageStatus.COMPLETE.value:
            recommendation, estimated_actual_tax = Recommendation.INDETERMINATE_MISSING_DATA.value, None
            notes = f"Partial coverage. Missing: {missing or 'unknown'}"
        else:
            comparison = compare_partner(year, known_actual, fictitious, filed_tax)
            recommendation, estimated_actual_tax, notes = comparison.recommendation, comparison.estimated_tax_actual, comparison.notes
        tax_fictitious = filed_tax or (
            multiply(fictitious, BOX3_RATE_BY_YEAR[year])
            if fictitious is not None and year in BOX3_RATE_BY_YEAR
            else None
        )
        results.append(TaxpayerTaxResult(
            tax_year=year, taxpayer_position=position, taxpayer_name=name or tax_return.filer_name or position.value,
            allocation_ratio=1.0, allocated_actual_return=known_actual, fictitious_return=fictitious,
            estimated_box3_tax_actual=estimated_actual_tax, estimated_box3_tax_fictitious=tax_fictitious,
            estimated_tax_savings=(subtract(tax_fictitious, estimated_actual_tax) if tax_fictitious is not None and estimated_actual_tax is not None else None),
            recommendation=recommendation, coverage_status=coverage, notes=notes,
        ))
    return results


def _position_for(name: str | None, household: HouseholdSettings) -> TaxpayerPosition | None:
    identity = resolve_identity(name, household)
    return identity.position if isinstance(identity, TaxpayerIdentity) else None
