from __future__ import annotations

import argparse
import json
import os
from functools import partial

import pandas as pd
import streamlit as st

from wr.config import PartnerSettings, load_settings, resolve_db_path
from wr.db import connect, init_db
from wr.identities import identity_slot, observed_names, name_key
from wr.recommend import rebuild_recommendations
from dashboard.settings import documents_ui, taxpayers_ui
from dashboard.workspace_settings import workspace_settings_ui
from wr.export import create_audit_export
from wr.money import subtract
from wr.i18n import currency, coverage_details, status_label, translator
from dashboard.localization import select_language
from dashboard.ownership import PURPLE, UNKNOWN, slot_color, table_style
from wr.portfolio import _fact_return, is_box3_fact
from wr.import_pipeline import pending_reprocessing


def _currency(value: float | None, language: str = "en") -> str:
    return currency(value, language)


def _decision_label(recommendation: str, language: str = "en") -> str:
    return status_label(recommendation, language)


def _decision_rows(results, language: str = "en") -> list[dict[str, str]]:
    t = translator(language)
    money = partial(_currency, language=language)
    rows = []
    for result in results:
        actual_tax = result["estimated_box3_tax_actual"]
        fictitious_tax = result["estimated_box3_tax_fictitious"]
        savings = None
        if actual_tax is not None and fictitious_tax is not None:
            savings = max(0.0, subtract(fictitious_tax, actual_tax))
        rows.append(
            {
                t("Taxpayer"): result["partner_name"],
                t("Actual return"): money(result["allocated_actual_return"]),
                t("Fictitious return"): money(result["fictitious_return"]),
                t("Decision"): _decision_label(result["recommendation"], language),
                t("Potential tax savings"): money(savings),
            }
        )
    return rows


def _person_key(name: str | None) -> str:
    return " ".join(name_key(name or ""))


def _holder_label(value: str | None, canonical_names: dict[str, str] | None = None, language: str = "en") -> str:
    try:
        holders = json.loads(value or "[]")
    except json.JSONDecodeError:
        holders = []
    if not holders:
        return translator(language)("Unknown")
    canonical_names = canonical_names or {}
    normalized = []
    for holder in holders:
        holder_key = _person_key(holder)
        canonical = next(
            (
                name
                for alias, name in canonical_names.items()
                if alias and alias == holder_key
            ),
            holder,
        )
        if canonical not in normalized:
            normalized.append(canonical)
    return ", ".join(normalized)


def _canonical_name_map(partner_cfg: PartnerSettings) -> dict[str, str]:
    names = {}
    for slot, canonical in partner_cfg.identities():
        if not canonical:
            continue
        surname = _person_key(canonical.split()[-1])
        for alias in [canonical, *partner_cfg.aliases_for(slot)]:
            alias_key = _person_key(alias)
            if alias_key != surname:
                names[alias_key] = canonical
    return names


def _owner_style(value: str, colors: dict[str, str], *, muted: bool = False, joint: bool = False) -> str:
    holder_keys = [_person_key(holder) for holder in value.split(", ")]
    matches = {color for name, color in colors.items() if name in holder_keys}
    if joint or len(matches) > 1:
        return table_style(PURPLE, muted=muted)
    return table_style(matches.pop() if matches else UNKNOWN, muted=muted)


def _owner_colors(partner_cfg: PartnerSettings, canonical_names: dict[str, str]) -> dict[str, str]:
    return {
        alias: slot_color(slot)
        for slot, canonical in partner_cfg.identities() if canonical
        for alias, name in canonical_names.items() if name == canonical
    }


