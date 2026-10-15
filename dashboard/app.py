from __future__ import annotations

from wr.storage.facts import canonical_facts

from wr.storage.adapters import fact_from_row

import argparse
import json
import os
from functools import partial

import pandas as pd
import streamlit as st

from wr.models.facts import Ownership
from wr.models.storage import FactRecord
from wr.models.settings import PartnerSettings
from wr.workspace.settings import load_settings, resolve_db_path
from wr.storage.connection import connect
from wr.storage.migrations import init_db
from wr.identities.matching import identity_slot, name_key
from wr.storage.identities import observed_names
from wr.calculations.service import rebuild_recommendations
from wr.calculations.allocation import individual_portfolio
from dashboard.settings import documents_ui, taxpayers_ui
from dashboard.workspace_settings import workspace_settings_ui
from wr.export import create_audit_export
from wr.money import Currency, subtract
from wr.i18n import currency, coverage_details, status_label, translator
from wr.messages import Messages
from dashboard.localization import select_language
from dashboard.ownership import PURPLE, UNKNOWN, slot_color, table_style
from wr.calculations.returns import native_fact_return, is_box3_fact
from wr.importing.reprocessing import pending_reprocessing


def _currency(value: float | None, language: str = "en", currency_code: Currency | str = Currency.EUR) -> str:
    return currency(value, language, currency_code)


def _decision_label(recommendation: str, language: str = "en") -> str:
    return status_label(recommendation, language)


