from __future__ import annotations

import argparse
import json
import re
import sqlite3
from pathlib import Path

import pandas as pd
import streamlit as st

from wr.config import load_config, resolve_db_path
from wr.export import create_audit_export
from wr.portfolio import _fact_return, is_box3_fact


def _connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def _currency(value: float | None) -> str:
    return "—" if value is None else f"€ {value:,.2f}"


def _decision_label(recommendation: str) -> str:
    labels = {
        "ACTUAL_BETTER": "Actual return better",
        "FICTITIOUS_BETTER": "Fictitious return better",
        "EQUAL": "No material difference",
        "INDETERMINATE_MISSING_DATA": "Incomplete data",
        "NEEDS_MANUAL_RSAMW": "Manual rSAMw needed",
        "NOT_APPLICABLE": "Not applicable",
    }
    return labels.get(recommendation, recommendation)


def _decision_rows(results) -> list[dict[str, str]]:
    rows = []
    for result in results:
        actual_tax = result["estimated_box3_tax_actual"]
        fictitious_tax = result["estimated_box3_tax_fictitious"]
        savings = None
        if actual_tax is not None and fictitious_tax is not None:
            savings = max(0.0, fictitious_tax - actual_tax)
        rows.append(
            {
                "Issuer": result["partner_name"],
                "Actual return": _currency(result["allocated_actual_return"]),
                "Fictitious return": _currency(result["fictitious_return"]),
                "Decision": _decision_label(result["recommendation"]),
                "Potential tax savings": _currency(savings),
            }
        )
    return rows


def _person_key(name: str | None) -> str:
    return re.sub(r"[^a-z]", "", (name or "").lower())


def _holder_label(value: str | None, canonical_names: dict[str, str] | None = None) -> str:
    try:
        holders = json.loads(value or "[]")
    except json.JSONDecodeError:
        holders = []
    if not holders:
        return "Unknown"
    canonical_names = canonical_names or {}
    normalized = []
    for holder in holders:
        holder_key = _person_key(holder)
        canonical = next(
            (
                name
                for alias, name in canonical_names.items()
                if alias and (alias in holder_key or holder_key in alias)
            ),
            holder,
        )
        if canonical not in normalized:
            normalized.append(canonical)
    return ", ".join(normalized)


def _canonical_name_map(partner_cfg: dict) -> dict[str, str]:
    names = {}
    for slot in ("partner_a", "partner_b"):
        canonical = partner_cfg.get(slot)
        if not canonical:
            continue
        surname = _person_key(canonical.split()[-1])
        for alias in [canonical, *partner_cfg.get(f"{slot}_aliases", [])]:
            alias_key = _person_key(alias)
            if alias_key != surname:
                names[alias_key] = canonical
    return names


def _owner_style(value: str, colors: dict[str, str]) -> str:
    holder_keys = [_person_key(holder) for holder in value.split(", ")]
    matches = {color for name, color in colors.items() if any(name in holder for holder in holder_keys)}
    if len(matches) == 1:
        return f"background-color: {matches.pop()}; color: #f8fafc"
    if len(matches) > 1:
        return "background-color: #581c87; color: #f8fafc"
    return "background-color: #334155; color: #f8fafc"


