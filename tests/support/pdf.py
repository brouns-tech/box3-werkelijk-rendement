"""Synthetic PDF fixtures shared by parser and integration tests."""
from __future__ import annotations

from pathlib import Path


ING_TEXT = """ING Jaaroverzicht 2024
ING Oranje Spaarrekening: H 000-00000 Hr ALEX EXAMPLE
Saldo op 01-01-2024 1.000,00
Saldo op 31-12-2024 1.012,34
Rente, ontvangen in 2024 12,34
"""


def synthetic_pdf(path: Path, text: str = ING_TEXT) -> None:
    from pypdf import PdfWriter
    from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject
    writer = PdfWriter()
    page = writer.add_blank_page(width=900, height=900)
    font = DictionaryObject({NameObject("/Type"): NameObject("/Font"),
                             NameObject("/Subtype"): NameObject("/Type1"),
                             NameObject("/Encoding"): NameObject("/WinAnsiEncoding"),
                             NameObject("/BaseFont"): NameObject("/Courier")})
    page[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)})})
    lines = ["BT /F1 10 Tf 20 850 Td 14 TL"]
    for line in text.splitlines():
        escaped = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        lines.append(f"({escaped}) Tj T*")
    lines.append("ET")
    stream = DecodedStreamObject()
    stream.set_data("\n".join(lines).encode("cp1252"))
    page[NameObject("/Contents")] = writer._add_object(stream)
    writer.write(path)


SAMPLES = {
    "ing": ING_TEXT,
    "rabobank": """Example User
Onderwerp Financieel Jaaroverzicht 2024
Rabobank
Sparen
NL00 RABO 0000 0000 02 EUR Rabo SpaarRekening
Saldo 01-01-2024 20.000,00 C
Saldo 31-12-2024 21.000,00 C
Door u ontvangen rente in 2024 200,00
""",
    "sns": """Totaaloverzicht Rekeningen 2024
Rekening Rekeninghouder Saldo per 01-01-2024 Saldo per 31-12-2024
Shared checking                 ALEX EXAMPLE e/o SAM EXAMPLE       1.000,00      900,00
NL00SNSB0000000000               EXAMPLE
""",
    "raisin": """Raisin Financieel Jaaroverzicht 2024
Naam: ALEX EXAMPLE
Raisin spaarproduct(en)
KENMERK: SYNTHETIC
OMSCHRIJVING: Fictional savings
IBAN: NL00TEST0000000000
BANK: EXAMPLE BANK
LAND: EXAMPLE
Bronbelasting
EUR 1.000,00 1.012,34 12,34 12,34
""",
    "revolut": """EUR Statement
Revolut Bank UAB (Netherlands Branch)
IBAN NL00REVO0000000000
Account transactions from January 1, 2024 to December 31, 2024
Balance summary
Account (Current Account) €1,000.00 €250.00 €400.00 €1,150.00
""",
    "degiro": """DEGIRO Jaaropgave 2024
Dhr. ALEX EXAMPLE
Account: ****mpl
Portefeuilleoverzicht per 1-1-2024
Totale portefeuille waarde per 1-1-2024 50.000,00EUR
Portefeuilleoverzicht per 31-12-2024
Totale portefeuille waarde per 31-12-2024 55.000,00EUR
Totale waarde van stortingen * 10.000,00 EUR
Totale waarde van opnames * 0,00 EUR
""",
    "flatex": """flatexDEGIRO Bank AG
Lijst met financiële klanteninstrumenten en klantenfondsen
Ingesloten vindt u de lijst voor 31.12.2024.
Rekeningnummer : 1000000000
Rekeningstand : 100,00 EUR
Effectenrekeningnummer : 1000000001
Effectenrekeningposities
XX0000000001** 1.000,00 EUR
XX0000000002** 2.000,00 EUR
""",
    "belastingdienst": """Aangifte inkomstenbelasting 2024
Eigen kopie, niet opsturen
Formulierenversie IB 650E
Persoonlijke gegevens van ALEX EXAMPLE
Burgerservicenummer 123456789
Waarde van bezittingen 100.000 120.000
Naam echtgenoot SAM EXAMPLE
ALEX EXAMPLE en partner zijn heel 2024 fiscale partners
Grondslag sparen en beleggen
€ 160.000
Uw deel € 120.000
Deel SAM EXAMPLE € 40.000
""",
}


def synthetic_column_pdf(path: Path, fragments):
    """Synthetic cells written column-first, so stream order is not row order."""
    from pypdf import PdfWriter
    from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject
    writer = PdfWriter()
    page = writer.add_blank_page(width=900, height=900)
    font = DictionaryObject({NameObject('/Type'): NameObject('/Font'),
                             NameObject('/Subtype'): NameObject('/Type1'),
                             NameObject('/BaseFont'): NameObject('/Courier'),
                             NameObject('/Encoding'): NameObject('/WinAnsiEncoding')})
    page[NameObject('/Resources')] = DictionaryObject({NameObject('/Font'): DictionaryObject({NameObject('/F1'): writer._add_object(font)})})
    commands = []
    for x, y, text in fragments:
        escaped = text.replace('\\', '\\\\').replace('(', '\\(').replace(')', '\\)')
        commands.append(f'BT /F1 10 Tf {x} {y} Td ({escaped}) Tj ET')
    stream = DecodedStreamObject()
    stream.set_data('\n'.join(commands).encode('cp1252'))
    page[NameObject('/Contents')] = writer._add_object(stream)
    writer.write(path)


REVOLUT = [
    (20, 850, 'Revolut Annual Financial Summary 2024'),
    (20, 820, 'First Name'), (20, 800, 'Last Name'), (20, 780, 'Email'),
    (220, 820, 'Alex'), (220, 800, 'Example'), (220, 780, 'fictional@example.invalid'),
    (20, 740, 'Account Number'),
    (20, 720, 'NL00 REVO 0000000000'),
    (280, 720, '1,000.00'), (430, 720, '1,012.34'), (580, 720, '12.34'), (680, 720, '0.00'),
]
SNS = [
    (20, 850, 'SNS Totaaloverzicht Rekeningen 2024'),
    (20, 820, 'Rekening Rekeninghouder Saldo per 01-01-2024 Saldo per 31-12-2024'),
    (20, 780, 'Shared checking'), (20, 760, 'NL00SNSB0000000000'),
    (20, 730, 'Child checking'), (20, 710, 'NL00SNSB0000000001'),
    (210, 780, 'A. Example e/o B. Example'), (210, 730, 'C. Example'),
    (540, 780, '1.000,00'), (690, 780, '900,00'),
    (540, 730, '100,00'), (690, 730, '150,00'),
]
