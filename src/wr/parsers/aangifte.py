from __future__ import annotations

import re

from wr.classify import guess_tax_year
from wr.models import DeclaredBox3Asset, ParseResult, TaxReturnData
from wr.pdf import normalize_account_id, normalize_iban, parse_nl_amount


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
    portal_full_year = bool(
        re.search(
            rf"Stond u heel\s+{year}\s+ingeschreven op hetzelfde adres[^?]*\?\s+Ja\b",
            text,
            re.I,
        )
    )
    full_year = partner_line is not None or portal_full_year or bool(
        re.search(rf"heel\s+{year}\s+fiscale partners", text, re.I)
    )

    partner_a = None
    partner_b = None
    # Partner block
    m = re.search(r"Partner\s*\nNaam\s+([^\n]+)", text)
    if m:
        partner_b = m.group(1).strip()
    if partner_b is None:
        m = re.search(r"Naam (?:echtgenoot|partner)\s+([A-Z][A-Z .'-]+?)\s*$", text, re.M)
        if m:
            partner_b = m.group(1).strip()
    m = re.search(r"Naam\s+(T\.S\.N\.\s*EXAMPLE|E\.J\.M\.\s*EXAMPLE|[^\n]+)\n", text)
    if filer:
        partner_a = filer
    if partner_line:
        # "A. EXAMPLE en de echtgenote"
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
        r"^Waarde van bezittingen[^\S\n]+([\d.]+)[^\S\n]+([\d.]+)[^\S\n]*$",
        text,
        re.M,
    )
    if m:
        bezittingen_0101 = parse_nl_amount(m.group(1))
        bezittingen_3112 = parse_nl_amount(m.group(2))

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

    grondslag = _single_amount(text, r"Grondslag sparen en beleggen\s+([\d.]+)")

    portal_allocation = re.search(
        r"Grondslag voordeel uit sparen en beleggen\s+"
        r"€?\s*([\d.]+)\s+€?\s*([\d.]+)\s+€?\s*([\d.]+)",
        text,
        re.I,
    )
    if portal_allocation:
        grondslag = parse_nl_amount(portal_allocation.group(1))

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
            # In EXAMPLE return, EXAMPLE line is "-98.913" meaning 98913 allocated to partner
            val = parse_nl_amount(raw_line.group(1).lstrip("-")) or val

        if _name_matches(name, filer):
            grondslag_a = val
            name_a = name
        else:
            grondslag_b = val
            name_b = name

    if portal_allocation:
        grondslag_a = parse_nl_amount(portal_allocation.group(2))
        grondslag_b = parse_nl_amount(portal_allocation.group(3))
        name_a = filer or partner_a
        name_b = partner_b

    # If filer is EXAMPLE, first/second based on matching
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

    voordeel = _single_amount(
        text, r"Voordeel uit sparen en beleggen\s+([\d.]+)"
    )
    joint_fictitious = _single_amount(
        text, rf"Uw gezamenlijk fictief rendement over\s+{year}\s+€?\s*([\d.]+)"
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

    assets = _parse_assets(text, year)
    if bezittingen_0101 is None and assets:
        bezittingen_0101 = sum(a.balance_0101 or 0.0 for a in assets)
    if bezittingen_3112 is None and assets and all(a.balance_3112 is not None for a in assets):
        bezittingen_3112 = sum(a.balance_3112 or 0.0 for a in assets)

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
        assets=assets,
        allocation_status=allocation_status,
    )

    if joint_fictitious is not None:
        if tr.allocation_a is not None:
            tr.voordeel_a = joint_fictitious * tr.allocation_a
        if tr.allocation_b is not None:
            tr.voordeel_b = joint_fictitious * tr.allocation_b

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