def _styled_table(rows: list[dict], owner_column: str, colors: dict[str, str]):
    frame = pd.DataFrame(rows)
    return frame.style.apply(
        lambda row: [_owner_style(str(row[owner_column]), colors)] * len(row), axis=1
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=None)
    args, _ = parser.parse_known_args()

    cfg = load_config(args.config)
    db_path = resolve_db_path(cfg)

    st.set_page_config(page_title="Werkelijk Rendement", layout="wide")
    st.title("Werkelijk rendement — Box 3")
    st.caption(f"DB: `{db_path}`")

    if not db_path.exists():
        st.warning("Database not found. Run `wr import` first.")
        return

    conn = _connect(db_path)

    years = [
        r[0]
        for r in conn.execute(
            "SELECT DISTINCT tax_year FROM yearly_portfolio ORDER BY tax_year DESC"
        ).fetchall()
    ]
    if not years:
        years = [
            r[0]
            for r in conn.execute(
                "SELECT DISTINCT tax_year FROM tax_returns ORDER BY tax_year DESC"
            ).fetchall()
        ]
    if not years:
        st.info("No tax years in database yet.")
        return

    year = st.selectbox("Tax year", years, index=0)
    st.download_button(
        "Download audit export",
        data=create_audit_export(conn, [year]),
        file_name=f"werkelijk-rendement-{year}-audit.zip",
        mime="application/zip",
        help="ZIP with yearly totals, asset calculations, source facts, and tax results.",
    )

    portfolio = conn.execute(
        "SELECT * FROM yearly_portfolio WHERE tax_year = ?", (year,)
    ).fetchone()
    results = conn.execute(
        "SELECT * FROM partner_tax_results WHERE tax_year = ? ORDER BY partner",
        (year,),
    ).fetchall()
    owner_colors = {}
    partner_cfg = cfg.get("partners", {})
    canonical_names = _canonical_name_map(partner_cfg)
    for slot, color in (("partner_a", "#1e3a5f"), ("partner_b", "#14532d")):
        canonical = partner_cfg.get(slot)
        for alias, name in canonical_names.items():
            if name == canonical:
                owner_colors[alias] = color

    col1, col2, col3 = st.columns(3)
    if portfolio:
        col1.metric("Coverage", portfolio["coverage_status"])
        col2.metric("Actual return", _currency(portfolio["known_combined_actual_return"]))
        col3.metric("Statement sources", portfolio["source_fact_count"] or 0)
        if portfolio["missing_asset_summary"]:
            st.warning(f"Missing / partial: {portfolio['missing_asset_summary']}")
    else:
        st.info("No portfolio rollup for this year.")

    st.subheader("Decision overview")
    if results:
        st.dataframe(
            _styled_table(_decision_rows(results), "Issuer", owner_colors),
            width="stretch",
            hide_index=True,
        )
    else:
        st.info("No tax decision is available for this year.")

    facts = conn.execute(
        """
        SELECT issuer, account_key, account_label, holder_names, ownership, currency,
               start_balance, end_balance, deposits, withdrawals,
               interest_received, interest_paid, dividends_gross, withholding_tax,
               capital_gain, gain_method, extra
        FROM account_year_facts
        WHERE tax_year = ? AND is_canonical = 1
        ORDER BY issuer, account_key
        """,
        (year,),
    ).fetchall()
    st.subheader("Account overview")
    fact_rows = []
    for fact in facts:
        fact_rows.append(
            {
                "Account holder": _holder_label(fact["holder_names"], canonical_names),
                "Box 3": is_box3_fact(fact),
                "Source": fact["issuer"].upper(),
                "Account label": fact["account_label"],
                "Account key": fact["account_key"],
                "Value 1 January": _currency(fact["start_balance"]),
                "Value 31 December": _currency(fact["end_balance"]),
                "Purchases / deposits": _currency(fact["deposits"]),
                "Sales / withdrawals": _currency(fact["withdrawals"]),
                "Received interest": _currency(fact["interest_received"]),
                "Paid interest": _currency(fact["interest_paid"]),
                "Gross dividends": _currency(fact["dividends_gross"]),
                "Withholding tax": _currency(fact["withholding_tax"]),
                "Calculated actual return": _currency(_fact_return(fact)),
                "Market-value component (internal)": _currency(fact["capital_gain"]),
                "Currency": fact["currency"] or "EUR",
                "Calculation method": fact["gain_method"],
            }
        )
    legend_rows = [
        {"Account holder": partner_cfg.get("partner_a", "Partner A"), "Meaning": "Individual"},
        {"Account holder": partner_cfg.get("partner_b", "Partner B"), "Meaning": "Individual"},
        {
            "Account holder": ", ".join(
                name
                for name in (partner_cfg.get("partner_a"), partner_cfg.get("partner_b"))
                if name
            ),
            "Meaning": "Joint",
        },
        {"Account holder": "Unknown", "Meaning": "Holder not established"},
    ]
    st.caption("Account-holder color legend")
    legend_column, _ = st.columns(2)
    with legend_column:
        st.dataframe(
            _styled_table(legend_rows, "Account holder", owner_colors),
            width="stretch",
            hide_index=True,
        )
    st.dataframe(
        _styled_table(fact_rows, "Account holder", owner_colors),
        width="stretch",
        hide_index=True,
    )

    with st.expander("Import diagnostics"):
        docs = conn.execute(
            """
            SELECT COALESCE(issuer, 'unknown') AS issuer,
                   COALESCE(doc_type, 'unclassified') AS doc_type,
                   SUM(CASE WHEN parse_status = 'parsed' THEN 1 ELSE 0 END) AS parsed,
                   SUM(CASE WHEN parse_status = 'skipped' THEN 1 ELSE 0 END) AS skipped,
                   SUM(CASE WHEN parse_status = 'failed' THEN 1 ELSE 0 END) AS failed,
                   COUNT(*) AS total
            FROM documents
            GROUP BY issuer, doc_type
            ORDER BY total DESC, issuer, doc_type
            """
        ).fetchall()
        diagnostic_rows = [
            {
                "Source": row["issuer"].upper() if row["issuer"] != "unknown" else "Unknown",
                "Document type": row["doc_type"].replace("_", " ").title(),
                "Parsed": row["parsed"],
                "Skipped": row["skipped"],
                "Failed": row["failed"],
                "Total": row["total"],
            }
            for row in docs
        ]
        st.dataframe(diagnostic_rows, width="stretch", hide_index=True)


if __name__ == "__main__":
    main()
