from __future__ import annotations

from collections import defaultdict
import re

from pydantic import Field, field_validator

from wr.models import AccountYearFact, GainMethod, ParseResult
from wr.models.base import Record
from wr.models.metadata import FactMetadata
from wr.models.settings import InstitutionSettings
from wr.models.reconciliation import AttributeField, EvidenceStatus, FieldEvidence, ReconciledFact
from wr.models.storage import FactRecord, MoneyField
from wr.reconciliation.engine import account_key, derive_field, group_observations, reconcile_field, reconcile_group, set_field
from wr.money import add, subtract, total
from wr.parsers._text import normalize_iban, parse_nl_amount
from wr.parsers.base import (
    ClassificationRule,
    InstitutionPlugin,
    InstitutionSetting,
    ParserContext,
    ParserRegistration,
)
from wr.parsers.common import resolve_tax_year


class FlatexSettings(InstitutionSettings):
    linked_account: str | None = None

    @field_validator("linked_account")
    @classmethod
    def normalize_account(cls, value: str | None) -> str | None:
        return (value.strip() or None) if value is not None else None


class SecurityPosition(Record):
    isin: str
    market_value: float


class ReturnEvidence(Record):
    opening_balance: str
    external_flow_documents: int
    linked_account: str | None = None


class FlatexMetadata(FactMetadata):
    inventory_date: str | None = None
    cash_balance: float | None = None
    securities_account: str | None = None
    securities_market_value: float | None = None
    asset_class: str | None = None
    position_count: int | None = None
    positions: list[SecurityPosition] = Field(default_factory=list)
    linked_account: str | None = None
    statement_number: int = 0
    linked_transfer_count: int | None = None
    cash_sweep_count: int | None = None
    cash_sweep_deposits: float | None = None
    cash_sweep_withdrawals: float | None = None
    opening_statement: bool = False
    portfolio_return_basis: str | None = None
    securities_market_value_start: float | None = None
    securities_market_value_end: float | None = None
    securities_market_value_change: float | None = None
    return_derived_from: ReturnEvidence | None = None


def _is_tax_certificate(text: str) -> bool:
    return (
        "flatex" in text
        and "steuerbescheinigung" in text
        and "kunde:" in text
        and "kapitalerträge" in text
    )


def _is_financial_instruments_statement(text: str) -> bool:
    return (
        "flatex" in text
        and "lijst met financiële klanteninstrumenten en klantenfondsen" in text
        and "ingesloten vindt u de lijst voor 31.12." in text
        and "rekeningstand" in text
        and "effectenrekeningposities" in text
    )


def _is_account_statement(text: str) -> bool:
    return (
        "flatex" in text
        and "rekeninguittreksel nr:" in text
        and "rekeningnummer:" in text
        and "oud saldo van" in text
        and "nieuw saldo" in text
    )


def _parse_with_context(
    text: str, tax_year: int | None, context: ParserContext
) -> ParseResult:
    return parse_flatex(
        text,
        tax_year,
        context.doc_type,
        FlatexSettings.model_validate(context.options.model_dump()).linked_account,
    )


def parse_flatex(
    text: str,
    tax_year: int | None,
    doc_type: str,
    linked_account: str | None = None,
) -> ParseResult:
    if doc_type == "financial_instruments_statement":
        return _parse_financial_instruments_statement(text)
    if doc_type == "account_statement":
        normalized_account = normalize_iban(linked_account) if linked_account else None
        return _parse_account_statement(text, normalized_account)

    year = resolve_tax_year(text, tax_year)
    # Try period in Steuerbescheinigung
    if year is None:
        m = re.search(r"Zeitraum vom 01\.01\.(20\d{2}) bis 31\.12\.(20\d{2})", text)
        if m:
            year = int(m.group(1))

    if year is None:
        return ParseResult("flatex", doc_type, None, notes=["no year"])

    kunde = re.search(r"Kunde:\s*(\d+)", text)
    account_key = kunde.group(1) if kunde else f"flatex-{year}"

    # These certificates rarely give start/end portfolio for NL Box 3.
    kap = re.search(
        r"Kapitalerträge im Sinne[^\n]*\n[^\n]*?([\d.]+,\d{2})\s*EUR",
        text,
    )
    interest = parse_nl_amount(kap.group(1)) if kap else None

    fact = AccountYearFact(
        tax_year=year,
        issuer="flatex",
        account_key=account_key,
        account_label="flatex (legacy)",
        extra=FlatexMetadata(box3=True),
        holder_names=_holder_names(text),
        interest_received=interest,
        gain_method=GainMethod.INTEREST_ONLY if interest is not None else GainMethod.UNKNOWN,
        capital_gain=interest,
    )
    return ParseResult(
        "flatex",
        doc_type,
        year,
        facts=[fact],
        notes=["flatex tax certificate"],
    )


