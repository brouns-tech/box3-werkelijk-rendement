from __future__ import annotations

from dataclasses import dataclass


@dataclass
class CoverageResult:
    tax_year: int
    coverage_status: str
    known_combined_actual_return: float | None
    start_balance: float
    end_balance: float
    deposits: float
    withdrawals: float
    interest_received: float
    dividends_net: float
    capital_gain: float
    source_fact_count: int
    missing: list[str]
