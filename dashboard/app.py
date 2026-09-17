from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

import streamlit as st

from wr.config import load_config, resolve_db_path
from wr.export import create_audit_export
from wr.portfolio import is_box3_fact


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
    partnership = conn.execute(
        """
        SELECT * FROM tax_returns
        WHERE tax_year = ?
        ORDER BY full_year_fiscal_partners DESC, grondslag DESC
        LIMIT 1
        """,
        (year,),
    ).fetchone()

    results = conn.execute(
        "SELECT * FROM partner_tax_results WHERE tax_year = ? ORDER BY partner",
        (year,),
    ).fetchall()

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
        st.dataframe(_decision_rows(results), width="stretch", hide_index=True)
    else:
        st.info("No tax decision is available for this year.")

    with st.expander("Diagnostics"):
        st.caption(
            "Account-level inventory is derived from canonical annual statements; "
            "the official tax return contributes aggregate figures only."
        )
        if partnership:
            st.subheader("Tax return")
            st.json(dict(partnership))
        if portfolio:
            st.subheader("Portfolio rollup")
            st.json(dict(portfolio))
        st.subheader("Canonical account facts (all statements)")
        st.caption("Includes non-Box 3 statements for diagnostics.")
        facts = conn.execute(
            """
            SELECT issuer, account_key, account_label, start_balance, end_balance,
                   deposits, withdrawals, interest_received, dividends_gross,
                   capital_gain, gain_method, extra
            FROM account_year_facts
            WHERE tax_year = ? AND is_canonical = 1
            ORDER BY issuer, account_key
            """,
            (year,),
        ).fetchall()
        fact_rows = []
        for fact in facts:
            row = dict(fact)
            row["Box 3"] = is_box3_fact(fact)
            fact_rows.append(row)
        st.dataframe(fact_rows, width="stretch")
        st.subheader("Import diagnostics")
        docs = conn.execute(
            """
            SELECT parse_status, issuer, doc_type, COUNT(*) AS n
            FROM documents
            GROUP BY parse_status, issuer, doc_type
            ORDER BY n DESC
            """
        ).fetchall()
        st.dataframe([dict(d) for d in docs], width="stretch")


if __name__ == "__main__":
    main()