def _parse_financial_instruments_statement(text: str) -> ParseResult:
    snapshot = re.search(
        r"Ingesloten vindt u de lijst voor\s+(31\.12\.(20\d{2}))", text, re.I
    )
    if not snapshot:
        return ParseResult(
            "flatex",
            "financial_instruments_statement",
            None,
            notes=["missing 31 December inventory date"],
        )

    year = int(snapshot.group(2))
    account = re.search(r"Rekeningnummer\s*:\s*(\d+)", text, re.I)
    depot = re.search(r"Effectenrekeningnummer\s*:\s*(\d+)", text, re.I)
    cash = _amount_after(text, r"Rekeningstand\s*:\s*")
    positions = _positions(text)
    securities_value = round(sum(position.market_value for position in positions), 2)

    if account is None or cash is None or not positions:
        return ParseResult(
            "flatex",
            "financial_instruments_statement",
            year,
            notes=["incomplete financial-instruments inventory"],
        )

    account_key = account.group(1)
    fact = AccountYearFact(
        tax_year=year,
        issuer="flatex",
        account_key=account_key,
        account_label=f"flatex securities portfolio (cash and custody) {account_key}",
        holder_names=_holder_names(text),
        end_balance=round(cash + securities_value, 2),
        extra=FlatexMetadata(
            box3=True,
            inventory_date=snapshot.group(1),
            cash_balance=cash,
            securities_account=depot.group(1) if depot else None,
            securities_market_value=securities_value,
            asset_class="securities_portfolio",
            position_count=len(positions),
            positions=positions,
        ),
    )
    return ParseResult(
        "flatex",
        "financial_instruments_statement",
        year,
        facts=[fact],
    )


def _amount_after(text: str, label_pattern: str) -> float | None:
    m = re.search(label_pattern + r"([\d.]+,\d{2})\s*EUR", text, re.I)
    return parse_nl_amount(m.group(1)) if m else None


def _positions(text: str) -> list[SecurityPosition]:
    positions = []
    for match in re.finditer(
        r"^\s*([A-Z]{2}[A-Z0-9]{10})\*{0,4}\s+([\d.]+,\d{2})\s*EUR\s*$",
        text,
        re.M,
    ):
        market_value = parse_nl_amount(match.group(2))
        if market_value is not None:
            positions.append(SecurityPosition(isin=match.group(1), market_value=market_value))
    return positions


def _parse_account_statement(text: str, linked_account: str | None) -> ParseResult:
    statement = re.search(r"Rekeninguittreksel nr:\s*\d+/(20\d{2})", text, re.I)
    account = re.search(r"Rekeningnummer\s*:\s*(\d+)", text, re.I)
    if statement is None or account is None:
        return ParseResult(
            "flatex", "account_statement", None, notes=["missing statement year or account"]
        )

    statement_number = int(re.search(r"\d+", statement.group(0)).group(0))
    year = int(statement.group(1))
    opening = re.search(
        r"Oud saldo van\s+(\d{2}\.\d{2}\.20\d{2}).*?([\d.]+,\d{2})([+-])",
        text,
        re.I | re.S,
    )
    opening_balance = None
    opening_statement = False
    if opening:
        opening_balance = parse_nl_amount(opening.group(2))
        if opening.group(3) == "-" and opening_balance and opening_balance > 0:
            opening_balance = -opening_balance
        opening_statement = (
            statement_number == 1
            and opening.group(1).endswith(str(year))
            and opening_balance == 0.0
        )

    linked_deposits, linked_withdrawals, linked_count = _linked_account_transfers(
        text, linked_account
    )
    sweep_deposits, sweep_withdrawals, sweep_count = _cash_sweep_transfers(text)
    end_balance = _closing_balance(text)
    account_label = f"flatex cash account {account.group(1)}"
    fact = AccountYearFact(
        tax_year=year,
        issuer="flatex",
        account_key=account.group(1),
        account_label=account_label,
        holder_names=_holder_names(text),
        start_balance=opening_balance if opening_statement else None,
        end_balance=end_balance,
        deposits=linked_deposits,
        withdrawals=linked_withdrawals,
        capital_gain=0.0,
        gain_method=GainMethod.EXPLICIT,
        extra=FlatexMetadata(
            box3=True,
            linked_account=linked_account,
            statement_number=statement_number,
            linked_transfer_count=linked_count,
            cash_sweep_count=sweep_count,
            cash_sweep_deposits=sweep_deposits,
            cash_sweep_withdrawals=sweep_withdrawals,
            opening_statement=opening_statement,
            return_assumption="zero_by_product",
        ),
    )
    return ParseResult("flatex", "account_statement", year, facts=[fact])