def _decision_rows(results, language: str = "en", statement_returns=None) -> list[dict[str, str]]:
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
                t(Messages.TAXPAYER): result["partner_name"],
                **({t(Messages.STATEMENT_RETURN_BY_HOLDER): money(statement_returns.get(result["partner"]))} if statement_returns is not None else {}),
                t(Messages.TAX_ALLOCATION): "—" if result["allocation_ratio"] is None else f"{result['allocation_ratio']:.0%}",
                t(Messages.ALLOCATED_ACTUAL_RETURN): money(result["allocated_actual_return"]),
                t(Messages.FICTITIOUS_RETURN): money(result["fictitious_return"]),
                t(Messages.DECISION): _decision_label(result["recommendation"], language),
                t(Messages.POTENTIAL_TAX_SAVINGS): money(savings),
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
        return translator(language)(Messages.UNKNOWN)
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
    st.title(t(Messages.WERKELIJK_RENDEMENT_BOX_3))
    st.caption(t.database(name=db_path.name))

    job = st.session_state.get("import_job")
    if os.environ.get("WR_CONTROL_URL"):
        from wr.desktop.control import desktop_request
        with st.sidebar:
            st.caption(t(Messages.BROWSER_CLOSE_HELP))
            if st.button(t(Messages.OPEN_LOCAL_DATA), key="open_local_data"):
                desktop_request("data")
            active = job is not None and not job.done.is_set()
            if st.button(t(Messages.EXIT_APPLICATION), disabled=active, key="exit_application"):
                desktop_request("stop")
                st.info(t(Messages.APPLICATION_STOPPING))
                st.stop()
    if os.environ.get("WR_CONTROL_URL") and job is not None and not job.done.is_set():
        documents_ui(cfg)
        st.stop()

    conn = connect(db_path)
    init_db(conn)
    overview, documents, taxpayers, settings = st.tabs([t(Messages.OVERVIEW), t(Messages.DOCUMENTS), t(Messages.TAXPAYERS), t(Messages.SETTINGS)])
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
        st.warning(t.pdf_extraction_updated(count=pending))
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
        st.info(t(Messages.NO_TAX_YEARS_IN_DATABASE_YET))
        return

    year = st.selectbox(t(Messages.TAX_YEAR), years, index=0, key="tax_year")
    st.download_button(
        t(Messages.DOWNLOAD_AUDIT_EXPORT),
        data=create_audit_export(conn, [year]),
        file_name=f"werkelijk-rendement-{year}-audit.zip",
        mime="application/zip",
        help=t(Messages.AUDIT_EXPORT_HELP),
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
            t(Messages.COVERAGE), status_label(portfolio["coverage_status"], language),
            help=t(Messages.COVERAGE_HELP),
        )
        col2.metric(t(Messages.ACTUAL_RETURN), money(portfolio["known_combined_actual_return"]))
        col3.metric(t(Messages.STATEMENT_SOURCES), portfolio["source_fact_count"] or 0)
        if portfolio["missing_asset_summary"]:
            st.warning(t.missing_partial(details=coverage_details(portfolio["missing_asset_summary"], language)))
    else:
        st.info(t(Messages.NO_PORTFOLIO_ROLLUP_FOR_THIS_YEAR))

    st.subheader(t(Messages.DECISION_OVERVIEW))
    if results:
        statement_returns = {
            result["partner"]: individual_portfolio(canonical_facts(conn, year), year, result["partner_name"], partner_cfg)[0]
            for result in results
        }
        st.caption(t(Messages.STATEMENT_RETURNS_HELP))
        st.dataframe(
            _styled_table(_decision_rows(results, language, statement_returns), t(Messages.TAXPAYER), owner_colors),
            width="stretch",
            hide_index=True,
        )
    else:
        st.info(t(Messages.NO_TAX_DECISION_IS_AVAILABLE_FOR_THIS_YEAR))

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
    facts = [fact_from_row(row) for row in facts]
    st.subheader(t(Messages.ACCOUNT_OVERVIEW))
    fact_rows = []
    for fact in facts:
        account_money = partial(_currency, language=language, currency_code=fact.currency or Currency.EUR)
        child_account = any(
            (identity_slot(holder, partner_cfg) or "").startswith("child_")
            for holder in fact.holder_names
        )
        fact_rows.append(
            {
                t(Messages.ACCOUNT_HOLDER): _holder_label(json.dumps(fact.holder_names), canonical_names, language),
                t(Messages.ALLOCATION): t(Messages.JOINT) if child_account or fact.ownership == Ownership.JOINT else t(Messages.INDIVIDUAL),
                t(Messages.BOX_3): t(Messages.YES) if is_box3_fact(fact) else t(Messages.NO),
                t(Messages.SOURCE): fact.issuer.upper(),
                t(Messages.ACCOUNT_LABEL): fact.account_label,
                t(Messages.ACCOUNT_KEY): fact.account_key,
                t(Messages.VALUE_1_JANUARY): account_money(fact.start_balance),
                t(Messages.VALUE_31_DECEMBER): account_money(fact.end_balance),
                t(Messages.PURCHASES_DEPOSITS): account_money(fact.deposits),
                t(Messages.SALES_WITHDRAWALS): account_money(fact.withdrawals),
                t(Messages.RECEIVED_INTEREST): account_money(fact.interest_received),
                t(Messages.PAID_INTEREST): account_money(fact.interest_paid),
                t(Messages.GROSS_DIVIDENDS): account_money(fact.dividends_gross),
                t(Messages.WITHHOLDING_TAX): account_money(fact.withholding_tax),
                t(Messages.CALCULATED_ACTUAL_RETURN): account_money(native_fact_return(fact)),
                t(Messages.MARKET_VALUE_COMPONENT_INTERNAL): account_money(fact.capital_gain),
                t(Messages.CURRENCY): (fact.currency or Currency.EUR).value,
                t(Messages.CALCULATION_METHOD): status_label(fact.gain_method, language),
            }
        )
    st.caption(t(Messages.ACCOUNT_CURRENCY_HELP))
    st.dataframe(
        _styled_table(
            fact_rows, t(Messages.ACCOUNT_HOLDER), owner_colors,
            muted_rows=[not is_box3_fact(fact) for fact in facts],
            joint_rows=[row[t(Messages.ALLOCATION)] == t(Messages.JOINT) for row in fact_rows],
        ),
        width="stretch",
        hide_index=True,
    )

    with st.expander(t(Messages.IMPORT_DIAGNOSTICS)):
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
                t(Messages.SOURCE): row["issuer"].upper() if row["issuer"] != "unknown" else t(Messages.UNKNOWN),
                t(Messages.DOCUMENT_TYPE): status_label(row["doc_type"], language),
                t(Messages.PARSED): row["parsed"],
                t(Messages.SKIPPED): row["skipped"],
                t(Messages.FAILED): row["failed"],
                t(Messages.TOTAL): row["total"],
            }
            for row in docs
        ]
        st.dataframe(diagnostic_rows, width="stretch", hide_index=True)


if __name__ == "__main__":
    main()
