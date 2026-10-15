from __future__ import annotations

from wr.models.base import Record
from wr.models.facts import GainMethod, Ownership
from wr.money import Currency


class YearSummary(Record):
    tax_year: int
    coverage_status: str | None = None
    start_capital_from_sources: float | None = None
    end_capital_from_sources: float | None = None
    deposits: float | None = None
    withdrawals: float | None = None
    net_interest: float | None = None
    dividends_gross: float | None = None
    withholding_tax: float | None = None
    net_dividends: float | None = None
    market_value_change: float | None = None
    actual_return_used: float | None = None
    source_fact_count: int | None = None
    missing_asset_summary: str | None = None
    declared_assets_0101: float | None = None
    declared_assets_3112: float | None = None
    declared_debts_0101: float | None = None
    declared_debts_3112: float | None = None
    taxable_base: float | None = None
    estimated_household_tax_savings: float | None = None


class AssetExportRow(Record):
    tax_year: int
    asset_id: int | str
    category: str
    institution: str
    account_id: str
    label: str | None
    coverage_status: str
    declared_start_capital: float | None
    declared_end_capital: float | None
    source_start_capital: float | None
    source_end_capital: float | None
    deposits: float | None
    withdrawals: float | None
    interest_received: float | None
    interest_paid: float | None
    net_interest: float | None
    dividends_gross: float | None
    withholding_tax: float | None
    net_dividends: float | None
    market_value_change: float | None
    actual_return_from_sources: float | None
    return_used: float
    currency: Currency | None = None
    native_actual_return: float | None = None
    return_basis: str
    matched_fact_ids: int | str
    included_fact_ids: int | str
    source_document_sha256s: str
    source_paths: str | None


class SourceFactExportRow(Record):
    tax_year: int
    fact_id: int
    issuer: str
    account_key: str
    account_label: str | None
    holder_names: str
    ownership: Ownership | None
    currency: Currency
    start_capital: float | None
    end_capital: float | None
    deposits: float | None
    withdrawals: float | None
    interest_received: float | None
    interest_paid: float | None
    dividends_gross: float | None
    withholding_tax: float | None
    capital_gain: float | None
    gain_method: GainMethod | None
    calculated_actual_return: float | None
    native_actual_return: float | None
    has_usable_actual_return: bool
    matched_asset_ids: str
    primary_asset_id: int | None
    included_in_year_total: bool
    exclusion_reason: str | None
    document_sha256: str
    source_path: str | None
    processing_profile: str | None
    document_type: str | None
    parse_status: str | None
    extra: str


class PartnerTaxExportRow(Record):
    tax_year: int
    partner: str
    partner_name: str | None
    allocation_ratio: float | None
    allocated_actual_return: float | None
    fictitious_return: float | None
    estimated_box3_tax_actual: float | None
    estimated_box3_tax_fictitious: float | None
    estimated_tax_savings: float | None
    recommendation: str
    coverage_status: str
    notes: str | None


class AuditManifest(Record):
    format: str = "werkelijk-rendement-audit"
    version: int = 1
    pending_pdf_reprocessing: int
    document_processing_profiles: list[str]
    generated_at_utc: str
    tax_years: list[int]
    files: dict[str, str]
    calculation_notes: list[str]