def _holder_names(text: str) -> list[str]:
    match = re.search(r"(?:De heer|Mevrouw)\s*\n\s*([A-Z][A-Z .'-]{3,80})", text)
    return [match.group(1).strip()] if match else []


def _linked_account_transfers(
    text: str, linked_account: str | None
) -> tuple[float, float, int]:
    deposits = 0.0
    withdrawals = 0.0
    count = 0
    for match in re.finditer(
        r"^\s*\d{2}\.\d{2}\.\s+.*?(?:Überweisung|Overboeking)\s+"
        r"(-?[\d.]+,\d{2})([+-])\s*$",
        text,
        re.I | re.M,
    ):
        next_transaction = re.search(
            r"^\s*\d{2}\.\d{2}\.", text[match.end() :], re.M
        )
        details_end = (
            match.end() + next_transaction.start()
            if next_transaction
            else len(text)
        )
        details = text[match.end() : details_end]
        if not linked_account or linked_account not in details.replace(" ", ""):
            continue
        amount = parse_nl_amount(match.group(1))
        if amount is None:
            continue
        if match.group(2) == "-" and amount > 0:
            amount = -amount
        if amount >= 0:
            deposits += amount
        else:
            withdrawals += abs(amount)
        count += 1
    return round(deposits, 2), round(withdrawals, 2), count


def _cash_sweep_transfers(text: str) -> tuple[float, float, int]:
    deposits = 0.0
    withdrawals = 0.0
    count = 0
    for match in re.finditer(
        r"^\s*\d{2}\.\d{2}\.\s+.*?Cash Sweep\s+"
        r"(-?[\d.]+,\d{2})([+-])\s*$",
        text,
        re.I | re.M,
    ):
        amount = parse_nl_amount(match.group(1))
        if amount is None:
            continue
        if match.group(2) == "-" and amount > 0:
            amount = -amount
        if amount >= 0:
            deposits += amount
        else:
            withdrawals += abs(amount)
        count += 1
    return round(deposits, 2), round(withdrawals, 2), count


def _closing_balance(text: str) -> float | None:
    closing = re.search(
        r"Nieuw saldo\s+\d{2}\.\d{2}\.20\d{2}.*?([\d.]+,\d{2})([+-])",
        text,
        re.I | re.S,
    )
    if not closing:
        return None
    balance = parse_nl_amount(closing.group(1))
    if closing.group(2) == "-" and balance and balance > 0:
        return -balance
    return balance


