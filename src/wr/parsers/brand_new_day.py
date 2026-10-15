"""Brand New Day quarterly investment statements (native quarterly evidence)."""
from __future__ import annotations

import calendar
import re

from wr.models import AccountPeriodFact, ParseResult
from wr.parsers.base import ClassificationRule, InstitutionPlugin, ParserRegistration, simple_parser
from wr.pdf import parse_nl_amount
from wr.money import add, subtract


_PERIOD = r"Overzicht\s+([1-4])e\s+kwartaal\s+(20\d{2})"
_AMOUNT = r"€\s*(-?[\d.]+,\d{2})"


def _is_quarterly(text: str) -> bool:
    return ("brand new day" in text and "kwartaaloverzicht" in text
            and re.search(_PERIOD, text, re.I) is not None
            and re.search(r"\bBeleggingsrekening\s+NL\d{2}BNDA", text, re.I) is not None)


def parse_brand_new_day(text: str, tax_year: int | None = None) -> ParseResult:
    period = re.search(_PERIOD, text, re.I)
    account = re.search(r"\bBeleggingsrekening\s+(NL\d{2}BNDA[\d*X]+)", text, re.I)
    if period is None or account is None:
        raise ValueError("Missing Brand New Day quarter or investment account")
    quarter, year = int(period.group(1)), int(period.group(2))
    # Anchor to the Rendement table; Q4 also has an annual costs/return page.
    table = re.search(r"^\s*Rendement\s*$([\s\S]*?)^\s*Totaal([^\n]+)", text, re.I | re.M)
    amounts = re.findall(_AMOUNT, table.group(2)) if table else []
    if len(amounts) != 4:
        raise ValueError("Incomplete Brand New Day quarterly return totals")
    opening, net_flow, closing, earned = [parse_nl_amount(value) for value in amounts]
    if abs(subtract(closing, opening, net_flow, earned)) > 0.02:
        raise ValueError("Brand New Day quarterly totals do not reconcile")
    # The first bank-cost total belongs to this quarter. Q4's later annual
    # totals and indicative gross return (which includes fund-level costs)
    # must not replace the actual quarterly portfolio return.
    costs = re.search(r"^\s*Kosten Brand New Day Bank[ \t]+" + _AMOUNT, text, re.I | re.M)
    if costs is None:
        raise ValueError("Missing Brand New Day quarterly bank costs")
    bank_costs = parse_nl_amount(costs.group(1))
    holder = re.search(r"^(?:De heer|Mevrouw)\s+([^\n]+)", text, re.I | re.M)
    first_month, last_month = (quarter - 1) * 3 + 1, quarter * 3
    fact = AccountPeriodFact(
        tax_year=year, issuer="brand_new_day", account_key=account.group(1).upper(),
        account_label=f"Brand New Day Beleggingsrekening {account.group(1).upper()}",
        holder_names=[holder.group(1).strip()] if holder else [],
        ownership="individual" if holder else "unknown",
        period_start=f"{year}-{first_month:02d}-01",
        period_end=f"{year}-{last_month:02d}-{calendar.monthrange(year, last_month)[1]}",
        start_balance=opening, end_balance=closing,
        capital_gain=add(earned, bank_costs), gain_method="earned_return",
        extra={"quarter": quarter, "net_cashflow": net_flow,
               "reported_net_return": earned, "bank_costs": bank_costs,
               "return_basis": "quarterly net return plus separately charged bank costs", "box3": True},
    )
    return ParseResult("brand_new_day", "quarterly_statement", year, period_facts=[fact])


PLUGIN = InstitutionPlugin(
    issuer="brand_new_day",
    classification_rules=(ClassificationRule("brand_new_day", "quarterly_statement", _is_quarterly),),
    parsers={"quarterly_statement": ParserRegistration(simple_parser(parse_brand_new_day), 80)},
)
