from __future__ import annotations

import re

from wr.classify import guess_tax_year
from wr.models import ParseResult, TaxReturnData
from wr.pdf import parse_nl_amount


def parse_aangifte(text: str, tax_year: int | None = None) -> ParseResult:
    year = tax_year or guess_tax_year(text)
    if year is None:
        m = re.search(r"inkomstenbelasting\s+(20\d{2})", text, re.I)
        year = int(m.group(1)) if m else None
    if year is None:
        return ParseResult("belastingdienst", "aangifte_ib", None, notes=["no year"])

    filer = _filer_name(text)
    partner_line = re.search(
        rf"([^\n]+)\s+en\s+(?:de echtgenote|de echtgenoot|partner)\s+zijn\s+heel\s+{year}\s+fiscale partners",
        text,
        re.I,
    )
    full_year = partner_line is not None or bool(
        re.search(rf"heel\s+{year}\s+fiscale partners", text, re.I)
    )

    partner_a = None
    partner_b = None
    # Partner block
    m = re.search(r"Partner\s*\nNaam\s+([^\n]+)", text)
    if m:
        partner_b = m.group(1).strip()
    m = re.search(r"Naam echtgenoot\s+([^\n]+)", text, re.I)
    if m:
        partner_b = m.group(1).strip()
    if filer:
        partner_a = filer
    if partner_line:
        partner_a = partner_line.group(1).strip()

    # Totals
    bez = re.search(
        r"Totaal waarde bezittingen\s+([\d.]+)\s+([\d.]+)",
        text,
    )
    # sometimes with thousands separators 318.895
    if not bez:
        bez = re.search(
            r"Totaal waarde bezittingen\s+([\d.]+(?:,\d{2})?)\s+([\d.]+(?:,\d{2})?)",
            text,
        )

    bezittingen_0101 = parse_nl_amount(bez.group(1)) if bez else _amount_after(text, "Waarde van bezittingen")
    bezittingen_3112 = parse_nl_amount(bez.group(2)) if bez else None

    # Prefer explicit lines under rendementsgrondslag
    m = re.search(
        r"Waarde van bezittingen\s+([\d.]+)\s+([\d.]+)",
        text,
    )
    if m:
        bezittingen_0101 = parse_nl_amount(m.group(1))
        bezittingen_3112 = parse_nl_amount(m.group(2))

    if bezittingen_0101 is None:
        bezittingen_0101 = _official_box3_assets_at_0101(text)

    schulden_0101 = None
    schulden_3112 = None
    m = re.search(r"Aftrekbare schulden\s+([\d.]+)\s+([\d.]+)", text)
    if m:
        schulden_0101 = parse_nl_amount(m.group(1))
        schulden_3112 = parse_nl_amount(m.group(2))

    heffingsvrij = _single_amount(text, r"Heffingsvrij vermogen\s+(?:-)?([\d.]+)")
    if heffingsvrij is not None and re.search(r"Heffingsvrij vermogen\s+-", text):
        # stored as positive allowance magnitude
        pass

    grondslag = _single_amount(
        text, r"Grondslag sparen en beleggen\s+(?:€\s*)?([\d.]+)"
    )

    # Allocation — order of names varies by filer
    grondslag_parts = re.findall(
        r"Deel van de grondslag van\s+([^\n]+?)\s+(-?[\d.]+)",
        text,
    )
    grondslag_a = None
    grondslag_b = None
    name_a = partner_a
    name_b = partner_b
    for name, amt in grondslag_parts:
        name = name.strip()
        val = parse_nl_amount(amt)
        if val is None:
            continue
        val = abs(val)  # PDF shows partner share with leading minus as formatting
        # Detect sign from original: "-98.913" means allocation amount 98913
        raw_line = re.search(
            rf"Deel van de grondslag van\s+{re.escape(name)}\s+(-?[\d.]+)",
            text,
        )
        if raw_line and raw_line.group(1).startswith("-"):
            val = parse_nl_amount(raw_line.group(1).lstrip("-")) or val

        if _name_matches(name, filer):
            grondslag_a = val
            name_a = name
        else:
            grondslag_b = val
            name_b = name

    if grondslag_a is None and len(grondslag_parts) >= 1:
        # Fallback: larger of remaining
        vals = []
        for name, amt in grondslag_parts:
            raw = re.search(
                rf"Deel van de grondslag van\s+{re.escape(name.strip())}\s+(-?[\d.]+)",
                text,
            )
            if not raw:
                continue
            v = parse_nl_amount(raw.group(1).lstrip("-"))
            vals.append((name.strip(), v))
        if len(vals) == 2:
            # Identify filer
            for name, v in vals:
                if _name_matches(name, filer):
                    grondslag_a = v
                    name_a = name
                else:
                    grondslag_b = v
                    name_b = name

    if grondslag_a is None:
        uw_deel = _single_amount(text, r"Uw deel\s+(?:€\s*)?([\d.]+)")
        if uw_deel is not None:
            grondslag_a = uw_deel

    if grondslag_b is None and partner_b:
        partner_part = re.search(
            rf"Deel\s+{re.escape(partner_b)}\s+(?:€\s*)?([\d.]+)",
            text,
            re.I,
        )
        if partner_part:
            grondslag_b = parse_nl_amount(partner_part.group(1))

    voordeel = _single_amount(
        text, r"Voordeel uit sparen en beleggen\s+(?:€\s*)?([\d.]+)"
    )
    # Box 3 tax for filer
    box3_tax = None
    m = re.search(r"Box 3 belasting:.*?([\d.]+)\s*$", text, re.M)
    if not m:
        m = re.search(r"Totaal box 3 belasting\s+([\d.]+)", text)
    if m:
        box3_tax = parse_nl_amount(m.group(1))

    allocation_status = "ok"
    if grondslag == 0:
        allocation_status = "ZERO_BASE"
    elif grondslag_a is None or (full_year and grondslag_b is None):
        allocation_status = "incomplete"

    tr = TaxReturnData(
        tax_year=year,
        filer_name=filer or "unknown",
        full_year_fiscal_partners=full_year,
        partner_a_name=name_a or partner_a,
        partner_b_name=name_b or partner_b,
        bezittingen_0101=bezittingen_0101,
        bezittingen_3112=bezittingen_3112,
        schulden_0101=schulden_0101,
        schulden_3112=schulden_3112,
        heffingsvrij_vermogen=heffingsvrij,
        grondslag=grondslag,
        grondslag_a=grondslag_a,
        grondslag_b=grondslag_b,
        voordeel_a=voordeel if _name_matches(filer or "", name_a or "") else None,
        voordeel_b=None,
        box3_tax_a=box3_tax,
        allocation_status=allocation_status,
    )

    # If we only have filer's voordeel, store it on the matching partner slot
    if voordeel is not None:
        if _name_matches(filer or "", tr.partner_a_name or ""):
            tr.voordeel_a = voordeel
        elif _name_matches(filer or "", tr.partner_b_name or ""):
            tr.voordeel_b = voordeel
        else:
            tr.voordeel_a = voordeel

    return ParseResult(
        issuer="belastingdienst",
        doc_type="aangifte_ib",
        tax_year=year,
        tax_return=tr,
    )


