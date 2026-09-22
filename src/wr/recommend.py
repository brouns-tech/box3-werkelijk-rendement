from __future__ import annotations

import json
import re
import sqlite3

from wr.compare.base import BOX3_RATE_BY_YEAR, compare_partner
from wr.config import PartnerSettings
from wr.money import add, multiply, subtract
from wr.models import CoverageStatus, PartnerTaxResult, Recommendation
from wr.portfolio import _fact_return, is_box3_fact


def rebuild_recommendations(
    conn: sqlite3.Connection, partner_cfg: PartnerSettings | None = None
) -> None:
    conn.execute("DELETE FROM partner_tax_results")
    years = {
        r[0] for r in conn.execute("SELECT DISTINCT tax_year FROM tax_returns").fetchall()
    }
    years |= {
        r[0] for r in conn.execute("SELECT DISTINCT tax_year FROM yearly_portfolio").fetchall()
    }

    partner_cfg = partner_cfg or PartnerSettings()

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
    conn: sqlite3.Connection, year: int, partner_cfg: PartnerSettings
) -> list[PartnerTaxResult]:
    portfolio = conn.execute(
        "SELECT * FROM yearly_portfolio WHERE tax_year = ?", (year,)
    ).fetchone()
    returns = conn.execute(
        """
        SELECT t.*, d.raw_text_excerpt
        FROM tax_returns t
        JOIN documents d ON d.content_sha256 = t.document_sha256
        WHERE t.tax_year = ?
        ORDER BY t.id
        """,
        (year,),
    ).fetchall()

    coverage = portfolio["coverage_status"] if portfolio else CoverageStatus.UNKNOWN.value
    known_actual = portfolio["known_combined_actual_return"] if portfolio else None
    missing = portfolio["missing_asset_summary"] if portfolio else "no portfolio"
    preferred_a = partner_cfg.partner_a or "partner_a"

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
            _submission_rank(r["raw_text_excerpt"]),
            r["full_year_fiscal_partners"] or 0,
            1 if r["grondslag"] else 0,
            1 if r["allocation_a"] is not None else 0,
            1 if r["filer_name"] and "unknown" not in (r["filer_name"] or "").lower() else 0,
            1 if r["filer_name"] and "datum" not in (r["filer_name"] or "").lower() else 0,
            1 if _same_person(r["filer_name"], preferred_a) else 0,
            abs(r["grondslag"] or 0),
        ),
    )

    full_year = bool(primary["full_year_fiscal_partners"])
    if not full_year:
        return _individual_results(conn, year, returns, partner_cfg)

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

    incomplete = coverage != CoverageStatus.COMPLETE.value
    results = []
    for slot, name, ratio, fict, filed_tax in (
        ("a", name_a, alloc_a, primary["voordeel_a"], primary["box3_tax_a"]),
        ("b", name_b, alloc_b, primary["voordeel_b"], primary["box3_tax_b"]),
    ):
        allocated = (
            None if known_actual is None or ratio is None else multiply(known_actual, ratio)
        )
        if incomplete:
            rec = Recommendation.INDETERMINATE_MISSING_DATA.value
            notes = f"Partial coverage. Missing: {missing or 'unknown'}"
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


def _same_person(a: str | None, b: str | None) -> bool:
    if not a or not b:
        return False
    al = re.sub(r"[^a-z]", "", a.lower())
    bl = re.sub(r"[^a-z]", "", b.lower())
    return al in bl or bl in al


def _individual_results(
    conn, year: int, returns, partner_cfg: PartnerSettings
) -> list[PartnerTaxResult]:
    configured = [
        (slot, name) for slot, name in partner_cfg.configured() if name is not None
    ]
    if not configured:
        configured = [(chr(ord("a") + index), row["filer_name"]) for index, row in enumerate(returns)]
    results = []
    for slot, name in configured:
        matching = [row for row in returns if _same_person(row["filer_name"], name)]
        tax_return = max(matching, key=lambda row: _submission_rank(row["raw_text_excerpt"])) if matching else None
        known_actual, coverage, missing = _individual_portfolio(conn, year, name, partner_cfg)
        if tax_return is None:
            results.append(PartnerTaxResult(
                tax_year=year, partner=slot, partner_name=name or slot, allocation_ratio=1.0,
                allocated_actual_return=known_actual, fictitious_return=None,
                estimated_box3_tax_actual=None, estimated_box3_tax_fictitious=None,
                estimated_tax_savings=None, recommendation=Recommendation.NEEDS_MANUAL_RSAMW.value,
                coverage_status=coverage, notes="No tax return parsed for this filer",
            ))
            continue
        fictitious, filed_tax = tax_return["voordeel_a"], tax_return["box3_tax_a"]
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
        results.append(PartnerTaxResult(
            tax_year=year, partner=slot, partner_name=name or tax_return["filer_name"] or slot,
            allocation_ratio=1.0, allocated_actual_return=known_actual, fictitious_return=fictitious,
            estimated_box3_tax_actual=estimated_actual_tax, estimated_box3_tax_fictitious=tax_fictitious,
            estimated_tax_savings=(subtract(tax_fictitious, estimated_actual_tax) if tax_fictitious is not None and estimated_actual_tax is not None else None),
            recommendation=recommendation, coverage_status=coverage, notes=notes,
        ))
    return results


def _individual_portfolio(
    conn: sqlite3.Connection,
    year: int,
    filer_name: str | None,
    partner_cfg: PartnerSettings,
) -> tuple[float | None, str, str | None]:
    aliases = _aliases_for_filer(filer_name, partner_cfg)
    facts = conn.execute(
        "SELECT * FROM account_year_facts WHERE tax_year = ? AND is_canonical = 1", (year,)
    ).fetchall()
    total = 0.0
    used = 0
    missing: list[str] = []
    for fact in facts:
        if not is_box3_fact(fact):
            continue
        holders = json.loads(fact["holder_names"] or "[]")
        matches = [_matches_alias(holder, aliases) for holder in holders]
        if len(holders) == 1 and matches[0]:
            portion = 1.0
        elif fact["ownership"] == "joint" and len(holders) >= 2:
            portion = 0.5
        elif not holders:
            missing.append(f"{fact['issuer']} {fact['account_key']} (holder unknown)")
            continue
        else:
            continue
        value = _fact_return(fact)
        if value is None:
            missing.append(f"{fact['issuer']} {fact['account_key']} (no actual-return fields)")
            continue
        total = add(total, multiply(value, portion))
        used += 1
    if not used:
        missing.append("no statement-derived assets assigned to this filer")
    return (
        total if used else None,
        CoverageStatus.PARTIAL.value if missing else CoverageStatus.COMPLETE.value,
        "; ".join(missing) if missing else None,
    )


def _aliases_for_filer(
    filer_name: str | None, partner_cfg: PartnerSettings
) -> list[str]:
    aliases = [filer_name or ""]
    for slot, configured in partner_cfg.configured():
        if _same_person(filer_name, configured):
            aliases.extend([configured or "", *partner_cfg.aliases_for(slot)])
    return aliases


def _matches_alias(name: str, aliases: list[str]) -> bool:
    normalized = re.sub(r"[^a-z]", "", name.lower())
    return any(
        alias and re.sub(r"[^a-z]", "", alias.lower()) in normalized
        for alias in aliases
    )
