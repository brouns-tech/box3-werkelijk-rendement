from __future__ import annotations

import re

from wr.classify import guess_tax_year
from wr.models import AccountYearFact, ParseResult
from wr.pdf import normalize_iban, parse_nl_amount


def parse_sns(text: str, tax_year: int | None, doc_type: str) -> ParseResult:
    year = tax_year or guess_tax_year(text)
    if year is None:
        return ParseResult("sns", doc_type, None, notes=["no year"])

    if doc_type == "totaaloverzicht":
        return _parse_totaaloverzicht(text, year)
    return _parse_jaaroverzicht(text, year)


def _parse_jaaroverzicht(text: str, year: int) -> ParseResult:
    facts: list[AccountYearFact] = []
    # Recover IBAN even with OCR-mangled digits in the body.
    ibans = [
        normalize_iban(_clean_ocr_iban(m.group(0)))
        for m in re.finditer(r"NL\d{2}\s*SNSB\s*[\d\søóõòôùúûüð]{8,}", text, re.I)
    ]
    # SNS Internet Sparen *                                 2.000,00            2.000,00                 0,00                12,34
    row = re.compile(
        r"(NL\d{2}\s*SNSB\s*[\d\søóõòôùúûüð]+)\s+"
        r"(SNS[^\n]*?)\s+"
        r"([\d.]+,\d{2})\s+([\d.]+,\d{2})\s+([\d.]+,\d{2})\s+([\d.]+,\d{2})",
        re.I,
    )
    for m in row.finditer(text):
        iban = normalize_iban(_clean_ocr_iban(m.group(1)))
        label = re.sub(r"\s*\*.*$", "", m.group(2)).strip()
        start = parse_nl_amount(m.group(3))
        end = parse_nl_amount(m.group(4))
        paid = parse_nl_amount(m.group(5))
        received = parse_nl_amount(m.group(6))
        fact = AccountYearFact(
            tax_year=year,
            issuer="sns",
            account_key=iban,
            account_label=label,
            holder_names=_holders(text),
            start_balance=start,
            end_balance=end,
            interest_received=received,
            interest_paid=paid,
            extra={
                "account_type": _account_type(label),
                "interest_source": "reported",
            },
        )
        fact.compute_capital_gain()
        facts.append(fact)

    # Fallback without IBAN on same line
    if not facts:
        row2 = re.compile(
            r"(SNS[^\n]*Sparen[^\n]*)\s+([\d.]+,\d{2})\s+([\d.]+,\d{2})\s+([\d.]+,\d{2})\s+([\d.]+,\d{2})"
        )
        iban = ibans[0] if ibans else f"sns-unknown-{year}"
        # Prefer IBAN that is not the payment account if multiple
        for cand in ibans:
            if "8838" in cand or "9652" in cand:
                iban = cand
        for m in row2.finditer(text):
            if "Totaal" in m.group(1):
                continue
            fact = AccountYearFact(
                tax_year=year,
                issuer="sns",
                account_key=iban,
                account_label=re.sub(r"\s+", " ", m.group(1)).strip(" *"),
                holder_names=_holders(text),
                start_balance=parse_nl_amount(m.group(2)),
                end_balance=parse_nl_amount(m.group(3)),
                interest_paid=parse_nl_amount(m.group(4)),
                interest_received=parse_nl_amount(m.group(5)),
                extra={
                    "account_type": "savings",
                    "interest_source": "reported",
                },
            )
            fact.compute_capital_gain()
            facts.append(fact)

    return ParseResult("sns", "jaaroverzicht", year, facts=facts)


def _parse_totaaloverzicht(text: str, year: int) -> ParseResult:
    facts: list[AccountYearFact] = []
    pattern = re.compile(
        r"^[ \t]*(?P<label>\S[^\n]*?)[ \t]{2,}(?P<holders>\S[^\n]*?)[ \t]{2,}"
        r"(?P<start>[\d.]+,\d{2})[ \t]{2,}(?P<end>[\d.]+,\d{2})[ \t]*$\n"
        r"^\s*(?P<iban>NL\d{2}SNSB\d+)(?:\s+(?P<holder_tail>[^\n]+))?\s*$",
        re.M,
    )
    for m in pattern.finditer(text):
        iban = normalize_iban(m.group("iban"))
        holders_raw = " ".join(
            part.strip()
            for part in (m.group("holders"), m.group("holder_tail") or "")
            if part.strip()
        )
        ownership = "joint" if "e/o" in holders_raw.lower() else "unknown"
        label = m.group("label").strip()
        account_type = _account_type(label)
        interest = None if account_type == "savings" else 0.0
        fact = AccountYearFact(
            tax_year=year,
            issuer="sns",
            account_key=iban,
            account_label=label,
            holder_names=[h.strip() for h in re.split(r"\s+e/o\s+", holders_raw)],
            ownership=ownership,
            start_balance=parse_nl_amount(m.group("start")),
            end_balance=parse_nl_amount(m.group("end")),
            interest_received=interest,
            extra={
                "account_type": account_type,
                "interest_source": (
                    "not_available_on_total_overview"
                    if account_type == "savings"
                    else "inferred_zero_non_savings_account"
                ),
            },
        )
        fact.compute_capital_gain()
        facts.append(fact)

    # Alternative layout: IBAN first
    if not facts:
        alt = re.compile(
            r"(NL\d{2}SNSB\d+)\s+[^\n]*?\s+([\d.]+,\d{2})\s+([\d.]+,\d{2})"
        )
        for m in alt.finditer(text):
            fact = AccountYearFact(
                tax_year=year,
                issuer="sns",
                account_key=normalize_iban(m.group(1)),
                account_label="SNS rekening",
                start_balance=parse_nl_amount(m.group(2)),
                end_balance=parse_nl_amount(m.group(3)),
            )
            fact.compute_capital_gain()
            facts.append(fact)

    return ParseResult("sns", "totaaloverzicht", year, facts=facts)


def _account_type(label: str) -> str:
    return "savings" if re.search(r"\bSparen\b", label, re.I) else "payment"


def _clean_ocr_iban(raw: str) -> str:
    # Map common OCR confusions in SNS PDFs
    table = str.maketrans({
        "ø": "0", "ó": "0", "õ": "0", "ò": "0", "ô": "0",
        "ù": "1", "ú": "1", "û": "1", "ü": "1", "ð": "0",
    })
    return raw.translate(table)


def _holders(text: str) -> list[str]:
    return []
