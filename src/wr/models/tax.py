from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum

from wr.models.identities import TaxpayerPosition


class Recommendation(str, Enum):
    ACTUAL_BETTER = "ACTUAL_BETTER"
    FICTITIOUS_BETTER = "FICTITIOUS_BETTER"
    EQUAL = "EQUAL"
    INDETERMINATE_MISSING_DATA = "INDETERMINATE_MISSING_DATA"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    NEEDS_MANUAL_RSAMW = "NEEDS_MANUAL_RSAMW"


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
class TaxpayerTaxResult:
    tax_year: int
    taxpayer_position: TaxpayerPosition
    taxpayer_name: str
    allocation_ratio: float | None
    allocated_actual_return: float | None
    fictitious_return: float | None
    estimated_box3_tax_actual: float | None
    estimated_box3_tax_fictitious: float | None
    estimated_tax_savings: float | None
    recommendation: str
    coverage_status: str
    notes: str = ""

    def __post_init__(self) -> None:
        self.taxpayer_position = TaxpayerPosition(self.taxpayer_position)


@dataclass(frozen=True)
class TaxPolicy:
    year: int
    box3_rate: Decimal
    era: str


@dataclass
class CompareOutcome:
    recommendation: str
    estimated_tax_actual: float | None
    estimated_tax_savings: float | None
    notes: str
