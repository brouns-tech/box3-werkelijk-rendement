from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class CoverageStatus(str, Enum):
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    MISSING = "MISSING"
    UNKNOWN = "UNKNOWN"


class Recommendation(str, Enum):
    ACTUAL_BETTER = "ACTUAL_BETTER"
    FICTITIOUS_BETTER = "FICTITIOUS_BETTER"
    EQUAL = "EQUAL"
    INDETERMINATE_MISSING_DATA = "INDETERMINATE_MISSING_DATA"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    NEEDS_MANUAL_RSAMW = "NEEDS_MANUAL_RSAMW"


class ParseStatus(str, Enum):
    PARSED = "parsed"
    SKIPPED = "skipped"
    FAILED = "failed"


@dataclass
class AccountYearFact:
    tax_year: int
    issuer: str
    account_key: str
    account_label: str
    holder_names: list[str] = field(default_factory=list)
    ownership: str = "unknown"
    currency: str = "EUR"
    start_balance: float | None = None
    end_balance: float | None = None
    deposits: float | None = None
    withdrawals: float | None = None
    interest_received: float | None = None
    interest_paid: float | None = None
    dividends_gross: float | None = None
    withholding_tax: float | None = None
    capital_gain: float | None = None
    gain_method: str = "unknown"
    logical_group: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def compute_capital_gain(self) -> None:
        if self.capital_gain is not None:
            return
        if self.start_balance is None or self.end_balance is None:
            if self.interest_received is not None and self.deposits is None:
                self.capital_gain = (self.interest_received or 0.0) - (self.interest_paid or 0.0)
                self.gain_method = "interest_only"
            return
        deposits = self.deposits if self.deposits is not None else 0.0
        withdrawals = self.withdrawals if self.withdrawals is not None else 0.0
        # If cashflows unknown, still compute balance delta but mark method.
        if self.deposits is None and self.withdrawals is None:
            # Prefer interest-only when interest is known and we lack flows.
            if self.interest_received is not None:
                self.capital_gain = (self.interest_received or 0.0) - (self.interest_paid or 0.0)
                self.gain_method = "interest_only"
                return
            self.capital_gain = self.end_balance - self.start_balance
            self.gain_method = "balance_delta_incomplete"
            return
        self.capital_gain = self.end_balance - self.start_balance - deposits + withdrawals
        self.gain_method = "balance_flow"

    @property
    def actual_return_component(self) -> float | None:
        """Contribution to combined actual return for this fact."""
        parts: list[float] = []
        if self.interest_received is not None or self.interest_paid is not None:
            parts.append((self.interest_received or 0.0) - (self.interest_paid or 0.0))
        if self.dividends_gross is not None:
            # Net of withholding for economic return; withholding is separately reclaimable.
            parts.append(self.dividends_gross - (self.withholding_tax or 0.0))
        if self.gain_method == "interest_only":
            # Already counted via interest above.
            pass
        elif self.capital_gain is not None and self.gain_method in (
            "balance_flow",
            "explicit",
            "earned_return",
        ):
            # For investments, capital_gain is the value change net of flows.
            # Avoid double-counting interest/dividends if they are already in capital_gain.
            if self.gain_method == "earned_return":
                parts = [self.capital_gain]
            elif self.interest_received is None and self.dividends_gross is None:
                parts.append(self.capital_gain)
            elif self.dividends_gross is not None or self.interest_received is not None:
                # capital_gain from balance_flow already embeds income; use it alone.
                parts = [self.capital_gain]
        if not parts:
            return None
        return sum(parts)


@dataclass
class DeclaredBox3Asset:
    tax_year: int
    category: str
    institution: str
    account_id: str
    label: str
    balance_0101: float | None = None
    balance_3112: float | None = None
    coverage_status: str = CoverageStatus.UNKNOWN.value


@dataclass
class TaxReturnData:
    tax_year: int
    filer_name: str
    full_year_fiscal_partners: bool
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
    voordeel_a: float | None = None
    voordeel_b: float | None = None
    box3_tax_a: float | None = None
    box3_tax_b: float | None = None
    assets: list[DeclaredBox3Asset] = field(default_factory=list)
    allocation_status: str = "ok"

    @property
    def allocation_a(self) -> float | None:
        if self.grondslag is None or self.grondslag == 0:
            return None
        if self.grondslag_a is None:
            return None
        return abs(self.grondslag_a) / abs(self.grondslag)

    @property
    def allocation_b(self) -> float | None:
        if self.grondslag is None or self.grondslag == 0:
            return None
        if self.grondslag_b is None:
            return None
        return abs(self.grondslag_b) / abs(self.grondslag)


@dataclass
class ParseResult:
    issuer: str
    doc_type: str
    tax_year: int | None = None
    facts: list[AccountYearFact] = field(default_factory=list)
    tax_return: TaxReturnData | None = None
    notes: list[str] = field(default_factory=list)


@dataclass
class PartnerTaxResult:
    tax_year: int
    partner: str
    partner_name: str
    allocation_ratio: float | None
    allocated_actual_return: float | None
    fictitious_return: float | None
    estimated_box3_tax_actual: float | None
    estimated_box3_tax_fictitious: float | None
    recommendation: str
    coverage_status: str
    notes: str = ""
