from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from wr.models import CoverageStatus


@dataclass
class CoverageResult:
    tax_year: int
    coverage_status: str
    known_combined_actual_return: float | None
    start_balance: float
    end_balance: float
    deposits: float
    withdrawals: float
    interest_received: float
    dividends_net: float
    capital_gain: float
    source_fact_count: int
    missing: list[str]


def rebuild_portfolio(conn: sqlite3.Connection) -> None:
    years = {
        r[0]
        for r in conn.execute(
            "SELECT DISTINCT tax_year FROM account_year_facts WHERE is_canonical = 1"
        ).fetchall()
    }

    for year in sorted(y for y in years if y):
        result = _coverage_for_year(conn, year)
        conn.execute(
            """
            INSERT INTO yearly_portfolio (
                tax_year, coverage_status, known_combined_actual_return,
                start_balance, end_balance, deposits, withdrawals,
                interest_received, dividends_net, capital_gain,
                source_fact_count, missing_asset_summary
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(tax_year) DO UPDATE SET
                coverage_status=excluded.coverage_status,
                known_combined_actual_return=excluded.known_combined_actual_return,
                start_balance=excluded.start_balance,
                end_balance=excluded.end_balance,
                deposits=excluded.deposits,
                withdrawals=excluded.withdrawals,
                interest_received=excluded.interest_received,
                dividends_net=excluded.dividends_net,
                capital_gain=excluded.capital_gain,
                source_fact_count=excluded.source_fact_count,
                missing_asset_summary=excluded.missing_asset_summary
            """,
            (
                result.tax_year,
                result.coverage_status,
                result.known_combined_actual_return,
                result.start_balance,
                result.end_balance,
                result.deposits,
                result.withdrawals,
                result.interest_received,
                result.dividends_net,
                result.capital_gain,
                result.source_fact_count,
                "; ".join(result.missing) if result.missing else None,
            ),
        )
    conn.commit()


def _coverage_for_year(conn: sqlite3.Connection, year: int) -> CoverageResult:
    facts = conn.execute(
        "SELECT * FROM account_year_facts WHERE tax_year = ? AND is_canonical = 1",
        (year,),
    ).fetchall()

    missing: list[str] = []
    eligible_facts = [f for f in facts if not _is_excluded_box3_fact(f)]

    for fact in eligible_facts:
        if not _fact_has_actual_return(fact):
            missing.append(
                f"{fact['issuer']} {fact['account_key']} (no actual-return fields)"
            )

    used_facts = eligible_facts
    start = _sum(used_facts, "start_balance")
    end = _sum(used_facts, "end_balance")
    deposits = _sum(used_facts, "deposits")
    withdrawals = _sum(used_facts, "withdrawals")
    interest = _sum(used_facts, "interest_received") - _sum(used_facts, "interest_paid")
    dividends = _sum(used_facts, "dividends_gross") - _sum(used_facts, "withholding_tax")
    capital = 0.0
    known_return = 0.0
    for f in used_facts:
        known_return += _fact_return(f) or 0.0
        if f["capital_gain"] is not None:
            capital += f["capital_gain"]

    if not eligible_facts:
        coverage = CoverageStatus.UNKNOWN.value
        missing.append("no canonical Box 3 statements for this year")
    elif missing:
        coverage = CoverageStatus.PARTIAL.value
    else:
        coverage = CoverageStatus.COMPLETE.value

    return CoverageResult(
        tax_year=year,
        coverage_status=coverage,
        known_combined_actual_return=known_return if used_facts else None,
        start_balance=start,
        end_balance=end,
        deposits=deposits,
        withdrawals=withdrawals,
        interest_received=interest,
        dividends_net=dividends,
        capital_gain=capital,
        source_fact_count=len(used_facts),
        missing=missing,
    )


def _is_excluded_box3_fact(fact) -> bool:
    key = (fact["account_key"] or "").lower()
    label = (fact["account_label"] or "").lower()
    if key.endswith("-pensioen") or "pensioen" in label:
        return True
    extra = fact["extra"]
    if extra:
        try:
            import json

            data = json.loads(extra) if isinstance(extra, str) else extra
            if isinstance(data, dict) and data.get("box3") is False:
                return True
        except Exception:  # noqa: BLE001
            pass
    return False


def is_box3_fact(fact) -> bool:
    return not _is_excluded_box3_fact(fact)


def _fact_has_actual_return(fact) -> bool:
    if fact["interest_received"] is not None:
        return True
    if fact["dividends_gross"] is not None:
        return True
    if fact["capital_gain"] is not None and fact["gain_method"] in {
        "balance_flow",
        "earned_return",
        "interest_only",
        "explicit",
    }:
        return True
    # Start/end alone without flows is not enough for investments
    if (
        fact["start_balance"] is not None
        and fact["end_balance"] is not None
        and fact["deposits"] is not None
        and fact["withdrawals"] is not None
    ):
        return True
    # Savings with interest_only already handled; bank with only balances → partial
    if fact["issuer"] in {"ing", "sns", "raisin", "revolut"} and fact["interest_received"] is not None:
        return True
    return False


def _fact_return(fact) -> float | None:
    method = fact["gain_method"] or ""
    if method == "earned_return" and fact["capital_gain"] is not None:
        return fact["capital_gain"]
    if method == "balance_flow" and fact["capital_gain"] is not None:
        return fact["capital_gain"]
    if method == "interest_only":
        return (fact["interest_received"] or 0) - (fact["interest_paid"] or 0)
    total = 0.0
    has = False
    if fact["interest_received"] is not None or fact["interest_paid"] is not None:
        total += (fact["interest_received"] or 0) - (fact["interest_paid"] or 0)
        has = True
    if fact["dividends_gross"] is not None:
        total += fact["dividends_gross"] - (fact["withholding_tax"] or 0)
        has = True
    if fact["capital_gain"] is not None and method not in {"interest_only", "balance_delta_incomplete"}:
        if not has:
            total += fact["capital_gain"]
            has = True
    return total if has else None


def _sum(rows, col: str) -> float:
    return float(sum((r[col] or 0) for r in rows))
