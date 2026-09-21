from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class Classification:
    issuer: str
    doc_type: str
    confidence: float = 1.0


def classify(text: str) -> Classification | None:
    """Classify PDF by content markers. Returns None if not relevant."""
    low = text.lower()

    # Tax returns embed bank names/IBANs — detect them before bank heuristics.
    if _is_aangifte(low):
        return Classification("belastingdienst", "aangifte_ib")

    if _is_degiro_jaaroverzicht(low):
        return Classification("degiro", "jaaroverzicht")

    if _is_flatex_tax_cert(low):
        return Classification("flatex", "belastingcertificaat")

    if _is_flatex_financial_instruments_statement(low):
        return Classification("flatex", "financial_instruments_statement")

    if _is_flatex_account_statement(low):
        return Classification("flatex", "account_statement")

    if _is_ing_jaaroverzicht(low):
        return Classification("ing", "jaaroverzicht")

    if _is_rabobank_jaaroverzicht(low):
        return Classification("rabobank", "jaaroverzicht")

    if _is_sns_totaaloverzicht(low):
        return Classification("sns", "totaaloverzicht")

    if _is_sns_jaaroverzicht(low):
        return Classification("sns", "jaaroverzicht")

    if _is_raisin(low):
        return Classification("raisin", "jaaroverzicht")

    if _is_revolut_annual(low):
        return Classification("revolut", "jaaroverzicht")

    if _is_revolut_savings(low):
        return Classification("revolut", "savings_statement")

    if _is_revolut_business_account_statement(low):
        return None

    if _is_revolut_account_statement(low):
        return Classification("revolut", "account_statement")

    return None


def _is_aangifte(low: str) -> bool:
    # Belastingdienst portal/print template.
    if (
        "aangifte inkomstenbelasting" in low
        and "eigen kopie, niet opsturen" in low
        and "burgerservicenummer" in low
        and "formulierenversie" in low
    ):
        return True
    if (
        "belastingdienst" in low
        and re.search(r"aanslag\s+20\d{2}", low)
        and "definitieve aanslag is vastgesteld overeenkomstig uw aangifte" in low
        and "inkomstenbelasting en premie volksverzekeringen" in low
    ):
        return True
    return False


def _is_degiro_jaaroverzicht(low: str) -> bool:
    return (
        ("degiro" in low or "flatexdegiro" in low)
        and ("jaaropgave" in low or "jaaroverzicht" in low)
        and "portefeuilleoverzicht per" in low
        and (
            "totale portefeuille waarde" in low
            or "totale portefeuillewaarde" in low
        )
    )


def _is_flatex_tax_cert(low: str) -> bool:
    return (
        "flatex" in low
        and "steuerbescheinigung" in low
        and "kunde:" in low
        and "kapitalerträge" in low
    )


def _is_flatex_financial_instruments_statement(low: str) -> bool:
    return (
        "flatex" in low
        and "lijst met financiële klanteninstrumenten en klantenfondsen" in low
        and "ingesloten vindt u de lijst voor 31.12." in low
        and "rekeningstand" in low
        and "effectenrekeningposities" in low
    )


def _is_flatex_account_statement(low: str) -> bool:
    return (
        "flatex" in low
        and "rekeninguittreksel nr:" in low
        and "rekeningnummer:" in low
        and "oud saldo van" in low
        and "nieuw saldo" in low
    )


def _is_ing_jaaroverzicht(low: str) -> bool:
    return (
        "ing" in low
        and bool(re.search(r"jaaroverzicht\s+20\d{2}", low))
        and "saldo op 01-01" in low
        and "saldo op 31-12" in low
        and any(
            marker in low
            for marker in ("ing betaalrekening", "ing oranje spaarrekening", "creditcards")
        )
    )


def _is_rabobank_jaaroverzicht(low: str) -> bool:
    return (
        "rabobank" in low
        and "financieel jaaroverzicht" in low
        and (
            bool(re.search(r"onderwerp\s+financieel jaaroverzicht", low))
            or "hierbij ontvangt u een financieel jaaroverzicht over het afgelopen jaar" in low
            or "dit is uw financieel jaaroverzicht van het afgelopen jaar" in low
        )
        and "saldo 01-01" in low
        and "saldo 31-12" in low
    )


def _is_sns_jaaroverzicht(low: str) -> bool:
    return (
        "sns bank" in low
        and (
            "jaaroverzicht betalen, sparen & lenen" in low
            or "financieel overzicht" in low
        )
        and "saldo" in low
        and "rente" in low
        and "1-1-" in low
    )


def _is_sns_totaaloverzicht(low: str) -> bool:
    return (
        "sns" in low
        and "totaaloverzicht rekeningen" in low
        and "rekeninghouder" in low
        and "saldo per 01-01" in low
        and "saldo per 31-12" in low
    )


def _is_raisin(low: str) -> bool:
    return (
        "raisin" in low
        and "raisin financieel jaaroverzicht" in low
        and "raisin spaarproduct" in low
        and "kenmerk:" in low
        and "omschrijving:" in low
        and "bronbelasting" in low
    )


def _is_revolut_annual(low: str) -> bool:
    return (
        "revolut" in low
        and bool(re.search(r"annual financial summary\s+20\d{2}", low))
        and "account number" in low
    )


def _is_revolut_savings(low: str) -> bool:
    return (
        "revolut" in low
        and "period jan 1" in low
        and "dec 31" in low
        and "account number" in low
        and "flexible cash funds" in low
        and "total earned return" in low
    )


def _is_revolut_account_statement(low: str) -> bool:
    return (
        "revolut" in low
        and "account (current account)" in low
        and bool(re.search(r"\b(?:eur|usd|gbp) statement\b", low))
        and re.search(
            r"(?:transactions|period)\s+from\s+january\s+1.*december\s+31",
            low,
            re.S,
        )
    )


def _is_revolut_business_account_statement(low: str) -> bool:
    return (
        "revolut business" in low
        and "account statement" in low
        and "balance summary" in low
    )


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
    for pat in patterns:
        m = re.search(pat, text, re.I)
        if m:
            year = int(m.group(1))
            if 2000 <= year <= 2100:
                return year
    head = text[:4000]
    years = [int(y) for y in re.findall(r"\b(20[1-2]\d)\b", head)]
    if years:
        return max(set(years), key=years.count)
    return None
