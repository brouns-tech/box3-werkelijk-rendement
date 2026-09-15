from __future__ import annotations

import csv
import io
import json
import sqlite3
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from wr.db import connect
from wr.portfolio import _fact_has_actual_return, _fact_return, _is_excluded_box3_fact


def create_audit_export(
        conn: sqlite3.Connection, years: Iterable[int] | None = None
) -> bytes:
    """Create a portable audit bundle from the calculated database state."""
    selected_years = _selected_years(conn, years)
    yearly_rows = [_year_summary(conn, year) for year in selected_years]
    asset_rows: list[dict[str, Any]] = []
    fact_rows: list[dict[str, Any]] = []
    tax_rows: list[dict[str, Any]] = []

    for year in selected_years:
        assets, facts = _asset_and_fact_rows(conn, year)
        asset_rows.extend(assets)
        fact_rows.extend(facts)
        tax_rows.extend(
            dict(row)
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

    manifest = {
        "format": "werkelijk-rendement-audit",
        "version": 1,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "tax_years": selected_years,
        "files": {
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
        "calculation_notes": [
            "actual_return follows the same gain-method rules as the portfolio calculation.",
            "Net interest is interest_received minus interest_paid.",
            "Net dividends are dividends_gross minus withholding_tax.",
            "A source fact matched to multiple declared assets is included once, under the first asset id.",
            "Missing or partial assets contribute 0.00 to return_used and remain visibly warned.",
            "Declared balances and parsed source balances are exported separately; they may differ.",
        ],
    }

    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        bundle.writestr("manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False))
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
        FROM declared_box3_assets
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


def _year_summary(conn: sqlite3.Connection, year: int) -> dict[str, Any]:
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

    return {
        "tax_year": year,
        "coverage_status": _value(portfolio, "coverage_status"),
        "start_capital_from_sources": _value(portfolio, "start_balance"),
        "end_capital_from_sources": _value(portfolio, "end_balance"),
        "deposits": _value(portfolio, "deposits"),
        "withdrawals": _value(portfolio, "withdrawals"),
        "net_interest": _value(portfolio, "interest_received"),
        "net_dividends": _value(portfolio, "dividends_net"),
        "capital_gain": _value(portfolio, "capital_gain"),
        "actual_return_used": _value(portfolio, "known_combined_actual_return"),
        "source_fact_count": _value(portfolio, "source_fact_count"),
        "missing_asset_summary": _value(portfolio, "missing_asset_summary"),
        "declared_assets_0101": _value(tax_return, "bezittingen_0101"),
        "declared_assets_3112": _value(tax_return, "bezittingen_3112"),
        "declared_debts_0101": _value(tax_return, "schulden_0101"),
        "declared_debts_3112": _value(tax_return, "schulden_3112"),
        "taxable_base": _value(tax_return, "grondslag"),
        "estimated_household_tax_savings": savings,
    }


def _asset_and_fact_rows(
        conn: sqlite3.Connection, year: int
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    assets = conn.execute(
        """
        SELECT *
        FROM declared_box3_assets
        WHERE tax_year = ?
        ORDER BY id
        """,
        (year,),
    ).fetchall()
    facts = conn.execute(
        """
        SELECT f.*, d.first_seen_path, d.doc_type, d.parse_status
        FROM account_year_facts AS f
                 JOIN documents AS d ON d.content_sha256 = f.document_sha256
        WHERE f.tax_year = ?
          AND f.is_canonical = 1
        ORDER BY f.id
        """,
        (year,),
    ).fetchall()
    facts_by_id = {int(fact["id"]): fact for fact in facts}
    links: dict[int, list[int]] = {fact_id: [] for fact_id in facts_by_id}
    asset_matches: dict[int, list[int]] = {}
    for asset in assets:
        matched = [
            int(fact_id)
            for fact_id in _json_list(asset["matched_fact_ids"])
            if int(fact_id) in facts_by_id
        ]
        asset_matches[int(asset["id"])] = matched
        for fact_id in matched:
            links[fact_id].append(int(asset["id"]))

    primary_asset = {
        fact_id: min(asset_ids) for fact_id, asset_ids in links.items() if asset_ids
    }
    has_inventory = bool(assets)
    included_fact_ids = {
        fact_id
        for fact_id, fact in facts_by_id.items()
        if not _is_excluded_box3_fact(fact)
           and (not has_inventory or fact_id in primary_asset)
    }

    asset_rows = []
    for asset in assets:
        asset_id = int(asset["id"])
        matched_ids = asset_matches[asset_id]
        assigned_ids = [
            fact_id
            for fact_id in matched_ids
            if primary_asset.get(fact_id) == asset_id and fact_id in included_fact_ids
        ]
        assigned = [facts_by_id[fact_id] for fact_id in assigned_ids]
        usable = [fact for fact in assigned if _fact_has_actual_return(fact)]
        known_return = sum((_fact_return(fact) or 0.0) for fact in assigned)
        assumed_zero = not usable
        if usable:
            return_basis = "matched canonical source facts"
        elif abs(asset["balance_0101"] or 0) < 1 and abs(
                asset["balance_3112"] or 0
        ) < 1:
            return_basis = "0% assumption: immaterial declared balance"
        elif matched_ids:
            return_basis = "0% assumption: matched source lacks usable return data"
        else:
            return_basis = "0% assumption: no matched source data"
        asset_rows.append(
            {
                "tax_year": year,
                "asset_id": asset_id,
                "category": asset["category"],
                "institution": asset["institution"],
                "account_id": asset["account_id"],
                "label": asset["label"],
                "coverage_status": asset["coverage_status"],
                "declared_start_capital": asset["balance_0101"],
                "declared_end_capital": asset["balance_3112"],
                "source_start_capital": _optional_sum(assigned, "start_balance"),
                "source_end_capital": _optional_sum(assigned, "end_balance"),
                "deposits": _optional_sum(assigned, "deposits"),
                "withdrawals": _optional_sum(assigned, "withdrawals"),
                "interest_received": _optional_sum(assigned, "interest_received"),
                "interest_paid": _optional_sum(assigned, "interest_paid"),
                "net_interest": _optional_net(
                    assigned, "interest_received", "interest_paid"
                ),
                "dividends_gross": _optional_sum(assigned, "dividends_gross"),
                "withholding_tax": _optional_sum(assigned, "withholding_tax"),
                "net_dividends": _optional_net(
                    assigned, "dividends_gross", "withholding_tax"
                ),
                "capital_gain": _optional_sum(assigned, "capital_gain"),
                "actual_return_from_sources": known_return if usable else None,
                "return_used": 0.0 if assumed_zero else known_return,
                "return_basis": return_basis,
                "matched_fact_ids": _join_ids(matched_ids),
                "included_fact_ids": _join_ids(assigned_ids),
                "source_document_sha256s": ";".join(
                    sorted({fact["document_sha256"] for fact in assigned})
                ),
                "source_paths": ";".join(
                    sorted({fact["first_seen_path"] or "" for fact in assigned})
                ),
            }
        )

    # A year without a parsed tax-return inventory still gets one auditable asset row per fact.
    if not assets:
        for fact in facts:
            fact_id = int(fact["id"])
            if fact_id not in included_fact_ids:
                continue
            actual_return = _fact_return(fact)
            asset_rows.append(
                {
                    "tax_year": year,
                    "asset_id": f"fact-{fact_id}",
                    "category": "source fact (no declared inventory)",
                    "institution": fact["issuer"],
                    "account_id": fact["account_key"],
                    "label": fact["account_label"],
                    "coverage_status": "UNKNOWN",
                    "declared_start_capital": None,
                    "declared_end_capital": None,
                    "source_start_capital": fact["start_balance"],
                    "source_end_capital": fact["end_balance"],
                    "deposits": fact["deposits"],
                    "withdrawals": fact["withdrawals"],
                    "interest_received": fact["interest_received"],
                    "interest_paid": fact["interest_paid"],
                    "net_interest": _optional_net(
                        [fact], "interest_received", "interest_paid"
                    ),
                    "dividends_gross": fact["dividends_gross"],
                    "withholding_tax": fact["withholding_tax"],
                    "net_dividends": _optional_net(
                        [fact], "dividends_gross", "withholding_tax"
                    ),
                    "capital_gain": fact["capital_gain"],
                    "actual_return_from_sources": actual_return,
                    "return_used": actual_return or 0.0,
                    "return_basis": "canonical source fact; declared inventory unavailable",
                    "matched_fact_ids": fact_id,
                    "included_fact_ids": fact_id,
                    "source_document_sha256s": fact["document_sha256"],
                    "source_paths": fact["first_seen_path"],
                }
            )

    fact_rows = []
    for fact in facts:
        fact_id = int(fact["id"])
        excluded = _is_excluded_box3_fact(fact)
        included = fact_id in included_fact_ids
        fact_rows.append(
            {
                "tax_year": year,
                "fact_id": fact_id,
                "issuer": fact["issuer"],
                "account_key": fact["account_key"],
                "account_label": fact["account_label"],
                "holder_names": fact["holder_names"],
                "ownership": fact["ownership"],
                "currency": fact["currency"],
                "start_capital": fact["start_balance"],
                "end_capital": fact["end_balance"],
                "deposits": fact["deposits"],
                "withdrawals": fact["withdrawals"],
                "interest_received": fact["interest_received"],
                "interest_paid": fact["interest_paid"],
                "dividends_gross": fact["dividends_gross"],
                "withholding_tax": fact["withholding_tax"],
                "capital_gain": fact["capital_gain"],
                "gain_method": fact["gain_method"],
                "calculated_actual_return": _fact_return(fact),
                "has_usable_actual_return": _fact_has_actual_return(fact),
                "matched_asset_ids": _join_ids(links.get(fact_id, [])),
                "primary_asset_id": primary_asset.get(fact_id),
                "included_in_year_total": included,
                "exclusion_reason": (
                    "excluded from Box 3" if excluded else "unmatched to declared inventory"
                )
                if not included
                else None,
                "document_sha256": fact["document_sha256"],
                "source_path": fact["first_seen_path"],
                "document_type": fact["doc_type"],
                "parse_status": fact["parse_status"],
                "extra": fact["extra"],
            }
        )
    return asset_rows, fact_rows


def _write_csv(
        bundle: zipfile.ZipFile, name: str, rows: list[dict[str, Any]]
) -> None:
    buffer = io.StringIO(newline="")
    fieldnames = list(rows[0]) if rows else ["no_rows"]
    writer = csv.DictWriter(buffer, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    bundle.writestr(name, "\ufeff" + buffer.getvalue())


def _value(row: sqlite3.Row | None, key: str) -> Any:
    return row[key] if row is not None else None


def _json_list(value: str | None) -> list[Any]:
    if not value:
        return []
    try:
        result = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return []
    return result if isinstance(result, list) else []


def _optional_sum(rows: Iterable[sqlite3.Row], key: str) -> float | None:
    values = [row[key] for row in rows if row[key] is not None]
    return float(sum(values)) if values else None


def _optional_net(
        rows: Iterable[sqlite3.Row], positive_key: str, negative_key: str
) -> float | None:
    rows = list(rows)
    positive = _optional_sum(rows, positive_key)
    negative = _optional_sum(rows, negative_key)
    if positive is None and negative is None:
        return None
    return (positive or 0.0) - (negative or 0.0)


def _join_ids(values: Iterable[int]) -> str:
    return ";".join(str(value) for value in values)
