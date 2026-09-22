from __future__ import annotations

import re
from typing import Callable

from wr.pdf import parse_nl_amount


def guess_tax_year(text: str, doc_type: str | None = None) -> int | None:
    patterns = [
        r"[Jj]aaroverzicht\s+(20\d{2})",
        r"[Jj]aaropgave\s+(20\d{2})",
        r"Financieel [Jj]aaroverzicht\s+(20\d{2})",
        r"Annual Financial Summary\s+(20\d{2})",
        r"Financieel overzicht\s+(20\d{2})",
        r"Totaaloverzicht Rekeningen\s+(20\d{2})",
        r"aangifte inkomstenbelasting\s+(20\d{2})",
        r"inkomstenbelasting\s+(20\d{2})",
        r"heel\s+(20\d{2})\s+fiscale partners",
        r"01\.01\.(20\d{2})",
        r"01-01-(20\d{2})",
        r"1/1/(20\d{2})",
        r"Period\s+Jan\s+1,\s+(20\d{2})",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.I)
        if match:
            year = int(match.group(1))
            if 2000 <= year <= 2100:
                return year
    head = text[:4000]
    years = [int(year) for year in re.findall(r"\b(20[1-2]\d)\b", head)]
    return max(set(years), key=years.count) if years else None


def resolve_tax_year(text: str, explicit_year: int | None) -> int | None:
    return explicit_year if explicit_year is not None else guess_tax_year(text)


def amount_after_label(
    text: str,
    label: str,
    parser: Callable[[str], float | None] = parse_nl_amount,
) -> float | None:
    flexible_label = r"\s*".join(re.escape(character) for character in label)
    match = re.search(rf"{flexible_label}\s*:?\s*(-?[\d\s.,]+)", text, re.I)
    return parser(match.group(1).replace(" ", "")) if match else None


def first_holder(text: str, pattern: str) -> list[str]:
    match = re.search(pattern, text, re.I)
    return [match.group(1).strip()] if match else []
