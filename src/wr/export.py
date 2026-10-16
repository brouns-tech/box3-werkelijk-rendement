from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable
import csv
import io
import json
import sqlite3
import zipfile

from wr.calculations.returns import native_fact_return, has_actual_return, fact_return
from wr.importing.reprocessing import pending_reprocessing
from wr.models.audit import (
    AssetExportRow,
    AuditManifest,
    TaxpayerTaxExportRow,
    SourceFactExportRow,
    YearSummary,
)
from wr.models.base import Record
from wr.models.storage import FactValues, MoneyField
from wr.money import Currency
from wr.storage.connection import connect
from wr.storage.reconciliation import reconciled_facts, source_observations
from wr.storage.migrations import init_db
from wr.storage.portfolio import portfolio_for_year
from wr.storage.tax_returns import primary_return


def create_audit_export(
        conn: sqlite3.Connection, years: Iterable[int] | None = None
) -> bytes:
    """Create a portable audit bundle from the calculated database state."""
    selected_years = _selected_years(conn, years)
    yearly_rows = [_year_summary(conn, year) for year in selected_years]
    asset_rows: list[AssetExportRow] = []
    fact_rows: list[SourceFactExportRow] = []
    tax_rows: list[TaxpayerTaxExportRow] = []

    for year in selected_years:
        assets, facts = _asset_and_fact_rows(conn, year)
        asset_rows.extend(assets)
        fact_rows.extend(facts)
        tax_rows.extend(
            TaxpayerTaxExportRow.model_validate(dict(row))
            for row in conn.execute(
                """
                SELECT tax_year,
                       taxpayer_position,
                       taxpayer_name,
                       allocation_ratio,
                       allocated_actual_return,
                       fictitious_return,
                       estimated_box3_tax_actual,
                       estimated_box3_tax_fictitious,
                       estimated_tax_savings,
                       recommendation,
                       coverage_status,
                       notes
                FROM taxpayer_tax_results
                WHERE tax_year = ?
                ORDER BY taxpayer_position
                """,
                (year,),
            )
        )

    manifest = AuditManifest(
        pending_pdf_reprocessing= pending_reprocessing(conn),
        document_processing_profiles= [
            row[0] or "legacy-unknown"
            for row in conn.execute("SELECT DISTINCT processing_profile FROM documents ORDER BY processing_profile")
        ],
        generated_at_utc= datetime.now(timezone.utc).isoformat(),
        tax_years= selected_years,
        files= {
            "yearly_summary.csv": "Portfolio totals and filed Box 3 comparison by year.",
            "assets.csv": (
                "Reconciled account-year assets with source-derived balances, flows, return components, "
                "coverage, and the return included in the yearly result."
            ),
            "source_facts.csv": (
                "Unmodified document observations; these are evidence, not additive portfolio rows."
            ),
            "reconciled_facts.json": "Derived account-year facts with field-level sources, conflicts, and derivation rules.",
            "taxpayer_tax_results.csv": "Per-taxpayer tax estimates and recommendation.",
        },
        calculation_notes= [
            "actual_return follows the same gain-method rules as the portfolio calculation.",
            "Net interest is interest_received minus interest_paid.",
            "Gross dividends are part of actual return; withholding tax is exported separately.",
            "Net dividends are dividends_gross minus withholding_tax and are shown for cash reconciliation.",
            "The tax comparison does not estimate credits or refunds for withholding tax.",
            "Assets are reconciled account-year results; source observations are never added directly to totals.",
            "reconciled_facts.json records field-level support, disagreement, and derivation rules.",
            "Agreement between different PDFs is not a claim that their evidence is independent.",
            "Conflicted assets contribute no return and keep coverage incomplete.",
            "Declared balances and parsed source balances are exported separately; they may differ.",
        ],
    )

    output = io.BytesIO()
    observations_by_id: dict[int, SourceFactExportRow] = {}
    for row in fact_rows:
        previous = observations_by_id.get(row.fact_id)
        if previous:
            row.matched_asset_ids = ";".join(sorted(set(
                previous.matched_asset_ids.split(";") + row.matched_asset_ids.split(";")
            ) - {""}))
        observations_by_id[row.fact_id] = row
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        bundle.writestr("manifest.json", manifest.model_dump_json(indent=2))
        _write_csv(bundle, "yearly_summary.csv", yearly_rows)
        _write_csv(bundle, "assets.csv", asset_rows)
        _write_csv(bundle, "source_facts.csv", observations_by_id.values())
        bundle.writestr("reconciled_facts.json", json.dumps([
            fact.model_dump(mode="json") for year in selected_years for fact in reconciled_facts(conn, year)
        ], ensure_ascii=False, indent=2))
        _write_csv(bundle, "taxpayer_tax_results.csv", tax_rows)
    return output.getvalue()


