"""Typed definitions for application-owned English and Dutch messages."""
from __future__ import annotations

from dataclasses import dataclass
from string import Formatter
from typing import Final


def _fields(text: str) -> set[str]:
    return {name for _, name, _, _ in Formatter().parse(text) if name is not None}


@dataclass(frozen=True)
class Message:
    en: str
    nl: str

    def __post_init__(self) -> None:
        if _fields(self.en) or _fields(self.nl):
            raise ValueError("Use MessageTemplate for messages with parameters")


@dataclass(frozen=True)
class MessageTemplate:
    en: str
    nl: str

    def __post_init__(self) -> None:
        if not _fields(self.en) or _fields(self.en) != _fields(self.nl):
            raise ValueError("Message templates must have matching parameters in both languages")


class Messages:
    CONFLICTING_SOURCE_EVIDENCE: Final = Message(
        "Conflicting source evidence", "Tegenstrijdige brongegevens"
    )
    RECONCILIATION_EVIDENCE: Final = Message(
        "Reconciled facts and supporting evidence", "Afgestemde feiten en onderliggende bewijsstukken"
    )
    ACCOUNT_CURRENCY_HELP: Final = Message(
        "Account amounts use the source currency. Unconverted foreign-currency accounts are excluded from EUR totals and keep the tax comparison incomplete.",
        "Rekeningbedragen staan in de bronvaluta. Niet-omgerekende vreemdevalutarekeningen tellen niet mee in EUR-totalen en houden de belastingvergelijking onvolledig.",
    )
    ACCOUNT_HOLDER: Final = Message(
        "Account holder",
        "Rekeninghouder",
    )
    ACCOUNT_INVENTORY: Final = Message(
        "Account inventory",
        "Rekeninginventaris",
    )
    ACCOUNT_KEY: Final = Message(
        "Account key",
        "Rekeningkenmerk",
    )
    ACCOUNT_LABEL: Final = Message(
        "Account label",
        "Rekeningnaam",
    )
    ACCOUNT_OVERVIEW: Final = Message(
        "Account overview",
        "Rekeningoverzicht",
    )
    ACCOUNT_STATEMENT: Final = Message(
        "Account statement",
        "Rekeningafschrift",
    )
    ACTUAL_RETURN: Final = Message(
        "Actual return",
        "Werkelijk rendement",
    )
    ACTUAL_RETURN_BETTER: Final = Message(
        "Actual return better",
        "Werkelijk rendement gunstiger",
    )
    ADDITIONAL_OPTIONS: Final = Message(
        "Additional options",
        "Aanvullende opties",
    )
    ADD_CHILD: Final = Message(
        "Add child",
        "Kind toevoegen",
    )
    ALIASES_ONE_PER_LINE: Final = Message(
        "Aliases (one per line)",
        "Aliassen (één per regel)",
    )
    ALLOCATED_ACTUAL_RETURN: Final = Message(
        "Allocated actual return",
        "Toegerekend werkelijk rendement",
    )
    ALLOCATION: Final = Message(
        "Allocation",
        "Toerekening",
    )
    ANNUAL_STATEMENT: Final = Message(
        "Annual statement",
        "Jaaroverzicht",
    )
    APPLICATION_STOPPING: Final = Message(
        "The application is stopping. You can close this browser tab.",
        "De applicatie wordt afgesloten. U kunt dit browsertabblad sluiten.",
    )
    AUDIT_EXPORT_HELP: Final = Message(
        "ZIP with yearly totals, asset calculations, source facts, and tax results.",
        "ZIP met jaartotalen, vermogensberekeningen, brongegevens en belastingresultaten.",
    )
    AVAILABLE_EVIDENCE: Final = Message(
        "Available evidence",
        "Beschikbare gegevens",
    )
    BALANCE_AND_CASH_FLOWS: Final = Message(
        "Balance and cash flows",
        "Saldo en geldstromen",
    )
    BOX_3: Final = Message(
        "Box 3",
        "Box 3",
    )
    BROWSER_CLOSE_HELP: Final = Message(
        "Closing the browser tab leaves the application running. Use Exit application to stop it.",
        "Als u het browsertabblad sluit, blijft de applicatie actief. Gebruik Applicatie afsluiten om deze te stoppen.",
    )
    CALCULATED_ACTUAL_RETURN: Final = Message(
        "Calculated actual return",
        "Berekend werkelijk rendement",
    )
    CALCULATION_METHOD: Final = Message(
        "Calculation method",
        "Berekeningsmethode",
    )
    CANCEL: Final = Message(
        "Cancel",
        "Annuleren",
    )
    CANNOT_BROWSE_FOLDER: Final = MessageTemplate(
        "Cannot browse this folder: {error}",
        "Kan deze map niet openen: {error}",
    )
    CANONICAL_NAME: Final = Message(
        "Canonical name",
        "Voorkeursnaam",
    )
    CHILD: Final = MessageTemplate(
        "Child {number}",
        "Kind {number}",
    )
    CHILD_NAME_PLACEHOLDER: Final = MessageTemplate(
        "Child {number} (enter a name above)",
        "Kind {number} (voer hierboven een naam in)",
    )
    CHOOSE_A_DOCUMENT_FOLDER_FIRST: Final = Message(
        "Choose a document folder first.",
        "Kies eerst een documentenmap.",
    )
    COULD_NOT_OPEN: Final = MessageTemplate(
        "Could not open {target}: {error}",
        "Kon {target} niet openen: {error}",
    )
    COULD_NOT_RESET_WORKSPACE: Final = MessageTemplate(
        "Could not reset workspace: {error}",
        "Werkruimte kon niet opnieuw worden ingesteld: {error}",
    )
    COULD_NOT_SAVE_LANGUAGE_PREFERENCE: Final = MessageTemplate(
        "Could not save language preference: {error}",
        "Taalvoorkeur kon niet worden opgeslagen: {error}",
    )
    COULD_NOT_SAVE_WORKSPACE_SETTINGS: Final = MessageTemplate(
        "Could not save workspace settings: {error}",
        "Werkruimte-instellingen konden niet worden opgeslagen: {error}",
    )
    COVERAGE: Final = Message(
        "Coverage",
        "Documentdekking",
    )
    COVERAGE_HELP: Final = Message(
        "Coverage concerns imported statements only; it does not establish that all assets or partner documents are present.",
        "Dekking betreft alleen geïmporteerde overzichten; dit bewijst niet dat alle bezittingen of partnerdocumenten aanwezig zijn.",
    )
    CURRENCY: Final = Message(
        "Currency",
        "Valuta",
    )
    DASHBOARD_RUNNING: Final = Message(
        "Dashboard running. Close this window to exit.",
        "Dashboard actief. Sluit dit venster om af te sluiten.",
    )
    DASHBOARD_STOPPED: Final = MessageTemplate(
        "Dashboard stopped. See {log}.",
        "Dashboard is gestopt. Raadpleeg {log}.",
    )
    DATABASE: Final = MessageTemplate(
        "Database: `{name}`",
        "Database: `{name}`",
    )
    DATABASE_FILE: Final = Message(
        "Database file",
        "Databasebestand",
    )
    DATABASE_FILE_HELP: Final = Message(
        "Relative paths start at this workspace. Choosing a different file opens a different dataset; existing database files stay on disk.",
        "Relatieve paden beginnen bij deze werkruimte. Een ander bestand opent een andere gegevensverzameling; bestaande databasebestanden blijven op schijf.",
    )
    DATABASE_NOT_FOUND_RUN_WR_IMPORT_FIRST: Final = Message(
        "Database not found. Run `wr import` first.",
        "Database niet gevonden. Voer eerst `wr import` uit.",
    )
    DECISION: Final = Message(
        "Decision",
        "Uitkomst",
    )
    DECISION_OVERVIEW: Final = Message(
        "Decision overview",
        "Vergelijking van rendementen",
    )
    DELETE_CHILD: Final = Message(
        "Delete child",
        "Kind verwijderen",
    )
    DELETE_PROFILES_AND_IMPORTED_DATA: Final = Message(
        "Delete profiles and imported data",
        "Profielen en geïmporteerde gegevens verwijderen",
    )
    DESKTOP_IMPORT_HELP: Final = Message(
        "Select a folder with annual statements and tax returns. Source files stay unchanged. Importing does not prove that your entire financial situation is covered.",
        "Selecteer een map met jaaroverzichten en aangiften. De bronbestanden blijven ongewijzigd. Importeren bewijst niet dat uw totale financiële situatie volledig is gedekt.",
    )
    DETAILS: Final = Message(
        "Details",
        "Toelichting",
    )
    DISCARD_ALL_UNSAVED_CHANGES: Final = Message(
        "Discard all unsaved changes",
        "Alle niet-opgeslagen wijzigingen verwerpen",
    )
    DOCUMENT: Final = Message(
        "Document",
        "Document",
    )
    DOCUMENTS: Final = Message(
        "Documents",
        "Documenten",
    )
    DOCUMENT_FOLDER: Final = Message(
        "Document folder",
        "Documentenmap",
    )
    DOCUMENT_FOLDER_HELP: Final = Message(
        "Paste a folder path or browse. Relative paths start at this workspace; ~ refers to your home folder.",
        "Plak een mappad of blader. Relatieve paden beginnen bij deze werkruimte; ~ verwijst naar uw thuismap.",
    )
    DOCUMENT_FOLDER_SAVED: Final = Message(
        "Document folder saved.",
        "Documentenmap opgeslagen.",
    )
    DOCUMENT_IMPORT_HELP: Final = Message(
        "Choose a folder on the computer running the app. Imports scan PDFs in that folder and its subfolders directly. The path is remembered across sessions.",
        "Kies een map op de computer waarop de app draait. De import leest PDF-bestanden rechtstreeks uit deze map en submappen. Het pad wordt onthouden.",
    )
    DOCUMENT_TYPE: Final = Message(
        "Document type",
        "Documentsoort",
    )
    DONE: Final = Message(
        "Done",
        "Gereed",
    )
    DOWNLOAD_AUDIT_EXPORT: Final = Message(
        "Download audit export",
        "Auditexport downloaden",
    )
    DUPLICATE: Final = Message(
        "Duplicate",
        "Dubbel",
    )
    EXIT: Final = Message(
        "Exit",
        "Afsluiten",
    )
    EXIT_APPLICATION: Final = Message(
        "Exit application",
        "Applicatie afsluiten",
    )
    EXPLICIT_VALUES: Final = Message(
        "Explicit values",
        "Expliciete waarden",
    )
    FAILED: Final = Message(
        "Failed",
        "Mislukt",
    )
    FICTITIOUS_RETURN: Final = Message(
        "Fictitious return",
        "Forfaitair rendement",
    )
    FICTITIOUS_RETURN_BETTER: Final = Message(
        "Fictitious return better",
        "Forfaitair rendement gunstiger",
    )
    FILE: Final = Message(
        "File",
        "Bestand",
    )
    FINAL_ASSESSMENT: Final = Message(
        "Final assessment",
        "Definitieve aanslag",
    )
    FIRST_TAXPAYER: Final = Message(
        "First taxpayer",
        "Eerste belastingplichtige",
    )
    FIRST_TAXPAYER_ENTER_A_NAME_ABOVE: Final = Message(
        "First taxpayer (enter a name above)",
        "Eerste belastingplichtige (voer hierboven een naam in)",
    )
    FOLDER_SELECTION_FAILED: Final = MessageTemplate(
        "Folder selection failed: {error}",
        "Mapselectie mislukt: {error}",
    )
    GROSS_DIVIDENDS: Final = Message(
        "Gross dividends",
        "Bruto dividend",
    )
    IDENTITY_ASSIGNMENT_HELP: Final = Message(
        "Assignments save and update the analysis immediately, including any name or alias edits above. These assignments take precedence over the alias text. Source names are preserved.",
        "Toewijzingen worden direct opgeslagen en werken de analyse bij, inclusief wijzigingen in namen of aliassen hierboven. Deze toewijzingen gaan voor de aliastekst. Bronnamen blijven behouden.",
    )
    IMPORTING_DOCUMENTS: Final = Message(
        "Importing documents…",
        "Documenten worden geïmporteerd…",
    )
    IMPORT_BUSY: Final = Message(
        "Another dashboard window is already importing documents.",
        "Er loopt al een import in een ander dashboardvenster.",
    )
    IMPORT_DIAGNOSTICS: Final = Message(
        "Import diagnostics",
        "Importmeldingen",
    )
    IMPORT_DIAGNOSTICS_HELP: Final = Message(
        "Technical details from the source or parser are shown as recorded.",
        "Technische details uit de bron of parser worden weergegeven zoals vastgelegd.",
    )
    IMPORT_DOCUMENTS: Final = Message(
        "Import documents",
        "Documenten importeren",
    )
    IMPORT_FAILED: Final = MessageTemplate(
        "Import failed: {error}",
        "Import mislukt: {error}",
    )
    IMPORT_FINISHED: Final = MessageTemplate(
        "Import finished: {parsed} parsed, {duplicate} duplicates, {skipped} skipped, {failed} failed.",
        "Import voltooid: {parsed} verwerkt, {duplicate} dubbel, {skipped} niet herkend, {failed} mislukt.",
    )
    IMPORT_RESULT: Final = MessageTemplate(
        "{status}: {parsed} processed, {duplicate} duplicate, {skipped} unrecognized, {failed} failed.",
        "{status}: {parsed} verwerkt, {duplicate} dubbel, {skipped} niet herkend, {failed} mislukt.",
    )
    IMPORT_STOP_HELP: Final = Message(
        "Imported documents are retained; calculations will be updated.",
        "Reeds geïmporteerde documenten blijven behouden; berekeningen worden bijgewerkt.",
    )
    INCOME_TAX_RETURN: Final = Message(
        "Income tax return",
        "Aangifte inkomstenbelasting",
    )
    INCOMPLETE_BALANCE_CHANGE: Final = Message(
        "Incomplete balance change",
        "Onvolledige saldoverandering",
    )
    INCOMPLETE_DATA: Final = Message(
        "Incomplete data",
        "Onvolledige gegevens",
    )
    INDIVIDUAL: Final = Message(
        "Individual",
        "Individueel",
    )
    INSTANCE_STARTING: Final = Message(
        "Another instance is still starting. Close it through its launcher and try again.",
        "Een andere instantie start nog. Sluit die via het startvenster en probeer opnieuw.",
    )
    INSTANCE_STARTING_LOG: Final = MessageTemplate(
        "Another instance is still starting. Wait and reopen the application. See {log}.",
        "Een andere instantie start nog. Wacht en open de applicatie opnieuw. Raadpleeg {log}.",
    )
    INSTITUTION: Final = Message(
        "Institution",
        "Instelling",
    )
    INSTITUTION_OPTIONS_HELP: Final = Message(
        "Institution options apply when documents are parsed. To apply changes to existing documents, reset the workspace and import them again.",
        "Instellingsopties worden toegepast bij het verwerken van documenten. Stel de werkruimte opnieuw in en importeer opnieuw om wijzigingen op bestaande documenten toe te passen.",
    )
    INTEREST_ONLY: Final = Message(
        "Interest only",
        "Alleen rente",
    )
    JOINT: Final = Message(
        "Joint",
        "Gezamenlijk",
    )
    LANGUAGE_REFRESH_HELP: Final = Message(
        "Refresh the dashboard after changing language here.",
        "Vernieuw het dashboard nadat u hier de taal wijzigt.",
    )
    LANGUAGE_TAAL: Final = Message(
        "Language / Taal",
        "Language / Taal",
    )
    MANUAL_REVIEW_NEEDED: Final = Message(
        "Manual review needed",
        "Handmatige controle nodig",
    )
    MARKET_VALUE_COMPONENT_INTERNAL: Final = Message(
        "Market-value component (internal)",
        "Waardeverandering (intern)",
    )
    MINOR_CHILDREN_ASSETS_ATTRIBUTED_TO_PARENTS: Final = Message(
        "Minor children (assets attributed to parents)",
        "Minderjarige kinderen (vermogen toegerekend aan ouders)",
    )
    MINOR_CHILDREN_HELP: Final = Message(
        "Minderjarige kinderen: use this category for children whose Box 3 assets are attributed to the parents. Their documents appear as joint (purple) in the overview. Review ages and parental authority for the relevant tax year.",
        "Gebruik deze categorie voor minderjarige kinderen van wie het Box 3-vermogen wordt toegerekend aan de ouders. Hun documenten verschijnen als gezamenlijk (paars). Controleer leeftijden en ouderlijk gezag voor het betreffende belastingjaar.",
    )
    MISSING: Final = Message(
        "Missing",
        "Ontbrekend",
    )
    MISSING_PARTIAL: Final = MessageTemplate(
        "Missing / partial: {details}",
        "Ontbrekend / gedeeltelijk: {details}",
    )
    NAMES_FOUND_IN_DOCUMENTS: Final = Message(
        "Names found in documents",
        "Namen gevonden in documenten",
    )
    NO: Final = Message(
        "No",
        "Nee",
    )
    NOT_APPLICABLE: Final = Message(
        "Not applicable",
        "Niet van toepassing",
    )
    NO_ACTUAL_RETURN_FIELDS: Final = Message(
        "No actual-return fields",
        "Geen gegevens voor werkelijk rendement",
    )
    NO_RECONCILED_BOX_3_STATEMENTS_FOR_THIS_YEAR: Final = Message(
        "No reconciled Box 3 statements for this year",
        "Geen afgestemde Box 3-bronoverzichten voor dit jaar",
    )
    NO_MATERIAL_DIFFERENCE: Final = Message(
        "No material difference",
        "Geen wezenlijk verschil",
    )
    NO_PORTFOLIO_ROLLUP_FOR_THIS_YEAR: Final = Message(
        "No portfolio rollup for this year.",
        "Voor dit jaar is geen vermogensoverzicht beschikbaar.",
    )
    NO_TAX_DECISION_IS_AVAILABLE_FOR_THIS_YEAR: Final = Message(
        "No tax decision is available for this year.",
        "Voor dit jaar is geen belastingvergelijking beschikbaar.",
    )
    NO_TAX_YEARS_IN_DATABASE_YET: Final = Message(
        "No tax years in database yet.",
        "Er staan nog geen belastingjaren in de database.",
    )
    OPEN_DASHBOARD: Final = Message(
        "Open dashboard",
        "Dashboard openen",
    )
    OPEN_LOCAL_DATA: Final = Message(
        "Open local data",
        "Lokale gegevens openen",
    )
    ORIGINAL_PDFS_AND_AUDIT_EXPORTS_STAY_ON_DISK: Final = Message(
        "Original PDFs and audit exports stay on disk.",
        "Originele PDF-bestanden en auditexports blijven op schijf.",
    )
    OTHER: Final = Message(
        "Other",
        "Overig",
    )
    OVERVIEW: Final = Message(
        "Overview",
        "Overzicht",
    )
    PAID_INTEREST: Final = Message(
        "Paid interest",
        "Betaalde rente",
    )
    PARSED: Final = Message(
        "Parsed",
        "Verwerkt",
    )
    PARTIAL: Final = Message(
        "Partial",
        "Gedeeltelijk",
    )
    PDF_EXTRACTION_UPDATED: Final = MessageTemplate(
        "PDF extraction has been updated. Scan your document folder again to refresh {count} previously imported documents before reviewing the calculation.",
        "De PDF-verwerking is bijgewerkt. Scan uw documentenmap opnieuw om {count} eerder geïmporteerde documenten te vernieuwen voordat u de berekening beoordeelt.",
    )
    POTENTIAL_TAX_SAVINGS: Final = Message(
        "Potential tax savings",
        "Mogelijke belastingbesparing",
    )
    PROVIDE_A_CHILD_NAME_BEFORE_ASSIGNING_ALIASES_OR_DOCUMENTS: Final = Message(
        "Provide a child name before assigning aliases or documents.",
        "Voer een naam voor het kind in voordat u aliassen of documenten toewijst.",
    )
    PROVIDE_A_DATABASE_FILE_PATH: Final = Message(
        "Provide a database file path.",
        "Geef een pad voor het databasebestand op.",
    )
    PURCHASES_DEPOSITS: Final = Message(
        "Purchases / deposits",
        "Aankopen / stortingen",
    )
    RECEIVED_INTEREST: Final = Message(
        "Received interest",
        "Ontvangen rente",
    )
    REPORTED_RETURN: Final = Message(
        "Reported return",
        "Gerapporteerd rendement",
    )
    REQUIRES_EUR_CONVERSION_AND_CURRENCY_GAIN_LOSS: Final = Message(
        "Requires EUR conversion and currency gain/loss",
        "Omrekening naar EUR en valutawinst/-verlies vereist",
    )
    RESET_WORKSPACE: Final = Message(
        "Reset workspace",
        "Werkruimte opnieuw instellen",
    )
    RESET_WORKSPACE_CONFIRMATION: Final = Message(
        "This permanently deletes all imported data and profiles from this workspace. You will need to import your documents again.",
        "Dit verwijdert alle geïmporteerde gegevens en profielen definitief uit deze werkruimte. U moet uw documenten opnieuw importeren.",
    )
    RESET_WORKSPACE_HELP: Final = Message(
        "Remove all taxpayer profiles, aliases, imported document records, extracted data, analysis results, institution options, and the saved document folder.",
        "Verwijder alle profielen, aliassen, geïmporteerde documentgegevens, geëxtraheerde gegevens, analyseresultaten, instellingsopties en de opgeslagen documentenmap.",
    )
    SALES_WITHDRAWALS: Final = Message(
        "Sales / withdrawals",
        "Verkopen / opnames",
    )
    SAVE_ALL_CHANGES_AND_UPDATE_ANALYSIS: Final = Message(
        "Save all changes and update analysis",
        "Alle wijzigingen opslaan en analyse bijwerken",
    )
    SAVE_FOLDER: Final = Message(
        "Save folder",
        "Map opslaan",
    )
    SAVE_WORKSPACE_SETTINGS: Final = Message(
        "Save workspace settings",
        "Werkruimte-instellingen opslaan",
    )
    SAVINGS_STATEMENT: Final = Message(
        "Savings statement",
        "Spaaroverzicht",
    )
    SCAN_DOCUMENTS_AND_CALCULATE: Final = Message(
        "Scan documents and calculate",
        "Documenten scannen en berekenen",
    )
    SEARCHING_FOR_DOCUMENTS: Final = Message(
        "Searching for documents…",
        "Documenten zoeken…",
    )
    SECOND_TAXPAYER_ENTER_A_NAME_ABOVE: Final = Message(
        "Second taxpayer (enter a name above)",
        "Tweede belastingplichtige (voer hierboven een naam in)",
    )
    SECOND_TAXPAYER_OPTIONAL: Final = Message(
        "Second taxpayer (optional)",
        "Tweede belastingplichtige (optioneel)",
    )
    SECURITIES_AND_CASH_INVENTORY: Final = Message(
        "Securities and cash inventory",
        "Effecten- en geldinventaris",
    )
    SELECTED_FOLDER: Final = MessageTemplate(
        "Selected folder: {folder}",
        "Geselecteerde map: {folder}",
    )
    SELECTED_FOLDER_UNAVAILABLE: Final = Message(
        "The selected folder is no longer available. Select another folder.",
        "De geselecteerde map is niet meer beschikbaar. Selecteer een andere map.",
    )
    SELECT_A_DOCUMENT_FOLDER_TO_GET_STARTED: Final = Message(
        "Select a document folder to get started.",
        "Selecteer een documentenmap om te beginnen.",
    )
    SELECT_FOLDER: Final = Message(
        "Select folder",
        "Map selecteren",
    )
    SETTINGS: Final = Message(
        "Settings",
        "Instellingen",
    )
    SETTINGS_SAVED: Final = Message(
        "Settings saved.",
        "Instellingen opgeslagen.",
    )
    SINGLE_TAXPAYER_HELP: Final = Message(
        "For one identity, clear the second name and assign its spellings to the remaining person. Two identities do not imply full-year fiscal partnership.",
        "Voor één persoon: wis de tweede naam en wijs de schrijfwijzen toe aan de overblijvende persoon. Twee personen betekenen niet automatisch fiscaal partnerschap voor het hele jaar.",
    )
    SKIPPED: Final = Message(
        "Skipped",
        "Niet herkend",
    )
    SOURCE: Final = Message(
        "Source",
        "Bron",
    )
    STARTING_DASHBOARD: Final = Message(
        "Starting dashboard…",
        "Dashboard wordt gestart…",
    )
    STARTUP_TIMEOUT: Final = MessageTemplate(
        "Startup is taking too long. See {log}.",
        "Starten duurt te lang. Raadpleeg {log}.",
    )
    STATEMENT_RETURNS_HELP: Final = Message(
        "Statement returns follow account ownership; joint accounts are split equally for this view. Tax estimates use the filed fiscal-partner allocation of the combined return.",
        "Bronrendement volgt rekeningbezit; gezamenlijke rekeningen worden in deze weergave gelijk verdeeld. Belastingramingen gebruiken de fiscale verdeling uit de aangifte van het gezamenlijke rendement.",
    )
    STATEMENT_RETURN_BY_HOLDER: Final = Message(
        "Statement return by holder",
        "Bronrendement per rekeninghouder",
    )
    STATEMENT_SOURCES: Final = Message(
        "Statement sources",
        "Brongegevens uit overzichten",
    )
    STATUS: Final = Message(
        "Status",
        "Status",
    )
    STOPPED: Final = Message(
        "Stopped",
        "Gestopt",
    )
    STOP_IMPORT_AFTER_CURRENT_DOCUMENT: Final = Message(
        "Stop import after current document",
        "Import stoppen na huidig document",
    )
    STORAGE: Final = Message(
        "Storage",
        "Opslag",
    )
    TAXPAYER: Final = Message(
        "Taxpayer",
        "Belastingplichtige",
    )
    TAXPAYERS: Final = Message(
        "Taxpayers",
        "Belastingplichtigen",
    )
    TAXPAYER_DISCOVERY_HELP: Final = Message(
        "Tax returns identify primary taxpayers and fiscal partners. Other distinct account holders are suggested as minor children; review these guesses, especially missing adult returns and shared initials. Fiscal partnership and allocation come from each tax return.",
        "Aangiften identificeren belastingplichtigen en fiscale partners. Andere rekeninghouders worden voorgesteld als minderjarige kinderen; controleer deze suggesties, vooral bij ontbrekende aangiften van volwassenen en gedeelde initialen. Fiscaal partnerschap en verdeling volgen uit elke aangifte.",
    )
    TAXPAYER_PROFILES_HELP: Final = Message(
        "Taxpayer names and aliases are saved in this workspace and reused across sessions.",
        "Namen en aliassen van belastingplichtigen worden opgeslagen in deze werkruimte en hergebruikt.",
    )
    TAX_ALLOCATION: Final = Message(
        "Tax allocation",
        "Fiscale verdeling",
    )
    TAX_CERTIFICATE: Final = Message(
        "Tax certificate",
        "Belastingcertificaat",
    )
    TAX_YEAR: Final = Message(
        "Tax year",
        "Belastingjaar",
    )
    THE_DOCUMENT_FOLDER_DOES_NOT_EXIST_OR_IS_NOT_A_DIRECTORY: Final = Message(
        "The document folder does not exist or is not a directory.",
        "De documentenmap bestaat niet of is geen map.",
    )
    TOTAL: Final = Message(
        "Total",
        "Totaal",
    )
    UNASSIGNED: Final = Message(
        "Unassigned",
        "Niet toegewezen",
    )
    UNCLASSIFIED: Final = Message(
        "Unclassified",
        "Niet geclassificeerd",
    )
    UNKNOWN: Final = Message(
        "Unknown",
        "Onbekend",
    )
    VALUE_1_JANUARY: Final = Message(
        "Value 1 January",
        "Waarde op 1 januari",
    )
    VALUE_31_DECEMBER: Final = Message(
        "Value 31 December",
        "Waarde op 31 december",
    )
    VERSION_DETAILS: Final = MessageTemplate(
        "Version {version} · Local processing · Data: {directory}",
        "Versie {version} · Lokale verwerking · Gegevens: {directory}",
    )
    WERKELIJK_RENDEMENT_BOX_3: Final = Message(
        "Werkelijk rendement — Box 3",
        "Werkelijk rendement — Box 3",
    )
    WITHHOLDING_TAX: Final = Message(
        "Withholding tax",
        "Bronbelasting",
    )
    WORKSPACE: Final = MessageTemplate(
        "Workspace: {path}",
        "Werkruimte: {path}",
    )
    WORKSPACE_RESET_CHOOSE_A_DOCUMENT_FOLDER_TO_START_AGAIN: Final = Message(
        "Workspace reset. Choose a document folder to start again.",
        "Werkruimte opnieuw ingesteld. Kies een documentenmap om opnieuw te beginnen.",
    )
    WORKSPACE_SETTINGS_SAVED: Final = Message(
        "Workspace settings saved.",
        "Werkruimte-instellingen opgeslagen.",
    )
    YEAR: Final = Message(
        "Year",
        "Jaar",
    )
    YES: Final = Message(
        "Yes",
        "Ja",
    )
