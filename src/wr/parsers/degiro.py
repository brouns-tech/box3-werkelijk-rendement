from __future__ import annotations

import re

from wr.classify import guess_tax_year
from wr.models import AccountYearFact, ParseResult
from wr.pdf import normalize_account_id, parse_nl_amount


def parse_degiro(text: str, tax_year: int | None = None) -> ParseResult:
    year = tax_year or guess_tax_year(text) or _year_from_portefeuille(text)
    facts: list[AccountYearFact] = []
    notes: list[str] = []

    if year is None:
        return ParseResult("degiro", "jaaroverzicht", None, notes=["could not determine tax year"])

    # Pension accounts are typically Box 1 — keep fact but exclude from Box 3 logical group.
    is_pensioen = bool(re.search(r"pensioen", text, re.I)) and not re.search(
        r"DEGIRO Beleggingsrekening", text
    )
    # Filename/body often says "pensioen" explicitly on pension jaaropgave.
    if re.search(r"jaaropgave.*pensioen|pensioen.*jaaropgave|beleggingsrekening.*pensioen", text, re.I):
        is_pensioen = True
    # Heuristic: smaller dedicated pension docs still say DEGIRO; mark via common cue.
    if re.search(r"\bpensioen\b", text, re.I) and re.search(r"Account:\s*\*+", text):
        # If document title area mentions pensioen more than once, treat as pension.
        if len(re.findall(r"pensioen", text, re.I)) >= 1 and re.search(
                r"lijfrente|opeeuw|pensioenbelegg", text, re.I
        ):
            is_pensioen = True

    start = _find_amount(
        text, rf"Totale portefeuille\s*waarde per 1-1-{year}\s+([\d.]+,\d{{2}})"
    )
    end = _find_amount(
        text,
        rf"Totale portefeuille\s*waarde per 31-12-{year}\s+([\d.]+,\d{{2}})",
    )

    deposits = _find_amount(text, r"Totale waarde van stortingen\s*\*?\s+([\d.]+,\d{2})")
    withdrawals = _find_amount(text, r"Totale waarde van opnames\s*\*?\s+([\d.]+,\d{2})")
    dividends_gross = None
    div_section = re.search(
        r"Dividend in EUR.*?Totaal\s+([\d.]+,\d{2})\s+([\d.]+,\d{2})\s+([\d.]+,\d{2})",
        text,
        re.S,
    )
    withholding = None
    if div_section:
        dividends_gross = parse_nl_amount(div_section.group(1))
        withholding = parse_nl_amount(div_section.group(2))

    interest_received = _find_amount(text, r"Totaal ontvangen rente\s+([\d.]+,\d{2})")
    interest_paid = _find_amount(text, r"Totaal betaalde rente\s+([\d.]+,\d{2})")

    account_key = _account_key(text) or f"degiro-portfolio-{year}"
    if is_pensioen and not account_key.endswith("-pensioen"):
        account_key = f"{account_key}-pensioen"
        notes.append("classified as pensioen (excluded from Box 3 rollup)")

    holders = _holders(text)

    fact = AccountYearFact(
        tax_year=year,
        issuer="degiro",
        account_key=account_key,
        account_label=f"DEGIRO {'Pensioen' if is_pensioen else 'Beleggingsrekening'} {account_key}",
        holder_names=holders,
        ownership="unknown",
        start_balance=start,
        end_balance=end,
        deposits=deposits if deposits is not None else 0.0,
        withdrawals=withdrawals if withdrawals is not None else 0.0,
        interest_received=interest_received,
        interest_paid=interest_paid,
        dividends_gross=dividends_gross,
        withholding_tax=withholding,
        logical_group=None if is_pensioen else "flatex_degiro",
        extra=(
            {"box3": False}
            if is_pensioen
            else {"account_aliases": _account_aliases(text)}
        ),
    )
    fact.compute_capital_gain()
    facts.append(fact)

    if start is None or end is None:
        notes.append("missing portfolio totals")

    return ParseResult("degiro", "jaaroverzicht", year, facts=facts, notes=notes)


def _year_from_portefeuille(text: str) -> int | None:
    m = re.search(r"Portefeuilleoverzicht per 1-1-(20\d{2})", text)
    return int(m.group(1)) if m else None


def _find_amount(text: str, pattern: str) -> float | None:
    m = re.search(pattern, text, re.I)
    if not m:
        return None
    return parse_nl_amount(m.group(1))


def _account_key(text: str) -> str | None:
    # Prefer explicit username if present in document body / filename-like tokens.
    for pat in (
            r"\b(tEXAMPLE|SAMEXAMPLE|tsnEXAMPLE)\b",
            r"Account:\s*\*+(\w+)",
    ):
        m = re.search(pat, text, re.I)
        if m:
            token = m.group(1).lower()
            # Map masked ****mpl → tEXAMPLE when holder is EXAMPLE
            if token == "uns" and re.search(r"EXAMPLE", text):
                return "tEXAMPLE"
            if token == "sen" and re.search(r"EXAMPLE", text, re.I):
                return "SAMEXAMPLE"
            return token
    m = re.search(r"Dhr\.\s+([A-Z\s]+)\n", text)
    if m:
        parts = m.group(1).split()
        if parts:
            last = parts[-1].lower()
            if "EXAMPLE" in last:
                return "tEXAMPLE"
            if "EXAMPLE" in last:
                return "SAMEXAMPLE"
            return last[:12]
    return None


def _account_aliases(text: str) -> list[str]:
    """Identifiers printed for cash accounts belonging to this portfolio."""
    return list(
        dict.fromkeys(
            normalize_account_id(match)
            for match in re.findall(
                r"\b(?:EUR|USD|GBP)\s*\(([A-Z]{2}\d{18,})\)", text, re.I
            )
        )
    )


def _holders(text: str) -> list[str]:
    m = re.search(r"(?:Dhr\.|Hr|Mevr\.)\s+([A-Z][A-Za-z .]+EXAMPLE|[A-Z][A-Za-z .]+EXAMPLE)", text, re.I)
    if m:
        return [re.sub(r"\s+", " ", m.group(1)).strip()]
    m = re.search(r"(?:Dhr\.|Hr|Mevr\.)\s+([A-Z][A-Za-z .]{3,60})", text)
    if m:
        return [re.sub(r"\s+", " ", m.group(1)).strip()]
    return []
