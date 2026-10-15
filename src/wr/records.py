from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, SerializeAsAny, StrictBool, ValidationInfo, field_validator

from wr.money import Currency


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True, allow_inf_nan=False)


class FactMetadata(Record):
    synthetic: bool | None = None
    box3: StrictBool | None = None
    account_type: str | None = None
    interest_source: str | None = None
    return_assumption: str | None = None


class InstitutionSettings(Record):
    model_config = ConfigDict(extra="allow")
    __pydantic_extra__: dict[str, JsonValue] = Field(init=False)


def parse_institution_settings(issuer: str, value: object) -> InstitutionSettings:
    from wr.parsers import PLUGINS

    model = next((plugin.options_model for plugin in PLUGINS if plugin.issuer == issuer), InstitutionSettings)
    if isinstance(value, model):
        return value
    if isinstance(value, BaseModel):
        value = value.model_dump(exclude_unset=True)
    return model.model_validate(value if value is not None else {})


def parse_metadata(issuer: str, value: object) -> FactMetadata:
    from wr.parsers import PLUGINS

    model = next((plugin.metadata_model for plugin in PLUGINS if plugin.issuer == issuer), FactMetadata)
    if isinstance(value, model):
        return value
    if isinstance(value, BaseModel):
        value = value.model_dump(exclude_unset=True)
    if isinstance(value, str):
        return model.model_validate_json(value)
    return model.model_validate(value if value is not None else {})


class FactRecord(Record):
    id: int = 0
    document_sha256: str = ""
    tax_year: int = 0
    issuer: str = ""
    account_key: str = ""
    account_label: str | None = None
    holder_names: list[str] = Field(default_factory=list)
    ownership: str | None = "unknown"
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
    gain_method: str | None = "unknown"
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

    @field_validator("extra", mode="before")
    @classmethod
    def decode_metadata(cls, value: object, info: ValidationInfo) -> FactMetadata:
        return parse_metadata(info.data.get("issuer", ""), {} if value is None or value == "" else value)

    @field_validator("currency", mode="before")
    @classmethod
    def default_currency(cls, value: object) -> object:
        return Currency.EUR if value is None or value == "" else value

    @classmethod
    def from_row(cls, row: sqlite3.Row | Mapping[str, object] | FactRecord) -> FactRecord:
        return row if isinstance(row, cls) else cls.model_validate(dict(row))


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


MoneyField = Literal["start_balance", "end_balance", "deposits", "withdrawals", "interest_received", "interest_paid", "dividends_gross", "withholding_tax", "capital_gain"]
