from __future__ import annotations

import sqlite3

from wr.compare.base import BOX3_RATE_BY_YEAR, compare_partner
from wr.config import load_config
from wr.models import CoverageStatus, PartnerTaxResult, Recommendation


def rebuild_recommendations(conn: sqlite3.Connection) -> None:
    conn.execute("DELETE FROM partner_tax_results")
    years = {
        r[0] for r in conn.execute("SELECT DISTINCT tax_year FROM tax_returns").fetchall()
    }
    years |= {
        r[0] for r in conn.execute("SELECT DISTINCT tax_year FROM yearly_portfolio").fetchall()
    }

    try:
        cfg = load_config()
        partner_cfg = cfg.get("partners", {})
    except FileNotFoundError:
        partner_cfg = {}

    for year in sorted(y for y in years if y):
        for result in _results_for_year(conn, year, partner_cfg):
            conn.execute(
                """
                INSERT INTO partner_tax_results (
                    tax_year, partner, partner_name, allocation_ratio,
                    allocated_actual_return, fictitious_return,
                    estimated_box3_tax_actual, estimated_box3_tax_fictitious,
                    estimated_tax_savings, recommendation, coverage_status, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    result.tax_year,
                    result.partner,
                    result.partner_name,
                    result.allocation_ratio,
                    result.allocated_actual_return,
                    result.fictitious_return,
                    result.estimated_box3_tax_actual,
                    result.estimated_box3_tax_fictitious,
                    result.estimated_tax_savings,
                    result.recommendation,
                    result.coverage_status,
                    result.notes,
                ),
            )
    conn.commit()


def _results_for_year(
    conn: sqlite3.Connection, year: int, partner_cfg: dict
) -> list[PartnerTaxResult]:
    portfolio = conn.execute(
        "SELECT * FROM yearly_portfolio WHERE tax_year = ?", (year,)
    ).fetchone()
    returns = conn.execute(
        "SELECT * FROM tax_returns WHERE tax_year = ? ORDER BY id", (year,)
    ).fetchall()

    coverage = portfolio["coverage_status"] if portfolio else CoverageStatus.UNKNOWN.value
    known_actual = portfolio["known_combined_actual_return"] if portfolio else None
    missing = portfolio["missing_asset_summary"] if portfolio else "no portfolio"
    preferred_a = partner_cfg.get("partner_a", "EXAMPLE")

    if not returns:
        return [
            PartnerTaxResult(
                tax_year=year,
                partner="a",
                partner_name="unknown",
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
            r["full_year_fiscal_partners"] or 0,
            1 if r["grondslag"] else 0,
            1 if r["allocation_a"] is not None else 0,
            1 if r["filer_name"] and "unknown" not in (r["filer_name"] or "").lower() else 0,
            1 if r["filer_name"] and "datum" not in (r["filer_name"] or "").lower() else 0,
            1 if _same_person(r["filer_name"], preferred_a) else 0,
            abs(r["grondslag"] or 0),
        ),
    )

    voordeel_by_name: dict[str, float] = {}
    tax_by_name: dict[str, float] = {}
    # Read the selected primary return first and use other copies only to fill
    # missing partner values. This prevents an older/draft duplicate from
    # silently overwriting the chosen return.
    ordered_returns = [primary, *(r for r in returns if r["id"] != primary["id"])]
    for r in ordered_returns:
        name = r["partner_a_name"] or r["filer_name"] or ""
        if r["voordeel_a"] is not None:
            voordeel_by_name.setdefault(name, r["voordeel_a"])
        if r["box3_tax_a"] is not None:
            tax_by_name.setdefault(name, r["box3_tax_a"])
        name_b = r["partner_b_name"] or ""
        if name_b and r["voordeel_b"] is not None:
            voordeel_by_name.setdefault(name_b, r["voordeel_b"])
        if name_b and r["box3_tax_b"] is not None:
            tax_by_name.setdefault(name_b, r["box3_tax_b"])

    full_year = bool(primary["full_year_fiscal_partners"])
    if not full_year:
        return [
            PartnerTaxResult(
                tax_year=year,
                partner="a",
                partner_name=primary["filer_name"] or "filer",
                allocation_ratio=1.0,
                allocated_actual_return=known_actual,
                fictitious_return=primary["voordeel_a"],
                estimated_box3_tax_actual=None,
                estimated_box3_tax_fictitious=primary["box3_tax_a"],
                estimated_tax_savings=None,
                recommendation=Recommendation.NEEDS_MANUAL_RSAMW.value,
                coverage_status=coverage,
                notes="Not detected as full-year fiscal partners; manual rSAMw required",
            )
        ]

    if primary["allocation_status"] == "ZERO_BASE" or (primary["grondslag"] or 0) == 0:
        return [
            PartnerTaxResult(
                tax_year=year,
                partner="a",
                partner_name=primary["partner_a_name"] or "a",
                allocation_ratio=None,
                allocated_actual_return=known_actual,
                fictitious_return=0.0,
                estimated_box3_tax_actual=0.0,
                estimated_box3_tax_fictitious=0.0,
                estimated_tax_savings=0.0,
                recommendation=Recommendation.NOT_APPLICABLE.value,
                coverage_status=coverage,
                notes="Grondslag sparen en beleggen is zero; actual return cannot reduce Box 3 further",
            )
        ]

    name_a = primary["partner_a_name"]
    name_b = primary["partner_b_name"]
    alloc_a = primary["allocation_a"]
    alloc_b = primary["allocation_b"]
    g = primary["grondslag"] or 0
    if (
        alloc_a is None
        and g
        and primary["grondslag_a"] is not None
        and primary["grondslag_b"] is not None
    ):
        alloc_a = abs(primary["grondslag_a"]) / abs(g)
        alloc_b = abs(primary["grondslag_b"]) / abs(g)

    if name_a and not _same_person(name_a, preferred_a) and _same_person(name_b, preferred_a):
        name_a, name_b = name_b, name_a
        alloc_a, alloc_b = alloc_b, alloc_a

    def lookup_voordeel(person: str | None) -> float | None:
        if not person:
            return None
        for n, v in voordeel_by_name.items():
            if _same_person(n, person):
                return v
        return None

    def lookup_tax(person: str | None) -> float | None:
        if not person:
            return None
        for n, v in tax_by_name.items():
            if _same_person(n, person):
                return v
        return None

    results = []
    for slot, name, ratio in (("a", name_a, alloc_a), ("b", name_b, alloc_b)):
        fict = lookup_voordeel(name)
        filed_tax = lookup_tax(name)
        allocated = None if known_actual is None or ratio is None else known_actual * ratio
        if coverage == CoverageStatus.UNKNOWN.value:
            rec = Recommendation.INDETERMINATE_MISSING_DATA.value
            notes = f"Unknown coverage. Missing: {missing or 'unknown'}"
            tax_actual = None
            tax_savings = None
        else:
            cmp = compare_partner(year, allocated, fict, filed_tax)
            rec = cmp.recommendation
            notes = cmp.notes
            tax_actual = cmp.estimated_tax_actual
            tax_savings = cmp.estimated_tax_savings
            if coverage == CoverageStatus.PARTIAL.value:
                notes += (
                    "; WARNING: assumed 0% return for missing assets. "
                    f"Missing: {missing or 'unknown'}"
                )

        rate = BOX3_RATE_BY_YEAR.get(year)
        tax_fict = filed_tax
        if tax_fict is None and fict is not None and rate is not None:
            tax_fict = fict * rate

        results.append(
            PartnerTaxResult(
                tax_year=year,
                partner=slot,
                partner_name=name or slot,
                allocation_ratio=ratio,
                allocated_actual_return=allocated,
                fictitious_return=fict,
                estimated_box3_tax_actual=tax_actual,
                estimated_box3_tax_fictitious=tax_fict,
                estimated_tax_savings=tax_savings,
                recommendation=rec,
                coverage_status=coverage,
                notes=notes,
            )
        )
    return results


def _same_person(a: str | None, b: str | None) -> bool:
    if not a or not b:
        return False
    al, bl = a.lower(), b.lower()
    return (
        ("EXAMPLE" in al and "EXAMPLE" in bl)
        or ("EXAMPLE" in al and "EXAMPLE" in bl)
        or al in bl
        or bl in al
    )