def write_audit_export(
        db_path: str | Path,
        output_path: str | Path,
        years: Iterable[int] | None = None,
) -> Path:
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with connect(db_path) as conn:
        init_db(conn)
        payload = create_audit_export(conn, years)
    destination.write_bytes(payload)
    return destination


def _selected_years(
        conn: sqlite3.Connection, years: Iterable[int] | None
) -> list[int]:
    if years is not None:
        return sorted(set(years))
    rows = conn.execute(
        """
        SELECT tax_year
        FROM yearly_portfolio
        UNION
        SELECT tax_year
        FROM account_year_facts
        UNION
        SELECT tax_year
        FROM taxpayer_tax_results
        ORDER BY tax_year
        """
    ).fetchall()
    return [int(row[0]) for row in rows if row[0] is not None]


def _year_summary(conn: sqlite3.Connection, year: int) -> YearSummary:
    portfolio = portfolio_for_year(conn, year)
    tax_return = primary_return(conn, year)
    savings = conn.execute(
        """
        SELECT SUM(estimated_tax_savings)
        FROM taxpayer_tax_results
        WHERE tax_year = ?
        """,
        (year,),
    ).fetchone()[0]

    return YearSummary(
        tax_year=year,
        coverage_status=portfolio.coverage_status if portfolio is not None else None,
        start_capital_from_sources=portfolio.start_balance if portfolio is not None else None,
        end_capital_from_sources=portfolio.end_balance if portfolio is not None else None,
        deposits=portfolio.deposits if portfolio is not None else None,
        withdrawals=portfolio.withdrawals if portfolio is not None else None,
        net_interest=portfolio.interest_received if portfolio is not None else None,
        dividends_gross=portfolio.dividends_gross if portfolio is not None else None,
        withholding_tax=portfolio.withholding_tax if portfolio is not None else None,
        net_dividends=portfolio.dividends_net if portfolio is not None else None,
        market_value_change=portfolio.capital_gain if portfolio is not None else None,
        actual_return_used=portfolio.known_combined_actual_return if portfolio is not None else None,
        source_fact_count=portfolio.source_fact_count if portfolio is not None else None,
        missing_asset_summary=portfolio.missing_asset_summary if portfolio is not None else None,
        declared_assets_0101=tax_return.bezittingen_0101 if tax_return is not None else None,
        declared_assets_3112=tax_return.bezittingen_3112 if tax_return is not None else None,
        declared_debts_0101=tax_return.schulden_0101 if tax_return is not None else None,
        declared_debts_3112=tax_return.schulden_3112 if tax_return is not None else None,
        taxable_base=tax_return.grondslag if tax_return is not None else None,
        estimated_household_tax_savings=savings,
    )


