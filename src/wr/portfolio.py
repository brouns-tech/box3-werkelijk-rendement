from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass

from wr.models import CoverageStatus
from wr.pdf import normalize_account_id, normalize_iban


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
        for r in conn.execute("SELECT DISTINCT tax_year FROM declared_box3_assets").fetchall()
    }
    years |= {
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
    declared = conn.execute(
        "SELECT * FROM declared_box3_assets WHERE tax_year = ?", (year,)
    ).fetchall()
    facts = conn.execute(
        "SELECT * FROM account_year_facts WHERE tax_year = ? AND is_canonical = 1",
        (year,),
    ).fetchall()

    missing: list[str] = []
    matched_ids: set[int] = set()
    material_statuses: list[str] = []

    for asset in declared:
        if _is_immaterial(asset):
            conn.execute(
                "UPDATE declared_box3_assets SET coverage_status = ?, matched_fact_ids = ? WHERE id = ?",
                (CoverageStatus.COMPLETE.value, "[]", asset["id"]),
            )
            continue

        matches = _match_facts(asset, facts)
        status = CoverageStatus.MISSING.value
        if matches:
            usable = [f for f in matches if _fact_has_actual_return(f)]
            if usable:
                status = CoverageStatus.COMPLETE.value
                matched_ids.update(f["id"] for f in usable)
            else:
                status = CoverageStatus.PARTIAL.value
                matched_ids.update(f["id"] for f in matches)
                missing.append(f"{asset['institution']} {asset['account_id']} (no actual-return fields)")
        else:
            missing.append(f"{asset['institution']} {asset['account_id']} ({asset['label']})")

        material_statuses.append(status)
        conn.execute(
            "UPDATE declared_box3_assets SET coverage_status = ?, matched_fact_ids = ? WHERE id = ?",
            (status, json.dumps([f["id"] for f in matches]), asset["id"]),
        )

    used_facts = []
    for f in facts:
        if f["id"] not in matched_ids and declared:
            # still include unmatched non-pension facts in known totals? only if no declared inventory
            continue
        if _is_excluded_box3_fact(f):
            continue
        used_facts.append(f)
    if not declared:
        used_facts = [f for f in facts if not _is_excluded_box3_fact(f)]


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

    if not declared:
        coverage = CoverageStatus.UNKNOWN.value
        missing.append("no tax return Box 3 inventory for this year")
    elif any(s == CoverageStatus.MISSING.value for s in material_statuses):
        coverage = CoverageStatus.PARTIAL.value  # partnership incomplete
        # Use PARTIAL at portfolio level; recommend layer maps to INDETERMINATE
    elif any(s == CoverageStatus.PARTIAL.value for s in material_statuses):
        coverage = CoverageStatus.PARTIAL.value
    else:
        coverage = CoverageStatus.COMPLETE.value

    # Stricter: if any material MISSING, overall not COMPLETE
    if any(s == CoverageStatus.MISSING.value for s in material_statuses):
        coverage = "INCOMPLETE" if False else CoverageStatus.PARTIAL.value

    return CoverageResult(
        tax_year=year,
        coverage_status=coverage,
        # With a declared inventory, unmatched assets use the documented 0%
        # assumption. Without an inventory, completeness is unknowable.
        known_combined_actual_return=known_return if used_facts or declared else None,
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


def _is_immaterial(asset) -> bool:
    b1 = asset["balance_0101"] or 0
    b2 = asset["balance_3112"] or 0
    return abs(b1) < 1 and abs(b2) < 1


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


def _match_facts(asset, facts) -> list:
    target = normalize_account_id(asset["account_id"])
    target_iban = normalize_iban(asset["account_id"]) if re.search(r"[A-Za-z]{2}", asset["account_id"]) else ""
    out = []
    for f in facts:
        key = normalize_account_id(f["account_key"])
        if key == target or (target_iban and normalize_iban(f["account_key"]) == target_iban):
            out.append(f)
            continue
        # DEGIRO username match
        if asset["institution"] and asset["institution"].upper() == "DEGIRO":
            if target in key or key in target:
                out.append(f)
                continue
            if f["issuer"] == "degiro" and target in (f["account_label"] or "").lower():
                out.append(f)
                continue
        # Institution soft match when balances align (peildatum ≈ statement)
        if _balances_close(f, asset):
            inst = (asset["institution"] or "").lower()
            label = (f["account_label"] or "").lower()
            issuer = (f["issuer"] or "").lower()
            if inst and (inst in label or inst in issuer or _inst_alias(inst, issuer)):
                out.append(f)
                continue
            if issuer == "degiro" and asset["category"] == "investments":
                out.append(f)
                continue
    # flatex cash lines are included inside Degiro jaaroverzicht portfolio totals
    if not out and (asset["institution"] or "").lower().startswith("flatex"):
        degiro_facts = [f for f in facts if f["issuer"] == "degiro" and _fact_has_actual_return(f)]
        out.extend(degiro_facts)
    return out


def _inst_alias(inst: str, issuer: str) -> bool:
    aliases = {
        "revolut": {"revolut"},
        "raisin": {"raisin"},
        "sns": {"sns"},
        "ing": {"ing"},
        "rabobank": {"rabobank", "rabo"},
        "degiro": {"degiro"},
        "flatexdegiro": {"degiro", "flatex"},
        "flatex": {"degiro", "flatex"},
    }
    return issuer in aliases.get(inst, set())


def _balances_close(fact, asset, tol: float = 5.0) -> bool:
    pairs = (
        (fact["start_balance"], asset["balance_0101"]),
        (fact["end_balance"], asset["balance_3112"]),
    )
    hits = 0
    for a, b in pairs:
        if a is None or b is None:
            continue
        if abs(float(a) - float(b)) <= tol:
            hits += 1
    return hits >= 1


def _fact_has_actual_return(fact) -> bool:
    if fact["interest_received"] is not None or fact["interest_paid"] is not None:
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
