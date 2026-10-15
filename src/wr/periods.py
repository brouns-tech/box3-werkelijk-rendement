"""Aggregate native reporting periods without modifying source evidence."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict
from datetime import date, timedelta
import json
import sqlite3

from wr.db import insert_facts
from wr.models import AccountPeriodFact, AccountYearFact
from wr.money import add, subtract, total
from wr.parsers import canonical_priority
from wr.notifications import FactNotification, NotificationType


def rebuild_year_facts(conn: sqlite3.Connection) -> None:
    """Rebuild annual candidates before ordinary canonical selection.

    Native annual evidence takes precedence over period-derived evidence for
    the same account/year. Exact duplicate periods are ranked by adapter
    priority and completeness. Overlaps are never added together: prefer the
    highest-priority, longest period and flag the unresolved overlap.
    """
    conn.execute("""DELETE FROM account_year_facts
        WHERE json_extract(extra, '$.period_aggregation') IS NOT NULL""")
    rows = conn.execute("""SELECT p.*, d.doc_type FROM account_period_facts p
        JOIN documents d ON d.content_sha256 = p.document_sha256
        WHERE d.parse_status = 'parsed' ORDER BY p.id""").fetchall()
    groups = defaultdict(list)
    earliest_reports = {}
    for row in rows:
        fact = AccountPeriodFact(**json.loads(row["payload"]))
        account = fact.account_key.lower().replace(" ", "")
        groups[(fact.tax_year, fact.issuer, account)].append((row, fact))
        key = fact.issuer, account
        earliest_reports[key] = min(earliest_reports.get(key, fact.period_start), fact.period_start)

    # Native annual evidence also establishes that the account existed earlier.
    # Generated summaries have already been removed, so they cannot influence
    # the assumption on subsequent recomputations.
    for row in conn.execute("""SELECT f.issuer, f.account_key, f.tax_year
        FROM account_year_facts f JOIN documents d ON d.content_sha256 = f.document_sha256
        WHERE d.parse_status = 'parsed'"""):
        key = row["issuer"], row["account_key"].lower().replace(" ", "")
        start = f"{row['tax_year']}-01-01"
        earliest_reports[key] = min(earliest_reports.get(key, start), start)

    for (year, issuer, account), items in groups.items():
        if conn.execute("""SELECT 1 FROM account_year_facts f
            JOIN documents d ON d.content_sha256 = f.document_sha256
            WHERE f.tax_year = ? AND f.issuer = ? AND lower(replace(f.account_key, ' ', '')) = ?
              AND d.parse_status = 'parsed'""", (year, issuer, account)).fetchone():
            continue
        currencies = {fact.currency for _, fact in items}
        if len(currencies) != 1:
            raise ValueError(f"Mixed currencies in period evidence: {issuer} {account} {year}")

        def rank(item):
            row, fact = item
            length = (date.fromisoformat(fact.period_end) - date.fromisoformat(fact.period_start)).days
            completeness = sum(getattr(fact, field) is not None for field in (
                "start_balance", "end_balance", "capital_gain", "deposits", "withdrawals",
                "interest_received", "dividends_gross",
            ))
            return canonical_priority(issuer, row["doc_type"]), length, completeness, -row["id"]

        selected = []
        seen = set()
        issues = []
        for row, fact in sorted(items, key=rank, reverse=True):
            period = fact.period_start, fact.period_end
            if period in seen:
                continue
            seen.add(period)
            if any(fact.period_start <= other.period_end and other.period_start <= fact.period_end
                   for _, other in selected):
                issues.append(f"overlapping period {fact.period_start}/{fact.period_end}")
                continue
            selected.append((row, fact))
        selected.sort(key=lambda item: item[1].period_start)
        first, last = selected[0][1], selected[-1][1]
        assume_opened_during_year = (
            first.period_start > f"{year}-01-01"
            and first.currency == "EUR"
            and first.start_balance == 0.0
            and earliest_reports[(issuer, account)] == first.period_start
        )
        notifications = []
        expected = date(year, 1, 1)
        previous = None
        for _, fact in selected:
            start = date.fromisoformat(fact.period_start)
            if start != expected:
                if previous is None and assume_opened_during_year:
                    notifications.append(FactNotification(
                        NotificationType.ASSUMPTION,
                        "account_opened_during_year",
                        {"period_start": expected.isoformat(),
                         "period_end": (start - timedelta(days=1)).isoformat(),
                         "first_report_start": fact.period_start,
                         "opening_balance": 0.0, "currency": "EUR"},
                    ))
                else:
                    issues.append(f"missing period {expected}/{start - timedelta(days=1)}")
            if (previous is not None and start == expected
                    and previous.end_balance is not None and fact.start_balance is not None
                    and abs(subtract(previous.end_balance, fact.start_balance)) > 0.01):
                issues.append(f"balance discontinuity at {fact.period_start}")
            expected = date.fromisoformat(fact.period_end) + timedelta(days=1)
            previous = fact
        if expected != date(year + 1, 1, 1):
            issues.append(f"missing period {expected}/{year}-12-31")

        facts = [fact for _, fact in selected]
        returns = [_period_return(fact) for fact in facts]
        if any(value is None for value in returns):
            issues.append("periods without actual-return fields")

        def summed(field):
            values = [getattr(fact, field) for fact in facts]
            return total(values) if all(value is not None for value in values) else None

        # Never present one period's numeric metadata as annual figures.
        # Full details remain in the immutable source payloads.
        extra = {key: first.extra[key] for key in ("box3", "asset_class", "return_basis")
                 if key in first.extra and all(fact.extra.get(key) == first.extra[key] for fact in facts)}
        if any(fact.extra.get("box3") is False for fact in facts):
            extra["box3"] = False
        if all("net_cashflow" in fact.extra for fact in facts):
            extra["net_cashflow"] = total(fact.extra["net_cashflow"] for fact in facts)
        if notifications:
            extra["notifications"] = [asdict(notification) for notification in notifications]
        extra["period_aggregation"] = {
            "complete": not issues,
            "issues": issues,
            "sources": [{"period_fact_id": row["id"], "document_sha256": row["document_sha256"],
                         "period_start": fact.period_start, "period_end": fact.period_end}
                        for row, fact in selected],
        }
        summary = AccountYearFact(
            tax_year=year, issuer=issuer, account_key=first.account_key,
            account_label=first.account_label,
            holder_names=sorted({name for fact in facts for name in fact.holder_names}),
            ownership=first.ownership, currency=first.currency,
            start_balance=first.start_balance
                if first.period_start == f"{year}-01-01" or assume_opened_during_year else None,
            end_balance=last.end_balance if last.period_end == f"{year}-12-31" else None,
            deposits=summed("deposits"), withdrawals=summed("withdrawals"),
            interest_received=summed("interest_received"), interest_paid=summed("interest_paid"),
            dividends_gross=summed("dividends_gross"), withholding_tax=summed("withholding_tax"),
            capital_gain=total(value for value in returns if value is not None)
                if any(value is not None for value in returns) else None,
            gain_method="earned_return", logical_group=first.logical_group, extra=extra,
        )
        insert_facts(conn, selected[0][0]["document_sha256"], [asdict(summary)])


def _period_return(fact: AccountPeriodFact) -> float | None:
    if fact.gain_method == "earned_return":
        return fact.capital_gain
    income = subtract(fact.interest_received or 0, fact.interest_paid or 0)
    if fact.gain_method == "interest_only":
        return income if fact.interest_received is not None or fact.interest_paid is not None else None
    if fact.capital_gain is None or fact.gain_method not in {"explicit", "balance_flow"}:
        return None
    return add(fact.capital_gain, income, fact.dividends_gross or 0)