def _parse_assets(text: str, year: int) -> list[DeclaredBox3Asset]:
    assets: list[DeclaredBox3Asset] = _parse_portal_assets(text, year)

    # Dutch bank rows: Bank ... Rekeningnummer ... amounts
    # Rabobank Rabo SpaarRekening             NL34.RABO.1131.1183.83               203.629          60.777
    nl_bank = re.compile(
        r"(?P<label>(?:Rabobank|SNS|ING|Knab|ABN|bunq|Revolut|MAIN_POCKETS)[^\n]*?)\s+"
        r"(?P<iban>NL\d{2}[\.A-Z0-9]+)\s+"
        r"(?P<s>[\d.]+)\s+(?P<e>[\d.]+)",
        re.I,
    )
    for m in nl_bank.finditer(text):
        iban = normalize_iban(m.group("iban"))
        label = re.sub(r"\s+", " ", m.group("label")).strip()
        if re.search(r"fiscaal begin|fiscaal eind", label, re.I):
            continue
        inst = label.split()[0]
        if label.upper().startswith("MAIN_POCKETS"):
            inst = "Revolut"
        if "KNAB" in iban.upper():
            inst = "Knab"
        assets.append(
            DeclaredBox3Asset(
                tax_year=year,
                category="bank_nl",
                institution=inst,
                account_id=iban,
                label=label,
                balance_0101=parse_nl_amount(m.group("s")),
                balance_3112=parse_nl_amount(m.group("e")),
            )
        )

    # Foreign banks / Raisin / flatex cash / Revolut securities UUIDs
    # Raisin Banca Progetto ... IT27Q05015...
    foreign_iban = re.compile(
        r"(?P<label>(?:Raisin|flatexDEGIRO|eToro|Revolut)[^\n]{0,80}?)\s+"
        r"(?P<acct>(?:IT|DE|LT)[A-Z0-9]{10,}|(?:[0-9a-f]{20,})|\d{6,})\s+"
        r"(?P<s>[\d.]+)\s+(?P<e>[\d.]+)",
        re.I,
    )
    # Simpler: scan IBAN-like and uuid-like with trailing two amounts
    for m in re.finditer(
        r"(?P<acct>IT[A-Z0-9]{20,}|DE\d{18,}|NL\d{2}REVO\d+|[0-9a-f]{28,}|1\d{9})\s+"
        r"(?P<s>[\d.]+)\s+(?P<e>[\d.]+)",
        text,
        re.I,
    ):
        acct = normalize_account_id(m.group("acct"))
        if any(a.account_id == acct or normalize_iban(a.account_id) == normalize_iban(acct) for a in assets):
            continue
        # Context window for institution
        start = max(0, m.start() - 120)
        ctx = text[start : m.start()]
        if re.search(r"Raisin", ctx, re.I):
            inst, cat, label = "Raisin", "bank_foreign", "Raisin deposit"
        elif re.search(r"flatex", ctx, re.I):
            inst, cat, label = "flatexDEGIRO", "bank_foreign", "flatex cash"
        elif re.search(r"eToro", ctx, re.I):
            inst, cat, label = "eToro", "bank_foreign", "eToro"
        elif re.search(r"Revolut", ctx, re.I) or re.fullmatch(r"[0-9a-f]{28,}", acct):
            inst, cat, label = "Revolut", "bank_foreign", "Revolut Securities"
        else:
            inst, cat, label = "foreign", "bank_foreign", "Foreign account"
        assets.append(
            DeclaredBox3Asset(
                tax_year=year,
                category=cat,
                institution=inst,
                account_id=acct,
                label=label,
                balance_0101=parse_nl_amount(m.group("s")),
                balance_3112=parse_nl_amount(m.group("e")),
            )
        )

    # Investments / DEGIRO
    for m in re.finditer(
        r"DEGIRO Beleggingsrekening\s+(\S+)\s+([\d.]+)\s+([\d.]+)",
        text,
        re.I,
    ):
        assets.append(
            DeclaredBox3Asset(
                tax_year=year,
                category="investments",
                institution="DEGIRO",
                account_id=m.group(1).lower(),
                label=f"DEGIRO Beleggingsrekening {m.group(1)}",
                balance_0101=parse_nl_amount(m.group(2)),
                balance_3112=parse_nl_amount(m.group(3)),
            )
        )

    return _dedupe_assets(assets)


