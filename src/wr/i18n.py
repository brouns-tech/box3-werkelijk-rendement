"""Presentation-only localization. Stored facts and audit exports keep stable identifiers."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from wr.messages import Message, Messages, MessageTemplate
from wr.money import Currency

LANGUAGES = {"nl": "Nederlands", "en": "English"}


@dataclass(frozen=True)
class Translator:
    language: str

    def __post_init__(self) -> None:
        if self.language not in LANGUAGES:
            raise ValueError(f"Unsupported language: {self.language}")

    def __call__(self, message: Message) -> str:
        if not isinstance(message, Message):
            raise TypeError("Expected a Message; use a typed method for parameterized messages")
        return message.nl if self.language == "nl" else message.en

    def _format(self, template: MessageTemplate, **values: object) -> str:
        text = template.nl if self.language == "nl" else template.en
        return text.format(**values)

    def cannot_browse_folder(self, *, error: str | Exception) -> str:
        return self._format(Messages.CANNOT_BROWSE_FOLDER, error=error)

    def child(self, *, number: int) -> str:
        return self._format(Messages.CHILD, number=number)

    def child_name_placeholder(self, *, number: int) -> str:
        return self._format(Messages.CHILD_NAME_PLACEHOLDER, number=number)

    def could_not_open(self, *, target: str | Path, error: str | Exception) -> str:
        return self._format(Messages.COULD_NOT_OPEN, target=target, error=error)

    def could_not_reset_workspace(self, *, error: str | Exception) -> str:
        return self._format(Messages.COULD_NOT_RESET_WORKSPACE, error=error)

    def could_not_save_language_preference(self, *, error: str | Exception) -> str:
        return self._format(Messages.COULD_NOT_SAVE_LANGUAGE_PREFERENCE, error=error)

    def could_not_save_workspace_settings(self, *, error: str | Exception) -> str:
        return self._format(Messages.COULD_NOT_SAVE_WORKSPACE_SETTINGS, error=error)

    def dashboard_stopped(self, *, log: str | Path) -> str:
        return self._format(Messages.DASHBOARD_STOPPED, log=log)

    def database(self, *, name: str) -> str:
        return self._format(Messages.DATABASE, name=name)

    def folder_selection_failed(self, *, error: str | Exception) -> str:
        return self._format(Messages.FOLDER_SELECTION_FAILED, error=error)

    def import_failed(self, *, error: str | Exception) -> str:
        return self._format(Messages.IMPORT_FAILED, error=error)

    def import_finished(self, *, parsed: int, duplicate: int, skipped: int, failed: int) -> str:
        return self._format(Messages.IMPORT_FINISHED, parsed=parsed, duplicate=duplicate, skipped=skipped, failed=failed)

    def import_result(self, *, status: str, parsed: int, duplicate: int, skipped: int, failed: int) -> str:
        return self._format(Messages.IMPORT_RESULT, status=status, parsed=parsed, duplicate=duplicate, skipped=skipped, failed=failed)

    def instance_starting_log(self, *, log: str | Path) -> str:
        return self._format(Messages.INSTANCE_STARTING_LOG, log=log)

    def missing_partial(self, *, details: str) -> str:
        return self._format(Messages.MISSING_PARTIAL, details=details)

    def pdf_extraction_updated(self, *, count: int) -> str:
        return self._format(Messages.PDF_EXTRACTION_UPDATED, count=count)

    def selected_folder(self, *, folder: str | Path) -> str:
        return self._format(Messages.SELECTED_FOLDER, folder=folder)

    def startup_timeout(self, *, log: str | Path) -> str:
        return self._format(Messages.STARTUP_TIMEOUT, log=log)

    def version_details(self, *, version: str, directory: str | Path) -> str:
        return self._format(Messages.VERSION_DETAILS, version=version, directory=directory)

    def workspace(self, *, path: str | Path) -> str:
        return self._format(Messages.WORKSPACE, path=path)


def translator(language: str) -> Translator:
    return Translator(language)


def translate(language: str, message: Message) -> str:
    return translator(language)(message)


def currency(value: float | None, language: str = "en", currency_code: Currency | str = Currency.EUR) -> str:
    code = Currency(currency_code)
    if value is None:
        return "—"
    number = f"{value:,.2f}"
    if language == "nl":
        number = number.translate(str.maketrans({",": ".", ".": ","}))
    return f"{code.symbol} {number}"


STATUS_MESSAGES = {
    "ACTUAL_BETTER": Messages.ACTUAL_RETURN_BETTER,
    "COMPLETE": Messages.AVAILABLE_EVIDENCE,
    "EQUAL": Messages.NO_MATERIAL_DIFFERENCE,
    "FICTITIOUS_BETTER": Messages.FICTITIOUS_RETURN_BETTER,
    "INDETERMINATE_MISSING_DATA": Messages.INCOMPLETE_DATA,
    "MISSING": Messages.MISSING,
    "NEEDS_MANUAL_RSAMW": Messages.MANUAL_REVIEW_NEEDED,
    "NOT_APPLICABLE": Messages.NOT_APPLICABLE,
    "PARTIAL": Messages.PARTIAL,
    "UNKNOWN": Messages.UNKNOWN,
    "aangifte_ib": Messages.INCOME_TAX_RETURN,
    "account_statement": Messages.ACCOUNT_STATEMENT,
    "balance_delta_incomplete": Messages.INCOMPLETE_BALANCE_CHANGE,
    "balance_flow": Messages.BALANCE_AND_CASH_FLOWS,
    "belastingcertificaat": Messages.TAX_CERTIFICATE,
    "definitieve_aanslag": Messages.FINAL_ASSESSMENT,
    "duplicate": Messages.DUPLICATE,
    "earned_return": Messages.REPORTED_RETURN,
    "explicit": Messages.EXPLICIT_VALUES,
    "failed": Messages.FAILED,
    "financial_instruments_statement": Messages.SECURITIES_AND_CASH_INVENTORY,
    "interest_only": Messages.INTEREST_ONLY,
    "jaaroverzicht": Messages.ANNUAL_STATEMENT,
    "other": Messages.OTHER,
    "parsed": Messages.PARSED,
    "savings_statement": Messages.SAVINGS_STATEMENT,
    "skipped": Messages.SKIPPED,
    "steuerbescheinigung": Messages.TAX_CERTIFICATE,
    "totaaloverzicht": Messages.ACCOUNT_INVENTORY,
    "unclassified": Messages.UNCLASSIFIED,
    "unknown": Messages.UNKNOWN,
}


def status_label(value: str | None, language: str) -> str:
    if not value:
        return "—"
    message = STATUS_MESSAGES.get(value)
    return translate(language, message) if message is not None else value


def coverage_details(value: str, language: str) -> str:
    # Translate only known generated messages, never account identifiers or source text.
    messages = []
    suffix = " (no actual-return fields)"
    for entry in value.split("; "):
        if entry == "no reconciled Box 3 statements for this year":
            entry = translate(language, Messages.NO_RECONCILED_BOX_3_STATEMENTS_FOR_THIS_YEAR)
        elif entry.endswith(" (conflicting source evidence)"):
            entry = entry[:-len(" (conflicting source evidence)")] + " (" + translate(language, Messages.CONFLICTING_SOURCE_EVIDENCE) + ")"
        elif entry.endswith(suffix):
            entry = entry[:-len(suffix)] + " (" + translate(language, Messages.NO_ACTUAL_RETURN_FIELDS) + ")"
        elif entry.endswith(" (requires EUR conversion and currency gain/loss)"):
            entry = entry[:-len(" (requires EUR conversion and currency gain/loss)")] + " (" + translate(language, Messages.REQUIRES_EUR_CONVERSION_AND_CURRENCY_GAIN_LOSS) + ")"
        messages.append(entry)
    return "; ".join(messages)
