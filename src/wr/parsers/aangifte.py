from __future__ import annotations

import re

from wr.classify import guess_tax_year
from wr.models import ParseResult, TaxReturnData
from wr.pdf import parse_nl_amount


def parse_aangifte(text: str, tax_year: int | None = None) -> ParseResult:
    assessment_year = re.search(r"\bAanslag\s+(20\d{2})\b", text, re.I)
    year = int(assessment_year.group(1)) if assessment_year else tax_year or guess_tax_year(text)
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
    full_year = _has_full_year_fiscal_partners(text, year, partner_line is not None)

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
    if voordeel is None and re.search(
        r"Voordeel uit sparen en beleggen:.*?Forfaitair rendement\s+0,000%",
        text,
        re.I | re.S,
    ):
        voordeel = 0.0
    if voordeel is None:
        benefit_block = re.search(
            r"Voordeel uit sparen en beleggen:.*?(?=Belastbaar inkomen uit sparen en beleggen|\f|\Z)",
            text,
            re.I | re.S,
        )
        if benefit_block:
            components = [
                float(percent.replace(",", ".")) / 100 * parse_nl_amount(amount)
                for percent, amount in re.findall(
                    r"([\d,]+)%\s+van\s+€\s*([\d.]+)", benefit_block.group(0)
                )
                if parse_nl_amount(amount) is not None
            ]
            if components:
                voordeel = float(round(sum(components)))
    if voordeel is None:
        voordeel = _single_amount(
            text,
            rf"Uw gezamenlijk fictief rendement over\s+{year}\s+€?\s*([\d.]+)",
        )
    fictitious_parts = [
        parse_nl_amount(match.group(1))
        for match in re.finditer(
            r"Voordeel sparen en beleggen \(fictief\)\s+€?\s*([\d.]+)",
            text,
            re.I,
        )
    ]
    fictitious_parts = [amount for amount in fictitious_parts if amount is not None]
    if voordeel is None and fictitious_parts:
        voordeel = fictitious_parts[0]
    # Box 3 tax for filer
    box3_tax = None
    m = re.search(r"Box 3 belasting:.*?([\d.]+)\s*$", text, re.M)
    if not m:
        m = re.search(r"Totaal box 3 belasting\s+([\d.]+)", text)
    if not m:
        m = re.search(
            r"Inkomstenbelasting box 3\s*\n\s*€?\s*([\d.]+)",
            text,
            re.I,
        )
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
    if full_year and len(fictitious_parts) >= 2:
        tr.voordeel_b = fictitious_parts[1]
    if full_year and tr.partner_b_name:
        partner_voordeel, partner_box3_tax = _partner_box3_figures(text, tr.partner_b_name)
        if partner_voordeel is not None:
            tr.voordeel_b = partner_voordeel
        if partner_box3_tax is not None:
            tr.box3_tax_b = partner_box3_tax

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
    m = re.search(r"^\s*([A-Z][A-Z .'-]{3,80})\s+Aanslag\s+20\d{2}\b", text, re.M)
    if m:
        return m.group(1).strip()
    m = re.search(r"Naam\s+([^\n]+)", text)
    return m.group(1).strip() if m else None


def _has_full_year_fiscal_partners(text: str, year: int, has_partner_line: bool) -> bool:
    if has_partner_line or re.search(rf"heel\s+{year}\s+fiscale partners", text, re.I):
        return True
    same_address = re.search(
        rf"Stond u heel\s+{year}\s+ingeschreven op hetzelfde adres.*?\bJa\b",
        text,
        re.I | re.S,
    )
    if not same_address:
        return False
    qualifying_relationship = re.search(
        rf"(?:Had u in {year} een echtgenoot|Had u een notarieel samenlevingscontract|"
        r"Had u een kind samen|Heeft 1 van u een kind van de ander erkend|"
        r"Was u met .*? partners in een pensioenregeling|Was u samen met .*? eigenaar van de woning|"
        rf"Was .*? in {year - 1} uw fiscale partner)[^\n]*\bJa\b",
        text,
        re.I,
    )
    return qualifying_relationship is not None


def _name_matches(a: str, b: str) -> bool:
    def norm(s: str) -> str:
        return re.sub(r"[^a-z]", "", s.lower())

    na, nb = norm(a), norm(b)
    if not na or not nb:
        return False
    return na in nb or nb in na


def _partner_box3_figures(text: str, partner_name: str) -> tuple[float | None, float | None]:
    blocks = [text[match.start() : match.start() + 4000] for match in re.finditer(
        rf"(?:Deel|Grondslag)\s+{re.escape(partner_name)}\b", text, re.I
    )]
    block = next((block for block in reversed(blocks) if "sparen en beleggen" in block.lower()), None)
    if block is None:
        return None, None
    voordeel = _single_amount(
        block,
        r"Voordeel sparen en beleggen(?:\s*\([^)]*\))?\s+€?\s*([\d.]+)",
    )
    taxes = [
        parse_nl_amount(match.group(1))
        for match in re.finditer(
            r"Inkomstenbelasting box 3\s*\n\s*€?\s*([\d.]+)",
            block,
            re.I,
        )
    ]
    taxes = [tax for tax in taxes if tax is not None]
    return voordeel, taxes[-1] if taxes else None


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