def _reconcile(observations: list[FactRecord], options: InstitutionSettings) -> list[ReconciledFact]:
    results: list[ReconciledFact] = []
    inventories = [row for row in observations if row.doc_type == "financial_instruments_statement"]
    for group in group_observations(observations):
        inventory = [row for row in group if row.doc_type == "financial_instruments_statement"]
        statements = [row for row in group if row.doc_type == "account_statement"]
        if not inventory:
            if statements:
                latest = max(_metadata(row).statement_number for row in statements)
                group = [row for row in statements if _metadata(row).statement_number == latest]
            result = reconcile_group(group)
            if statements and result.gain_method == GainMethod.BALANCE_FLOW:
                set_field(result, FieldEvidence(field=MoneyField.CAPITAL_GAIN, status=EvidenceStatus.DERIVED,
                                               rule="cash_statement_is_not_portfolio_return"))
                set_field(result, FieldEvidence(field=AttributeField.GAIN_METHOD, status=EvidenceStatus.DERIVED,
                                               value=GainMethod.UNKNOWN.value,
                                               rule="cash_statement_is_not_portfolio_return"))
            results.append(result)
            continue
        result = reconcile_group(inventory)
        for field in (AttributeField.HOLDERS, AttributeField.OWNERSHIP, AttributeField.BOX3, AttributeField.CURRENCY):
            set_field(result, reconcile_field(group, field))
        previous = [row for row in inventories if row.tax_year == result.tax_year - 1
                    and account_key(row.account_key) == account_key(result.account_key)]
        opening = reconcile_field(previous, MoneyField.END_BALANCE) if previous else reconcile_field(
            [row for row in statements if _metadata(row).opening_statement], MoneyField.START_BALANCE)
        opening_currency = reconcile_field(inventory + previous, AttributeField.CURRENCY)
        derive_field(result, MoneyField.START_BALANCE, opening.value, [opening, opening_currency],
                     "prior_year_inventory" if previous else "opening_account_statement")
        flows: dict[int, list[FactRecord]] = defaultdict(list)
        for row in statements:
            flows[_metadata(row).statement_number].append(row)
        for field in (MoneyField.DEPOSITS, MoneyField.WITHDRAWALS):
            periods = [reconcile_field(rows, field) for rows in flows.values()]
            value = total(item.value for item in periods if item.value is not None) if periods and all(
                item.value is not None for item in periods) else None
            numbered_periods = sorted(number for number in flows if number > 0)
            gaps = numbered_periods and numbered_periods != list(range(1, numbered_periods[-1] + 1))
            derive_field(result, field, None if gaps else value, periods,
                         "missing_statement_periods" if gaps else "sum_distinct_statement_periods")
        inputs = [item for item in result.evidence if item.field in {
            MoneyField.START_BALANCE, MoneyField.END_BALANCE, MoneyField.DEPOSITS, MoneyField.WITHDRAWALS,
        }]
        complete = all(item.value is not None for item in inputs)
        capital = add(subtract(result.end_balance, result.start_balance, result.deposits), result.withdrawals) if complete else None
        derive_field(result, MoneyField.CAPITAL_GAIN, capital, inputs, "portfolio_valuation_minus_external_flows")
        derive_field(result, AttributeField.GAIN_METHOD, GainMethod.BALANCE_FLOW.value if complete else GainMethod.UNKNOWN.value,
                     inputs, "portfolio_valuation_minus_external_flows")
        extra = _metadata(inventory[0]).model_copy(deep=True)
        extra.portfolio_return_basis = "year-end securities-and-cash valuation adjusted only for external transfers"
        extra.return_derived_from = ReturnEvidence(
            opening_balance="prior_31_december_inventory" if previous else "opening_account_statement",
            external_flow_documents=len(statements),
            linked_account=FlatexSettings.model_validate(options.model_dump()).linked_account,
        )
        result.extra = extra
        box3 = next(item for item in result.evidence if item.field == AttributeField.BOX3)
        result.extra.box3 = box3.value if isinstance(box3.value, bool) else True
        results.append(result)
    return results


def _metadata(row: FactRecord) -> FlatexMetadata:
    return FlatexMetadata.model_validate(row.extra.model_dump())


PLUGIN = InstitutionPlugin(
    issuer="flatex",
    metadata_model=FlatexMetadata,
    options_model=FlatexSettings,
    classification_rules=(
        ClassificationRule("flatex", "belastingcertificaat", _is_tax_certificate),
        ClassificationRule(
            "flatex",
            "financial_instruments_statement",
            _is_financial_instruments_statement,
        ),
        ClassificationRule("flatex", "account_statement", _is_account_statement),
    ),
    parsers={
        "financial_instruments_statement": ParserRegistration(_parse_with_context),
        "account_statement": ParserRegistration(_parse_with_context),
        "belastingcertificaat": ParserRegistration(_parse_with_context),
    },
    reconcile=_reconcile,
    settings_fields=(
        InstitutionSetting("linked_account", "Linked bank account (IBAN)", "Used to identify external transfers in flatex account statements."),
    ),
)
