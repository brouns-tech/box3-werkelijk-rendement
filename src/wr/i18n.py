"""Presentation-only localization. Stored facts and audit exports keep stable identifiers."""
from __future__ import annotations

from functools import partial

LANGUAGES = {"nl": "Nederlands", "en": "English"}

# English messages are the keys, so no external locale files need bundling.
DUTCH = {
    "Language / Taal": "Language / Taal",
    "Werkelijk rendement — Box 3": "Werkelijk rendement — Box 3",
    "Database: `{name}`": "Database: `{name}`",
    "Select a document folder to get started.": "Selecteer een documentenmap om te beginnen.",
    "Database not found. Run `wr import` first.": "Database niet gevonden. Voer eerst `wr import` uit.",
    "No tax years in database yet.": "Er staan nog geen belastingjaren in de database.",
    "Tax year": "Belastingjaar",
    "Download audit export": "Auditexport downloaden",
    "ZIP with yearly totals, asset calculations, source facts, and tax results.": "ZIP met jaartotalen, vermogensberekeningen, brongegevens en belastingresultaten.",
    "Coverage": "Documentdekking",
    "Actual return": "Werkelijk rendement",
    "Statement sources": "Brongegevens uit overzichten",
    "Missing / partial: {details}": "Ontbrekend / gedeeltelijk: {details}",
    "No portfolio rollup for this year.": "Voor dit jaar is geen vermogensoverzicht beschikbaar.",
    "Decision overview": "Vergelijking van rendementen",
    "No tax decision is available for this year.": "Voor dit jaar is geen belastingvergelijking beschikbaar.",
    "Taxpayer": "Belastingplichtige",
    "Fictitious return": "Forfaitair rendement",
    "Decision": "Uitkomst",
    "Potential tax savings": "Mogelijke belastingbesparing",
    "Actual return better": "Werkelijk rendement gunstiger",
    "Fictitious return better": "Forfaitair rendement gunstiger",
    "No material difference": "Geen wezenlijk verschil",
    "Incomplete data": "Onvolledige gegevens",
    "Manual review needed": "Handmatige controle nodig",
    "Not applicable": "Niet van toepassing",
    "Unknown": "Onbekend",
    "Account overview": "Rekeningoverzicht",
    "Account holder": "Rekeninghouder",
    "Box 3": "Box 3",
    "Source": "Bron",
    "Account label": "Rekeningnaam",
    "Account key": "Rekeningkenmerk",
    "Value 1 January": "Waarde op 1 januari",
    "Value 31 December": "Waarde op 31 december",
    "Purchases / deposits": "Aankopen / stortingen",
    "Sales / withdrawals": "Verkopen / opnames",
    "Received interest": "Ontvangen rente",
    "Paid interest": "Betaalde rente",
    "Gross dividends": "Bruto dividend",
    "Withholding tax": "Bronbelasting",
    "Calculated actual return": "Berekend werkelijk rendement",
    "Market-value component (internal)": "Waardeverandering (intern)",
    "Currency": "Valuta",
    "Calculation method": "Berekeningsmethode",
    "Import diagnostics": "Importmeldingen",
    "Document type": "Documentsoort",
    "Parsed": "Verwerkt",
    "Skipped": "Niet herkend",
    "Failed": "Mislukt",
    "Total": "Totaal",
    "Yes": "Ja",
    "No": "Nee",
    "Complete for available statements": "Volledig voor de beschikbare overzichten",
    "Partial": "Gedeeltelijk",
    "Missing": "Ontbrekend",
    "No canonical Box 3 statements for this year": "Geen geselecteerde Box 3-bronoverzichten voor dit jaar",
    "No actual-return fields": "Geen gegevens voor werkelijk rendement",
    "Balance and cash flows": "Saldo en geldstromen",
    "Interest only": "Alleen rente",
    "Reported return": "Gerapporteerd rendement",
    "Explicit values": "Expliciete waarden",
    "Incomplete balance change": "Onvolledige saldoverandering",
    "Annual statement": "Jaaroverzicht",
    "Income tax return": "Aangifte inkomstenbelasting",
    "Final assessment": "Definitieve aanslag",
    "Savings statement": "Spaaroverzicht",
    "Account statement": "Rekeningafschrift",
    "Account inventory": "Rekeninginventaris",
    "Securities and cash inventory": "Effecten- en geldinventaris",
    "Tax certificate": "Belastingcertificaat",
    "Unclassified": "Niet geclassificeerd",
    "Other": "Overig",
    "Version {version} · Local processing · Data: {directory}": "Versie {version} · Lokale verwerking · Gegevens: {directory}",
    "Select a folder with annual statements and tax returns. Source files stay unchanged. Importing does not prove that your entire financial situation is covered.": "Selecteer een map met jaaroverzichten en aangiften. De bronbestanden blijven ongewijzigd. Importeren bewijst niet dat uw totale financiële situatie volledig is gedekt.",
    "Select folder": "Map selecteren",
    "Folder selection failed: {error}": "Mapselectie mislukt: {error}",
    "Selected folder: {folder}": "Geselecteerde map: {folder}",
    "Scan documents and calculate": "Documenten scannen en berekenen",
    "The selected folder is no longer available. Select another folder.": "De geselecteerde map is niet meer beschikbaar. Selecteer een andere map.",
    "Exit application": "Applicatie afsluiten",
    "Searching for documents…": "Documenten zoeken…",
    "Stop import after current document": "Import stoppen na huidig document",
    "Imported documents are retained; calculations will be updated.": "Reeds geïmporteerde documenten blijven behouden; berekeningen worden bijgewerkt.",
    "Another dashboard window is already importing documents.": "Er loopt al een import in een ander dashboardvenster.",
    "Import failed: {error}": "Import mislukt: {error}",
    "Technical details from the source or parser are shown as recorded.": "Technische details uit de bron of parser worden weergegeven zoals vastgelegd.",
    "Stopped": "Gestopt",
    "Done": "Gereed",
    "{status}: {parsed} processed, {duplicate} duplicate, {skipped} unrecognized, {failed} failed.": "{status}: {parsed} verwerkt, {duplicate} dubbel, {skipped} niet herkend, {failed} mislukt.",
    "Refresh dashboard": "Dashboard bijwerken",
    "File": "Bestand",
    "Status": "Status",
    "Institution": "Instelling",
    "Document": "Document",
    "Year": "Jaar",
    "Details": "Toelichting",
    "Duplicate": "Dubbel",
    "Starting dashboard…": "Dashboard wordt gestart…",
    "Open dashboard": "Dashboard openen",
    "Open local data": "Lokale gegevens openen",
    "Exit": "Afsluiten",
    "Dashboard running. Close this window to exit.": "Dashboard actief. Sluit dit venster om af te sluiten.",
    "Another instance is still starting. Close it through its launcher and try again.": "Een andere instantie start nog. Sluit die via het startvenster en probeer opnieuw.",
    "Dashboard stopped. See {log}.": "Dashboard is gestopt. Raadpleeg {log}.",
    "Startup is taking too long. See {log}.": "Starten duurt te lang. Raadpleeg {log}.",
    "Could not save language preference: {error}": "Taalvoorkeur kon niet worden opgeslagen: {error}",
    "Refresh the dashboard after changing language here.": "Vernieuw het dashboard nadat u hier de taal wijzigt.",
    "Could not open {target}: {error}": "Kon {target} niet openen: {error}",
}