def _styled_table(
    rows: list[dict], owner_column: str, colors: dict[str, str], *,
    muted_rows: list[bool] | None = None, joint_rows: list[bool] | None = None,
):
    frame = pd.DataFrame(rows)
    return frame.style.apply(
        lambda row: [_owner_style(
            str(row[owner_column]), colors,
            muted=muted_rows[row.name] if muted_rows is not None else False,
            joint=joint_rows[row.name] if joint_rows is not None else False,
        )] * len(row), axis=1
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", default=None)
    args, _ = parser.parse_known_args()

    cfg = load_settings(args.workspace)
    db_path = resolve_db_path(cfg)

    st.set_page_config(page_title="Werkelijk Rendement", layout="wide")
    language = select_language(cfg.project_root, "nl" if os.environ.get("WR_CONTROL_URL") else "en")
    t = translator(language)
    st.title(t("Werkelijk rendement — Box 3"))
    st.caption(t("Database: `{name}`", name=db_path.name))

    job = st.session_state.get("import_job")
    if os.environ.get("WR_CONTROL_URL"):
        from wr.desktop import desktop_request
        with st.sidebar:
            st.caption(t("Closing the browser tab leaves the application running. Use Exit application to stop it."))
            if st.button(t("Open local data"), key="open_local_data"):
                desktop_request("data")
            active = job is not None and not job.done.is_set()
            if st.button(t("Exit application"), disabled=active, key="exit_application"):
                desktop_request("stop")
                st.info(t("The application is stopping. You can close this browser tab."))
                st.stop()
    if os.environ.get("WR_CONTROL_URL") and job is not None and not job.done.is_set():
        documents_ui(cfg)
        st.stop()

    conn = connect(db_path)
    init_db(conn)
    overview, documents, taxpayers, settings = st.tabs([t("Overview"), t("Documents"), t("Taxpayers"), t("Settings")])
    try:
        with settings:
            workspace_settings_ui(cfg)
        with documents:
            documents_ui(cfg)
        with taxpayers:
            partner_cfg = taxpayers_ui(cfg, conn)
        with overview:
            rebuild_recommendations(conn, partner_cfg)
            _overview(conn, partner_cfg, language)
    finally:
        conn.close()


def _overview(conn, partner_cfg: PartnerSettings, language: str = "en") -> None:
    t = translator(language)
    money = partial(_currency, language=language)
    if pending := pending_reprocessing(conn):
        st.warning(t("PDF extraction has been updated. Scan your document folder again to refresh {count} previously imported documents before reviewing the calculation.", count=pending))
        return

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
        st.info(t("No tax years in database yet."))
        return

    year = st.selectbox(t("Tax year"), years, index=0, key="tax_year")
    st.download_button(
        t("Download audit export"),
        data=create_audit_export(conn, [year]),
        file_name=f"werkelijk-rendement-{year}-audit.zip",
        mime="application/zip",
        help=t("ZIP with yearly totals, asset calculations, source facts, and tax results."),
    )

    portfolio = conn.execute(
        "SELECT * FROM yearly_portfolio WHERE tax_year = ?", (year,)
    ).fetchone()
    results = conn.execute(
        "SELECT * FROM partner_tax_results WHERE tax_year = ? ORDER BY partner",
        (year,),
    ).fetchall()
    canonical_names = _canonical_name_map(partner_cfg)
    for name in observed_names(conn):
        slot = identity_slot(name, partner_cfg)
        if slot:
            canonical_names[_person_key(name)] = partner_cfg.canonical_for(slot)
    owner_colors = _owner_colors(partner_cfg, canonical_names)

    col1, col2, col3 = st.columns(3)
    if portfolio:
        col1.metric(
            t("Coverage"), status_label(portfolio["coverage_status"], language),
            help=t("Coverage concerns imported statements only; it does not establish that all assets or partner documents are present."),
        )
        col2.metric(t("Actual return"), money(portfolio["known_combined_actual_return"]))
        col3.metric(t("Statement sources"), portfolio["source_fact_count"] or 0)
        if portfolio["missing_asset_summary"]:
            st.warning(t("Missing / partial: {details}", details=coverage_details(portfolio["missing_asset_summary"], language)))
    else:
        st.info(t("No portfolio rollup for this year."))

    st.subheader(t("Decision overview"))
    if results:
        st.dataframe(
            _styled_table(_decision_rows(results, language), t("Taxpayer"), owner_colors),
            width="stretch",
            hide_index=True,
        )
    else:
        st.info(t("No tax decision is available for this year."))

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
    st.subheader(t("Account overview"))
    fact_rows = []
    for fact in facts:
        child_account = any(
            (identity_slot(holder, partner_cfg) or "").startswith("child_")
            for holder in json.loads(fact["holder_names"] or "[]")
        )
        fact_rows.append(
            {
                t("Account holder"): _holder_label(fact["holder_names"], canonical_names, language),
                t("Allocation"): t("Joint") if child_account or fact["ownership"] == "joint" else t("Individual"),
                t("Box 3"): t("Yes") if is_box3_fact(fact) else t("No"),
                t("Source"): fact["issuer"].upper(),
                t("Account label"): fact["account_label"],
                t("Account key"): fact["account_key"],
                t("Value 1 January"): money(fact["start_balance"]),
                t("Value 31 December"): money(fact["end_balance"]),
                t("Purchases / deposits"): money(fact["deposits"]),
                t("Sales / withdrawals"): money(fact["withdrawals"]),
                t("Received interest"): money(fact["interest_received"]),
                t("Paid interest"): money(fact["interest_paid"]),
                t("Gross dividends"): money(fact["dividends_gross"]),
                t("Withholding tax"): money(fact["withholding_tax"]),
                t("Calculated actual return"): money(_fact_return(fact)),
                t("Market-value component (internal)"): money(fact["capital_gain"]),
                t("Currency"): fact["currency"] or "EUR",
                t("Calculation method"): status_label(fact["gain_method"], language),
            }
        )
    st.dataframe(
        _styled_table(
            fact_rows, t("Account holder"), owner_colors,
            muted_rows=[not is_box3_fact(fact) for fact in facts],
            joint_rows=[row[t("Allocation")] == t("Joint") for row in fact_rows],
        ),
        width="stretch",
        hide_index=True,
    )

    with st.expander(t("Import diagnostics")):
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
                t("Source"): row["issuer"].upper() if row["issuer"] != "unknown" else t("Unknown"),
                t("Document type"): status_label(row["doc_type"], language),
                t("Parsed"): row["parsed"],
                t("Skipped"): row["skipped"],
                t("Failed"): row["failed"],
                t("Total"): row["total"],
            }
            for row in docs
        ]
        st.dataframe(diagnostic_rows, width="stretch", hide_index=True)


if __name__ == "__main__":
    main()
