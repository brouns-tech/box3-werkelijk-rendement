from __future__ import annotations

import re
from typing import Callable

from wr.classify import guess_tax_year
from wr.pdf import parse_nl_amount


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