def _filer_name(text: str) -> str | None:
    m = re.search(
        r"Persoonlijke gegevens van\s+([A-Z][A-Z ]+)", text, re.I
    )
    if m:
        return m.group(1).strip()
    m = re.search(r"Naam\s+([^\n]+)", text)
    return m.group(1).strip() if m else None


def _name_matches(a: str, b: str) -> bool:
    def norm(s: str) -> str:
        return re.sub(r"[^a-z]", "", s.lower())

    na, nb = norm(a), norm(b)
    if not na or not nb:
        return False
    return na in nb or nb in na


def _single_amount(text: str, pattern: str) -> float | None:
    m = re.search(pattern, text)
    return parse_nl_amount(m.group(1)) if m else None


def _amount_after(text: str, label: str) -> float | None:
    m = re.search(rf"{re.escape(label)}\s+([\d.]+)", text)
    return parse_nl_amount(m.group(1)) if m else None


def _official_box3_assets_at_0101(text: str) -> float | None:
    """Return the aggregate Box 3 assets from an official return printout.

    The official form shows Box 3 assets at one tax point only: 1 January.
    It does not provide a 31 December aggregate, so this deliberately does not
    populate ``bezittingen_3112``.
    """
    m = re.search(
        r"Bankrekeningen in box 3\s+€\s*([\d.]+).*?"
        r"Beleggingen in box 3\s+€\s*([\d.]+)",
        text,
        re.I | re.S,
    )
    if not m:
        return None

    bank_accounts = parse_nl_amount(m.group(1))
    investments = parse_nl_amount(m.group(2))
    if bank_accounts is None or investments is None:
        return None
    return bank_accounts + investments
