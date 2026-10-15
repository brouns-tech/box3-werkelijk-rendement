from __future__ import annotations

import csv
import io
import json
import sqlite3
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from wr.records import FactRecord, MoneyField, PortfolioRecord, Record, TaxReturnRecord
from wr.export_models import AssetExportRow, AuditManifest, PartnerTaxExportRow, SourceFactExportRow, YearSummary

from wr.db import connect, init_db
from wr.portfolio import _native_fact_return, _fact_has_actual_return, _fact_return, _is_excluded_box3_fact
from wr.import_pipeline import pending_reprocessing


def create_audit_export(
        conn: sqlite3.Connection, years: Iterable[int] | None = None
) -> bytes:
    """Create a portable audit bundle from the calculated database state."""
    selected_years = _selected_years(conn, years)
    yearly_rows = [_year_summary(conn, year) for year in selected_years]
    asset_rows: list[AssetExportRow] = []
    fact_rows: list[SourceFactExportRow] = []
    tax_rows: list[PartnerTaxExportRow] = []

    for year in selected_years:
        assets, facts = _asset_and_fact_rows(conn, year)
        asset_rows.extend(assets)
        fact_rows.extend(facts)
        tax_rows.extend(
            PartnerTaxExportRow.model_validate(dict(row))
            for row in conn.execute(
                """
                SELECT tax_year,
                       partner,
                       partner_name,
                       allocation_ratio,
                       allocated_actual_return,
                       fictitious_return,
                       estimated_box3_tax_actual,
                       estimated_box3_tax_fictitious,
                       estimated_tax_savings,
                       recommendation,
                       coverage_status,
                       notes
                FROM partner_tax_results
                WHERE tax_year = ?
                ORDER BY partner
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
                "Declared assets with source-derived balances, flows, return components, "
                "coverage, and the return included in the yearly result."
            ),
            "source_facts.csv": (
                "Canonical parsed account facts with source PDF identity and asset attribution."
            ),
            "partner_tax_results.csv": "Per-partner tax estimates and recommendation.",
        },
        calculation_notes= [
            "actual_return follows the same gain-method rules as the portfolio calculation.",
            "Net interest is interest_received minus interest_paid.",
            "Gross dividends are part of actual return; withholding tax is exported separately.",
            "Net dividends are dividends_gross minus withholding_tax and are shown for cash reconciliation.",
            "The tax comparison does not estimate credits or refunds for withholding tax.",
            "A source fact matched to multiple declared assets is included once, under the first asset id.",
            "Missing or partial assets contribute 0.00 to return_used and remain visibly warned.",
            "Declared balances and parsed source balances are exported separately; they may differ.",
        ],
    )

    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        bundle.writestr("manifest.json", manifest.model_dump_json(indent=2))
        _write_csv(bundle, "yearly_summary.csv", yearly_rows)
        _write_csv(bundle, "assets.csv", asset_rows)
        _write_csv(bundle, "source_facts.csv", fact_rows)
        _write_csv(bundle, "partner_tax_results.csv", tax_rows)
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
        FROM partner_tax_results
        ORDER BY tax_year
        """
    ).fetchall()
    return [int(row[0]) for row in rows if row[0] is not None]


def _year_summary(conn: sqlite3.Connection, year: int) -> YearSummary:
    portfolio = conn.execute(
        "SELECT * FROM yearly_portfolio WHERE tax_year = ?", (year,)
    ).fetchone()
    tax_return = conn.execute(
        """
        SELECT *
        FROM tax_returns
        WHERE tax_year = ?
        ORDER BY full_year_fiscal_partners DESC, grondslag DESC LIMIT 1
        """,
        (year,),
    ).fetchone()
    savings = conn.execute(
        """
        SELECT SUM(estimated_tax_savings)
        FROM partner_tax_results
        WHERE tax_year = ?
        """,
        (year,),
    ).fetchone()[0]

    portfolio = PortfolioRecord.model_validate(dict(portfolio)) if portfolio is not None else None
    tax_return = TaxReturnRecord.model_validate(dict(tax_return)) if tax_return is not None else None
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
    facts = conn.execute(
        """
        SELECT f.*, d.first_seen_path, d.doc_type, d.parse_status, d.processing_profile
        FROM account_year_facts AS f
                 JOIN documents AS d ON d.content_sha256 = f.document_sha256
        WHERE f.tax_year = ?
          AND f.is_canonical = 1
        ORDER BY f.id
        """,
        (year,),
    ).fetchall()
    facts = [FactRecord.from_row(fact) for fact in facts]
    included_fact_ids = {fact.id for fact in facts if not _is_excluded_box3_fact(fact)}
    asset_rows: list[AssetExportRow] = []

    # Canonical statement facts are the authoritative Box 3 inventory.
    for fact in facts:
        fact_id = int(fact.id)
        if fact_id not in included_fact_ids:
            continue
        actual_return = _fact_return(fact)
        asset_rows.append(
            AssetExportRow(
                tax_year=year,
                asset_id=f"fact-{fact_id}",
                category="canonical statement fact",
                institution=fact.issuer,
                account_id=fact.account_key,
                label=fact.account_label,
                coverage_status="COMPLETE" if _fact_has_actual_return(fact) else "PARTIAL",
                declared_start_capital=None,
                declared_end_capital=None,
                source_start_capital=fact.start_balance,
                source_end_capital=fact.end_balance,
                deposits=fact.deposits,
                withdrawals=fact.withdrawals,
                interest_received=fact.interest_received,
                interest_paid=fact.interest_paid,
                net_interest=_optional_net(
                    [fact], "interest_received", "interest_paid"
                ),
                dividends_gross=fact.dividends_gross,
                withholding_tax=fact.withholding_tax,
                net_dividends=_optional_net(
                    [fact], "dividends_gross", "withholding_tax"
                ),
                market_value_change=fact.capital_gain,
                actual_return_from_sources=actual_return,
                return_used=actual_return or 0.0,
                currency=fact.currency,
                native_actual_return=_native_fact_return(fact),
                return_basis="canonical statement fact" if (fact.currency or "EUR") == "EUR" else "requires EUR conversion; native amounts retained",
                matched_fact_ids=fact_id,
                included_fact_ids=fact_id,
                source_document_sha256s=fact.document_sha256,
                source_paths=fact.first_seen_path,
            )
        )

    fact_rows = []
    for fact in facts:
        fact_id = int(fact.id)
        excluded = _is_excluded_box3_fact(fact)
        included = fact_id in included_fact_ids and (fact.currency or "EUR") == "EUR"
        fact_rows.append(
            SourceFactExportRow(
                tax_year=year,
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
                calculated_actual_return=_fact_return(fact),
                native_actual_return=_native_fact_return(fact),
                has_usable_actual_return=_fact_has_actual_return(fact),
                matched_asset_ids="",
                primary_asset_id=None,
                included_in_year_total=included,
                exclusion_reason=(
                    "excluded from Box 3" if excluded else ("requires EUR conversion" if (fact.currency or "EUR") != "EUR" else "unmatched to declared inventory")
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


def _optional_sum(rows: Iterable[FactRecord], key: MoneyField) -> float | None:
    values = [getattr(row, key) for row in rows if getattr(row, key) is not None]
    return float(sum(values)) if values else None


def _optional_net(
        rows: Iterable[FactRecord], positive_key: MoneyField, negative_key: MoneyField
) -> float | None:
    rows = list(rows)
    positive = _optional_sum(rows, positive_key)
    negative = _optional_sum(rows, negative_key)
    if positive is None and negative is None:
        return None
    return (positive or 0.0) - (negative or 0.0)
