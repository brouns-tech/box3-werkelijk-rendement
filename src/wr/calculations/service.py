from __future__ import annotations

from pathlib import Path
import sqlite3

from wr.calculations.coverage import coverage_for_year
from wr.calculations.recommendations import recommendations_for_year
from wr.identities.service import effective_household
from wr.importing.canonicalization import canonicalize_facts
from wr.models.settings import HouseholdSettings
from wr.models.tax import TaxpayerTaxResult
from wr.parsers.base import InstitutionOptions
from wr.storage.connection import connect
from wr.storage.facts import canonical_facts, canonical_years, clear_canonical_flags
from wr.storage.migrations import init_db
from wr.storage.portfolio import portfolio_for_year, save_coverage
from wr.storage.recommendations import clear_recommendations, comparison_years, save_recommendation
from wr.storage.tax_returns import returns_for_year


def rebuild_portfolio(conn: sqlite3.Connection) -> None:
    for year in sorted(canonical_years(conn)):
        save_coverage(conn, coverage_for_year(year, canonical_facts(conn, year)))
    conn.commit()


def rebuild_recommendations(conn: sqlite3.Connection, household: HouseholdSettings | None = None) -> None:
    clear_recommendations(conn)
    household = effective_household(conn, household)
    for year in sorted(comparison_years(conn)):
        results = results_for_year(conn, year, household)
        for result in results:
            save_recommendation(conn, result)
    conn.commit()


def recompute(
    db_path: str | Path,
    *,
    household_config: HouseholdSettings | None = None,
    institution_options: InstitutionOptions | None = None,
) -> None:
    conn = connect(db_path)
    try:
        init_db(conn)
        clear_canonical_flags(conn)
        canonicalize_facts(conn, institution_options)
        rebuild_portfolio(conn)
        rebuild_recommendations(conn, household_config)
    finally:
        conn.close()


def results_for_year(conn: sqlite3.Connection, year: int, household: HouseholdSettings) -> list[TaxpayerTaxResult]:
    return recommendations_for_year(
        year, portfolio_for_year(conn, year), returns_for_year(conn, year),
        canonical_facts(conn, year), household,
    )
