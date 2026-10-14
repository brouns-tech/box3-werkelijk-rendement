"""Presentation-only localization. Stored facts and audit exports keep stable identifiers."""
from __future__ import annotations

from functools import partial

LANGUAGES = {"nl": "Nederlands", "en": "English"}

# English messages are the keys, so no external locale files need bundling.
DUTCH = {
    "PDF extraction has been updated. Scan your document folder again to refresh {count} previously imported documents before reviewing the calculation.": "De PDF-verwerking is bijgewerkt. Scan uw documentenmap opnieuw om {count} eerder geïmporteerde documenten te vernieuwen voordat u de berekening beoordeelt.",
    "Closing the browser tab leaves the application running. Use Exit application to stop it.": "Als u het browsertabblad sluit, blijft de applicatie actief. Gebruik Applicatie afsluiten om deze te stoppen.",
    "The application is stopping. You can close this browser tab.": "De applicatie wordt afgesloten. U kunt dit browsertabblad sluiten.",
    "Another instance is still starting. Wait and reopen the application. See {log}.": "Een andere instantie start nog. Wacht en open de applicatie opnieuw. Raadpleeg {log}.",
    "Overview": "Overzicht",
    "Documents": "Documenten",
    "Taxpayers": "Belastingplichtigen",
    "Settings": "Instellingen",
    "Allocation": "Toerekening",
    "Joint": "Gezamenlijk",
    "Individual": "Individueel",
    "Save all changes and update analysis": "Alle wijzigingen opslaan en analyse bijwerken",
    "Discard all unsaved changes": "Alle niet-opgeslagen wijzigingen verwerpen",
    "Document folder": "Documentenmap",
    "Save folder": "Map opslaan",
    "Paste a folder path or browse. Relative paths start at this workspace; ~ refers to your home folder.": "Plak een mappad of blader. Relatieve paden beginnen bij deze werkruimte; ~ verwijst naar uw thuismap.",
    "Choose a folder on the computer running the app. Imports scan PDFs in that folder and its subfolders directly. The path is remembered across sessions.": "Kies een map op de computer waarop de app draait. De import leest PDF-bestanden rechtstreeks uit deze map en submappen. Het pad wordt onthouden.",
    "Import documents": "Documenten importeren",
    "Choose a document folder first.": "Kies eerst een documentenmap.",
    "The document folder does not exist or is not a directory.": "De documentenmap bestaat niet of is geen map.",
    "Importing documents…": "Documenten worden geïmporteerd…",
    "Document folder saved.": "Documentenmap opgeslagen.",
    "Taxpayer names and aliases are saved in this workspace and reused across sessions.": "Namen en aliassen van belastingplichtigen worden opgeslagen in deze werkruimte en hergebruikt.",
    "Tax returns identify primary taxpayers and fiscal partners. Other distinct account holders are suggested as minor children; review these guesses, especially missing adult returns and shared initials. Fiscal partnership and allocation come from each tax return.": "Aangiften identificeren belastingplichtigen en fiscale partners. Andere rekeninghouders worden voorgesteld als minderjarige kinderen; controleer deze suggesties, vooral bij ontbrekende aangiften van volwassenen en gedeelde initialen. Fiscaal partnerschap en verdeling volgen uit elke aangifte.",
    "First taxpayer": "Eerste belastingplichtige",
    "Second taxpayer (optional)": "Tweede belastingplichtige (optioneel)",
    "Canonical name": "Voorkeursnaam",
    "Aliases (one per line)": "Aliassen (één per regel)",
    "For one identity, clear the second name and assign its spellings to the remaining person. Two identities do not imply full-year fiscal partnership.": "Voor één persoon: wis de tweede naam en wijs de schrijfwijzen toe aan de overblijvende persoon. Twee personen betekenen niet automatisch fiscaal partnerschap voor het hele jaar.",
    "Minor children (assets attributed to parents)": "Minderjarige kinderen (vermogen toegerekend aan ouders)",
    "Minderjarige kinderen: use this category for children whose Box 3 assets are attributed to the parents. Their documents appear as joint (purple) in the overview. Review ages and parental authority for the relevant tax year.": "Gebruik deze categorie voor minderjarige kinderen van wie het Box 3-vermogen wordt toegerekend aan de ouders. Hun documenten verschijnen als gezamenlijk (paars). Controleer leeftijden en ouderlijk gezag voor het betreffende belastingjaar.",
    "Add child": "Kind toevoegen",
    "Delete child": "Kind verwijderen",
    "Unassigned": "Niet toegewezen",
    "First taxpayer (enter a name above)": "Eerste belastingplichtige (voer hierboven een naam in)",
    "Second taxpayer (enter a name above)": "Tweede belastingplichtige (voer hierboven een naam in)",
    "Names found in documents": "Namen gevonden in documenten",
    "Assignments save and update the analysis immediately, including any name or alias edits above. These assignments take precedence over the alias text. Source names are preserved.": "Toewijzingen worden direct opgeslagen en werken de analyse bij, inclusief wijzigingen in namen of aliassen hierboven. Deze toewijzingen gaan voor de aliastekst. Bronnamen blijven behouden.",
    "Provide a child name before assigning aliases or documents.": "Voer een naam voor het kind in voordat u aliassen of documenten toewijst.",
    "Settings saved.": "Instellingen opgeslagen.",
    "Storage": "Opslag",
    "Database file": "Databasebestand",
    "Relative paths start at this workspace. Choosing a different file opens a different dataset; existing database files stay on disk.": "Relatieve paden beginnen bij deze werkruimte. Een ander bestand opent een andere gegevensverzameling; bestaande databasebestanden blijven op schijf.",
    "Additional options": "Aanvullende opties",
    "Institution options apply when documents are parsed. To apply changes to existing documents, reset the workspace and import them again.": "Instellingsopties worden toegepast bij het verwerken van documenten. Stel de werkruimte opnieuw in en importeer opnieuw om wijzigingen op bestaande documenten toe te passen.",
    "Save workspace settings": "Werkruimte-instellingen opslaan",
    "Provide a database file path.": "Geef een pad voor het databasebestand op.",
    "Workspace settings saved.": "Werkruimte-instellingen opgeslagen.",
    "Workspace reset. Choose a document folder to start again.": "Werkruimte opnieuw ingesteld. Kies een documentenmap om opnieuw te beginnen.",
    "Reset workspace": "Werkruimte opnieuw instellen",
    "Remove all taxpayer profiles, aliases, imported document records, extracted data, analysis results, institution options, and the saved document folder.": "Verwijder alle profielen, aliassen, geïmporteerde documentgegevens, geëxtraheerde gegevens, analyseresultaten, instellingsopties en de opgeslagen documentenmap.",
    "Original PDFs and audit exports stay on disk.": "Originele PDF-bestanden en auditexports blijven op schijf.",
    "This permanently deletes all imported data and profiles from this workspace. You will need to import your documents again.": "Dit verwijdert alle geïmporteerde gegevens en profielen definitief uit deze werkruimte. U moet uw documenten opnieuw importeren.",
    "Delete profiles and imported data": "Profielen en geïmporteerde gegevens verwijderen",
    "Cancel": "Annuleren",
    "Child {number}": "Kind {number}",
    "Child {number} (enter a name above)": "Kind {number} (voer hierboven een naam in)",
    "Workspace: {path}": "Werkruimte: {path}",
    "Cannot browse this folder: {error}": "Kan deze map niet openen: {error}",
    "Could not save workspace settings: {error}": "Werkruimte-instellingen konden niet worden opgeslagen: {error}",
    "Could not reset workspace: {error}": "Werkruimte kon niet opnieuw worden ingesteld: {error}",
    "Import finished: {parsed} parsed, {duplicate} duplicates, {skipped} skipped, {failed} failed.": "Import voltooid: {parsed} verwerkt, {duplicate} dubbel, {skipped} niet herkend, {failed} mislukt.",
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