def _parse_portal_assets(text: str, year: int) -> list[DeclaredBox3Asset]:
    """Parse Belastingdienst portal blocks that report the 1 January value."""
    assets: list[DeclaredBox3Asset] = []
    blocks = re.compile(
        r"^(?P<kind>Bankrekening|Belegging):\s*(?P<header>[^\n]+?):\s*"
        r"€\s*(?P<amount>[\d.]+)\s*$\n"
        r"(?P<body>.*?)(?=^(?:Bankrekening|Belegging):|\Z)",
        re.I | re.M | re.S,
    )
    for match in blocks.finditer(text):
        kind = match.group("kind").lower()
        header = match.group("header").strip()
        body = match.group("body")
        business_answer = re.search(
            r"Was (?:het|deze).*?zakelijk(?:e)?\s+(?:rekening|belegging)\?\s+(Ja|Nee)\b",
            body,
            re.I | re.S,
        )
        if business_answer and business_answer.group(1).lower() == "ja":
            continue

        balance = parse_nl_amount(match.group("amount"))
        if kind == "bankrekening":
            iban_match = re.search(
                r"IBAN \(rekeningnummer\)\s+(.+?)(?=\n\s*Saldo op)",
                body,
                re.I | re.S,
            )
            if not iban_match:
                continue
            account_id = normalize_iban(iban_match.group(1))
            if not re.fullmatch(r"[A-Z]{2}\d{2}[A-Z0-9]{10,30}", account_id):
                continue
            label_match = re.search(r"Naam bankrekening\s+([^\n]+)", body, re.I)
            label = label_match.group(1).strip() if label_match else header
            institution = _bank_institution(label, account_id)
            category = "bank_nl" if account_id.startswith("NL") else "bank_foreign"
        else:
            number_match = re.search(r"^\s*Nummer\s+([^\n]+)", body, re.I | re.M)
            if not number_match:
                continue
            account_id = normalize_account_id(number_match.group(1))
            description_match = re.search(r"^\s*Omschrijving\s+([^\n]+)", body, re.I | re.M)
            description = description_match.group(1).strip() if description_match else header
            institution = "DEGIRO" if "degiro" in f"{header} {description}".lower() else description.split()[0]
            label = f"{institution} Beleggingsrekening {account_id}"
            category = "investments"

        assets.append(
            DeclaredBox3Asset(
                tax_year=year,
                category=category,
                institution=institution,
                account_id=account_id,
                label=label,
                balance_0101=balance,
            )
        )
    return assets


def _bank_institution(label: str, iban: str) -> str:
    bank_code = iban[4:8] if iban.startswith("NL") and len(iban) >= 8 else ""
    by_code = {
        "INGB": "ING",
        "KNAB": "Knab",
        "RABO": "Rabobank",
        "REVO": "Revolut",
        "SNSB": "SNS",
    }
    if bank_code in by_code:
        return by_code[bank_code]
    if iban.startswith("IT") and "banca progetto" in label.lower():
        return "Raisin"
    return label.split()[0]


def _dedupe_assets(assets: list[DeclaredBox3Asset]) -> list[DeclaredBox3Asset]:
    seen: set[str] = set()
    out: list[DeclaredBox3Asset] = []
    for a in assets:
        key = f"{a.category}:{normalize_account_id(a.account_id)}"
        if key in seen:
            continue
        seen.add(key)
        out.append(a)
    return out


def _filer_name(text: str) -> str | None:
    m = re.search(
        r"Fiscaal rapport aangifte inkomstenbelasting\s+20\d{2}\s+van\s+(?:de heer|mevrouw)\s+([A-Z][A-Za-z .]+?)(?:\s+Datum|\s*$)",
        text,
        re.I | re.M,
    )
    if m:
        return m.group(1).strip()
    m = re.search(r"^Persoonlijke gegevens van\s+([A-Z][A-Z .'-]+?)\s*$", text, re.M)
    if m:
        return m.group(1).strip()
    m = re.search(r"Naam\s+(T\.S\.N\.\s*EXAMPLE|E\.J\.M\.\s*EXAMPLE)", text)
    return m.group(1).strip() if m else None


def _name_matches(a: str, b: str) -> bool:
    def norm(s: str) -> str:
        return re.sub(r"[^a-z]", "", s.lower())

    na, nb = norm(a), norm(b)
    if not na or not nb:
        return False
    return na in nb or nb in na or ("EXAMPLE" in na and "EXAMPLE" in nb) or ("EXAMPLE" in na and "EXAMPLE" in nb)


def _single_amount(text: str, pattern: str) -> float | None:
    m = re.search(pattern, text)
    return parse_nl_amount(m.group(1)) if m else None


def _amount_after(text: str, label: str) -> float | None:
    m = re.search(rf"{re.escape(label)}\s+([\d.]+)", text)
    return parse_nl_amount(m.group(1)) if m else None
