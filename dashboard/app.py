from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

import streamlit as st

from wr.config import load_config, resolve_db_path
from wr.export import create_audit_export


def _connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


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

    col1, col2, col3 = st.columns(3)
    portfolio = conn.execute(
        "SELECT * FROM yearly_portfolio WHERE tax_year = ?", (year,)
    ).fetchone()
    partnership = conn.execute(
        """
        SELECT *
        FROM tax_returns
        WHERE tax_year = ?
        ORDER BY full_year_fiscal_partners DESC, grondslag DESC LIMIT 1
        """,
        (year,),
    ).fetchone()

    if portfolio:
        col1.metric("Coverage", portfolio["coverage_status"])
        known = portfolio["known_combined_actual_return"]
        col2.metric(
            "Known combined actual return",
            f"€ {known:,.2f}" if known is not None else "—",
        )
        col3.metric("Canonical facts", portfolio["source_fact_count"] or 0)
        if portfolio["missing_asset_summary"]:
            st.warning(f"Missing / partial: {portfolio['missing_asset_summary']}")
    else:
        st.info("No portfolio rollup for this year.")

    if partnership:
        st.subheader("Fiscal partnership (from tax return)")
        a_ratio = partnership["allocation_a"]
        b_ratio = partnership["allocation_b"]
        st.write(
            {
                "full_year_partners": bool(partnership["full_year_fiscal_partners"]),
                "partner_a": partnership["partner_a_name"],
                "partner_b": partnership["partner_b_name"],
                "grondslag": partnership["grondslag"],
                "allocation_a": f"{a_ratio:.1%}" if a_ratio is not None else None,
                "allocation_b": f"{b_ratio:.1%}" if b_ratio is not None else None,
                "bezittingen_0101": partnership["bezittingen_0101"],
                "bezittingen_3112": partnership["bezittingen_3112"],
            }
        )

    st.subheader("Partner recommendations")
    results = conn.execute(
        "SELECT * FROM partner_tax_results WHERE tax_year = ? ORDER BY partner",
        (year,),
    ).fetchall()
    if results:
        savings = [
            r["estimated_tax_savings"]
            for r in results
            if r["estimated_tax_savings"] is not None
        ]
        if savings:
            st.metric(
                "Estimated household tax savings vs alternative",
                f"€ {sum(savings):,.2f}",
            )
        st.dataframe([dict(r) for r in results], use_container_width=True)
        for r in results:
            badge = r["recommendation"]
            if badge == "INDETERMINATE_MISSING_DATA":
                st.error(f"{r['partner_name']}: {badge} — {r['notes']}")
            elif badge == "ACTUAL_BETTER":
                st.success(f"{r['partner_name']}: {badge} — {r['notes']}")
            elif badge == "FICTITIOUS_BETTER":
                st.info(f"{r['partner_name']}: {badge} — {r['notes']}")
            else:
                st.write(f"{r['partner_name']}: **{badge}** — {r['notes']}")
    else:
        st.write("No partner results.")

    if portfolio:
        st.subheader("Combined balances / flows (from documents)")
        st.caption(
            "Gross dividends are included once in actual return. Withholding tax is "
            "shown separately; any credit or refund is outside this Box 3 comparison."
        )
        st.write(
            {
                "start_balance": portfolio["start_balance"],
                "end_balance": portfolio["end_balance"],
                "deposits": portfolio["deposits"],
                "withdrawals": portfolio["withdrawals"],
                "interest_received": portfolio["interest_received"],
                "dividends_gross": portfolio["dividends_gross"],
                "withholding_tax": portfolio["withholding_tax"],
                "dividends_net": portfolio["dividends_net"],
                "market_value_change": portfolio["capital_gain"],
            }
        )

    st.subheader("Declared Box 3 assets vs coverage")
    assets = conn.execute(
        """
        SELECT category,
               institution,
               account_id,
               label,
               balance_0101,
               balance_3112,
               coverage_status
        FROM declared_box3_assets
        WHERE tax_year = ?
        ORDER BY category, institution, account_id
        """,
        (year,),
    ).fetchall()
    if assets:
        st.dataframe([dict(a) for a in assets], use_container_width=True)
    else:
        st.write("No declared assets (tax return not parsed for this year).")

    with st.expander("Canonical account facts"):
        facts = conn.execute(
            """
            SELECT issuer,
                   account_key,
                   account_label,
                   start_balance,
                   end_balance,
                   deposits,
                   withdrawals,
                   interest_received,
                   dividends_gross,
                   capital_gain AS market_value_change,
                   gain_method
            FROM account_year_facts
            WHERE tax_year = ?
              AND is_canonical = 1
            ORDER BY issuer, account_key
            """,
            (year,),
        ).fetchall()
        st.dataframe([dict(f) for f in facts], use_container_width=True)

    with st.expander("Import diagnostics"):
        docs = conn.execute(
            """
            SELECT parse_status, issuer, doc_type, COUNT(*) AS n
            FROM documents
            GROUP BY parse_status, issuer, doc_type
            ORDER BY n DESC
            """
        ).fetchall()
        st.dataframe([dict(d) for d in docs], use_container_width=True)


if __name__ == "__main__":
    main()
