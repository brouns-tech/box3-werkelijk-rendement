"""Synthetic offline smoke test shared by source and frozen release builds."""
from __future__ import annotations

from pathlib import Path
import json
import sqlite3


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


def smoke_test(directory: Path) -> None:
    # Exercise the upstream dashboard dependency boundary in frozen builds too.
    from dashboard.explorer_compat import DirPicker
    from wr.workspace.settings import load_settings
    assert callable(DirPicker)
    from wr.desktop.storage import app_version, prepare_workspace, remember_language, remembered_language
    from wr.i18n import currency, translator
    from wr.messages import Messages
    from wr.export import write_audit_export
    from wr.calculations.service import recompute
    from wr.importing.pipeline import run_import
    from wr.parsers import PLUGINS
    from wr.importing.classification import classify, guess_tax_year
    from wr.parsers import parse_document
    from dataclasses import asdict
    from wr.documents.extraction import extract_text

    directory.mkdir(parents=True, exist_ok=True)
    config = prepare_workspace(directory)
    for language in ("nl", "en"):
        remember_language(directory, language)
        assert remembered_language(directory) == language
        assert translator(language)(Messages.SELECT_FOLDER) == ("Map selecteren" if language == "nl" else "Select folder")
        assert currency(1234.56, language) == ("€ 1.234,56" if language == "nl" else "€ 1,234.56")
    layout_directory = directory / "layout-fixtures"
    layout_directory.mkdir(exist_ok=True)
    for issuer, fragments, expected_holders in (
        ("revolut", REVOLUT, [["Alex Example"]]),
        ("sns", SNS, [["A. Example", "B. Example"], ["C. Example"]]),
    ):
        fixture = layout_directory / f"{issuer}.pdf"
        synthetic_column_pdf(fixture, fragments)
        layout_text, _ = extract_text(fixture)
        identified = classify(layout_text)
        assert identified and identified.issuer == issuer
        decoded = parse_document(issuer, identified.doc_type, layout_text, 2024)
        assert [fact.holder_names for fact in decoded.facts] == expected_holders
    documents = directory / "synthetic-documents"
    documents.mkdir(exist_ok=True)
    pdf = documents / "arbitrary-name.PDF"
    synthetic_pdf(pdf)
    for issuer, sample in SAMPLES.items():
        fixture = documents / ("arbitrary-name.PDF" if issuer == "ing" else f"synthetic-{issuer}.PDF")
        synthetic_pdf(fixture, sample)
        extracted, _ = extract_text(fixture)
        identified = classify(extracted)
        assert identified and identified.issuer == issuer
        year = guess_tax_year(sample, identified.doc_type)
        original = parse_document(issuer, identified.doc_type, sample, year)
        decoded = parse_document(issuer, identified.doc_type, extracted, year)
        assert original.facts or original.tax_return
        assert asdict(decoded) == asdict(original), issuer
    # Both CLI and frozen desktop use bundled PDFium without external tools.
    text, pages = extract_text(pdf)
    assert "ING Jaaroverzicht 2024" in text and pages == 1
    assert {p.issuer for p in PLUGINS} == {"ing", "rabobank", "sns", "raisin", "revolut", "degiro", "flatex", "belastingdienst"}
    db = load_settings(config).resolved_db_path
    report = run_import(documents, db)
    assert report.parsed + report.duplicate == len(SAMPLES) and not report.failed
    recompute(db)
    with sqlite3.connect(db) as conn:
        row = conn.execute("SELECT interest_received FROM account_year_facts WHERE issuer='ing'").fetchone()
        assert row and row[0] == 12.34
        assert conn.execute("SELECT grondslag FROM tax_returns").fetchone()[0] == 160000
        assert conn.execute("SELECT COUNT(*) FROM partner_tax_results WHERE tax_year=2024").fetchone()[0] == 2
    write_audit_export(db, directory / "audit.zip")
    (directory / "smoke-result.json").write_text(json.dumps({"version": app_version(), "parsers": len(PLUGINS), "pdf_backend": "pdfium", "config": str(config)}))

# Fictional layouts exercise the extraction boundary, not just parser strings.
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