def translate(language: str, message: str, **values) -> str:
    template = DUTCH.get(message, message) if language == "nl" else message
    return template.format(**values) if values else template


def translator(language: str):
    if language not in LANGUAGES:
        raise ValueError(f"Unsupported language: {language}")
    return partial(translate, language)


def currency(value: float | None, language: str = "en") -> str:
    if value is None:
        return "—"
    number = f"{value:,.2f}"
    if language == "nl":
        number = number.translate(str.maketrans({",": ".", ".": ","}))
    return f"€ {number}"


STATUS_MESSAGES = {
    "ACTUAL_BETTER": "Actual return better", "FICTITIOUS_BETTER": "Fictitious return better",
    "EQUAL": "No material difference", "INDETERMINATE_MISSING_DATA": "Incomplete data",
    "NEEDS_MANUAL_RSAMW": "Manual review needed", "NOT_APPLICABLE": "Not applicable",
    "COMPLETE": "Complete for available statements", "PARTIAL": "Partial",
    "MISSING": "Missing", "UNKNOWN": "Unknown",
    "parsed": "Parsed", "skipped": "Skipped", "failed": "Failed", "duplicate": "Duplicate",
    "balance_flow": "Balance and cash flows", "interest_only": "Interest only",
    "earned_return": "Reported return", "explicit": "Explicit values",
    "balance_delta_incomplete": "Incomplete balance change", "unknown": "Unknown",
    "jaaroverzicht": "Annual statement", "aangifte_ib": "Income tax return",
    "definitieve_aanslag": "Final assessment", "savings_statement": "Savings statement",
    "account_statement": "Account statement", "totaaloverzicht": "Account inventory",
    "financial_instruments_statement": "Securities and cash inventory",
    "steuerbescheinigung": "Tax certificate", "unclassified": "Unclassified", "other": "Other",
    "belastingcertificaat": "Tax certificate",
}


def status_label(value: str | None, language: str) -> str:
    return translate(language, STATUS_MESSAGES.get(value, value)) if value else "—"


def coverage_details(value: str, language: str) -> str:
    # Translate only known generated messages, never account identifiers or source text.
    messages = []
    suffix = " (no actual-return fields)"
    for entry in value.split("; "):
        if entry == "no canonical Box 3 statements for this year":
            entry = translate(language, "No canonical Box 3 statements for this year")
        elif entry.endswith(suffix):
            entry = entry[:-len(suffix)] + " (" + translate(language, "No actual-return fields") + ")"
        messages.append(entry)
    return "; ".join(messages)