def _asset_and_fact_rows(
        conn: sqlite3.Connection, year: int
) -> tuple[list[AssetExportRow], list[SourceFactExportRow]]:
    facts = reconciled_facts(conn, year)
    observations = source_observations(conn)
    sources_by_id = {row.id: row for row in observations}
    contributing_ids = {identifier for fact in facts for identifier in fact.source_fact_ids}
    included_fact_ids = {fact.id for fact in facts if fact.extra.box3}
    asset_rows: list[AssetExportRow] = []

    for fact in facts:
        fact_id = int(fact.id)
        if fact_id not in included_fact_ids:
            continue
        actual_return = fact_return(fact)
        asset_rows.append(
            AssetExportRow(
                tax_year=year,
                asset_id=f"reconciled-{fact_id}",
                category="reconciled account-year fact",
                institution=fact.issuer,
                account_id=fact.account_key,
                label=fact.account_label,
                coverage_status="COMPLETE" if has_actual_return(fact) else "PARTIAL",
                declared_start_capital=None,
                declared_end_capital=None,
                source_start_capital=fact.start_balance,
                source_end_capital=fact.end_balance,
                deposits=fact.deposits,
                withdrawals=fact.withdrawals,
                interest_received=fact.interest_received,
                interest_paid=fact.interest_paid,
                net_interest=_optional_net(
                    [fact], MoneyField.INTEREST_RECEIVED, MoneyField.INTEREST_PAID
                ),
                dividends_gross=fact.dividends_gross,
                withholding_tax=fact.withholding_tax,
                net_dividends=_optional_net(
                    [fact], MoneyField.DIVIDENDS_GROSS, MoneyField.WITHHOLDING_TAX
                ),
                market_value_change=fact.capital_gain,
                actual_return_from_sources=actual_return,
                return_used=actual_return or 0.0,
                currency=fact.currency,
                native_actual_return=native_fact_return(fact),
                return_basis="reconciled account-year fact" if (fact.currency or Currency.EUR) == Currency.EUR else "requires EUR conversion; native amounts retained",
                matched_fact_ids=";".join(map(str, fact.source_fact_ids)),
                included_fact_ids=";".join(map(str, fact.source_fact_ids)) if actual_return is not None else "",
                source_document_sha256s=";".join(sorted({sources_by_id[identifier].document_sha256 for identifier in fact.source_fact_ids})),
                source_paths=";".join(sorted({sources_by_id[identifier].first_seen_path for identifier in fact.source_fact_ids if sources_by_id[identifier].first_seen_path})),
            )
        )

    fact_rows = []
    for fact in observations:
        if fact.tax_year != year and fact.id not in contributing_ids:
            continue
        fact_id = int(fact.id)
        excluded = not fact.extra.box3
        included = False
        fact_rows.append(
            SourceFactExportRow(
                tax_year=fact.tax_year,
                fact_id=fact_id,
                issuer=fact.issuer,
                account_key=fact.account_key,
                account_label=fact.account_label,
                holder_names=json.dumps(fact.holder_names),
                ownership=fact.ownership,
                currency=fact.currency,
                start_capital=fact.start_balance,
                end_capital=fact.end_balance,
                deposits=fact.deposits,
                withdrawals=fact.withdrawals,
                interest_received=fact.interest_received,
                interest_paid=fact.interest_paid,
                dividends_gross=fact.dividends_gross,
                withholding_tax=fact.withholding_tax,
                capital_gain=fact.capital_gain,
                gain_method=fact.gain_method,
                calculated_actual_return=fact_return(fact),
                native_actual_return=native_fact_return(fact),
                has_usable_actual_return=has_actual_return(fact),
                matched_asset_ids=";".join(
                    f"reconciled-{result.id}" for result in facts
                    if result.extra.box3 and fact.id in result.source_fact_ids
                ),
                primary_asset_id=None,
                included_in_year_total=included,
                exclusion_reason=(
                    "excluded from Box 3" if excluded else ("requires EUR conversion" if (fact.currency or Currency.EUR) != Currency.EUR else "source observation; totals use reconciled facts")
                )
                if not included
                else None,
                document_sha256=fact.document_sha256,
                source_path=fact.first_seen_path,
                processing_profile=fact.processing_profile,
                document_type=fact.doc_type,
                parse_status=fact.parse_status,
                extra=fact.extra.model_dump_json(exclude_unset=True),
            )
        )
    return asset_rows, fact_rows


def _write_csv(
        bundle: zipfile.ZipFile, name: str, rows: Iterable[Record]
) -> None:
    buffer = io.StringIO(newline="")
    serialized = [row.model_dump(mode="json", exclude_unset=True) for row in rows]
    fieldnames = list(serialized[0]) if serialized else ["no_rows"]
    writer = csv.DictWriter(buffer, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(serialized)
    bundle.writestr(name, "\ufeff" + buffer.getvalue())


def _optional_sum(rows: Iterable[FactValues], key: MoneyField) -> float | None:
    values = [getattr(row, key.value) for row in rows if getattr(row, key.value) is not None]
    return float(sum(values)) if values else None


def _optional_net(
        rows: Iterable[FactValues], positive_key: MoneyField, negative_key: MoneyField
) -> float | None:
    rows = list(rows)
    positive = _optional_sum(rows, positive_key)
    negative = _optional_sum(rows, negative_key)
    if positive is None and negative is None:
        return None
    return (positive or 0.0) - (negative or 0.0)
