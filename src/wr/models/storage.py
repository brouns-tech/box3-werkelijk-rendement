from __future__ import annotations

from enum import Enum
import json

from pydantic import Field, SerializeAsAny, field_validator

from wr.models.base import Record
from wr.models.facts import GainMethod, Ownership
from wr.models.metadata import FactMetadata
from wr.money import Currency


class FactRecord(Record):
    id: int = 0
    document_sha256: str = ""
    tax_year: int = 0
    issuer: str = ""
    account_key: str = ""
    account_label: str | None = None
    holder_names: list[str] = Field(default_factory=list)
    ownership: Ownership | None = Ownership.UNKNOWN
    currency: Currency = Currency.EUR
    start_balance: float | None = None
    end_balance: float | None = None
    deposits: float | None = None
    withdrawals: float | None = None
    interest_received: float | None = None
    interest_paid: float | None = None
    dividends_gross: float | None = None
    withholding_tax: float | None = None
    capital_gain: float | None = None
    gain_method: GainMethod | None = GainMethod.UNKNOWN
    logical_group: str | None = None
    is_canonical: bool = False
    extra: SerializeAsAny[FactMetadata] = Field(default_factory=FactMetadata)
    first_seen_path: str | None = None
    doc_type: str | None = None
    parse_status: str | None = None
    processing_profile: str | None = None

    @field_validator("holder_names", mode="before")
    @classmethod
    def decode_holders(cls, value: object) -> object:
        return json.loads(value or "[]") if isinstance(value, str) or value is None else value

    @field_validator("currency", mode="before")
    @classmethod
    def default_currency(cls, value: object) -> object:
        return Currency.EUR if value is None or value == "" else value


class FactWriteRecord(FactRecord):
    tax_year: int = Field(...)
    issuer: str = Field(..., min_length=1)
    account_key: str = Field(..., min_length=1)


class DocumentInput(Record):
    content_sha256: str
    byte_size: int
    imported_at: str
    page_count: int | None = None
    first_seen_path: str | None = None
    issuer: str | None = None
    doc_type: str | None = None
    tax_year: int | None = None
    raw_text_excerpt: str | None = None
    parse_status: str


class DocumentUpdate(Record):
    page_count: int | None = None
    issuer: str | None = None
    doc_type: str | None = None
    tax_year: int | None = None
    raw_text_excerpt: str | None = None
    parse_status: str | None = None
    processing_profile: str | None = None


class PortfolioRecord(Record):
    tax_year: int
    coverage_status: str
    known_combined_actual_return: float | None = None
    start_balance: float | None = None
    end_balance: float | None = None
    deposits: float | None = None
    withdrawals: float | None = None
    interest_received: float | None = None
    dividends_net: float | None = None
    dividends_gross: float | None = None
    withholding_tax: float | None = None
    capital_gain: float | None = None
    source_fact_count: int | None = None
    missing_asset_summary: str | None = None


class TaxReturnRecord(Record):
    id: int = 0
    document_sha256: str = ""
    tax_year: int
    filer_name: str | None = None
    full_year_fiscal_partners: bool = False
    partner_a_name: str | None = None
    partner_b_name: str | None = None
    bezittingen_0101: float | None = None
    bezittingen_3112: float | None = None
    schulden_0101: float | None = None
    schulden_3112: float | None = None
    heffingsvrij_vermogen: float | None = None
    grondslag: float | None = None
    grondslag_a: float | None = None
    grondslag_b: float | None = None
    allocation_a: float | None = None
    allocation_b: float | None = None
    allocation_status: str | None = None
    voordeel_a: float | None = None
    voordeel_b: float | None = None
    box3_tax_a: float | None = None
    box3_tax_b: float | None = None
    raw_text_excerpt: str | None = None


class MoneyField(str, Enum):
    START_BALANCE = "start_balance"
    END_BALANCE = "end_balance"
    DEPOSITS = "deposits"
    WITHDRAWALS = "withdrawals"
    INTEREST_RECEIVED = "interest_received"
    INTEREST_PAID = "interest_paid"
    DIVIDENDS_GROSS = "dividends_gross"
    WITHHOLDING_TAX = "withholding_tax"
    CAPITAL_GAIN = "capital_gain"
