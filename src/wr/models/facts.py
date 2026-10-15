from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from wr.models.metadata import FactMetadata
from wr.money import Currency, add, subtract


class CoverageStatus(str, Enum):
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    MISSING = "MISSING"
    UNKNOWN = "UNKNOWN"


class ParseStatus(str, Enum):
    PARSED = "parsed"
    SKIPPED = "skipped"
    FAILED = "failed"


class Ownership(str, Enum):
    UNKNOWN = "unknown"
    INDIVIDUAL = "individual"
    JOINT = "joint"


class GainMethod(str, Enum):
    UNKNOWN = "unknown"
    INTEREST_ONLY = "interest_only"
    BALANCE_DELTA_INCOMPLETE = "balance_delta_incomplete"
    BALANCE_FLOW = "balance_flow"
    EXPLICIT = "explicit"
    EARNED_RETURN = "earned_return"


@dataclass
class AccountYearFact:
    tax_year: int
    issuer: str
    account_key: str
    account_label: str
    holder_names: list[str] = field(default_factory=list)
    ownership: Ownership = Ownership.UNKNOWN
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
    gain_method: GainMethod = GainMethod.UNKNOWN
    logical_group: str | None = None
    extra: FactMetadata = field(default_factory=FactMetadata)

    def __post_init__(self) -> None:
        self.ownership = Ownership(self.ownership)
        self.gain_method = GainMethod(self.gain_method)
        self.currency = Currency(self.currency)
        if not isinstance(self.extra, FactMetadata):
            self.extra = FactMetadata.model_validate(self.extra)

    def compute_capital_gain(self) -> None:
        if self.capital_gain is not None:
            return
        if self.start_balance is None or self.end_balance is None:
            if self.interest_received is not None and self.deposits is None:
                self.capital_gain = subtract(
                    self.interest_received or 0.0, self.interest_paid or 0.0
                )
                self.gain_method = GainMethod.INTEREST_ONLY
            return
        deposits = self.deposits if self.deposits is not None else 0.0
        withdrawals = self.withdrawals if self.withdrawals is not None else 0.0
        # If cashflows unknown, still compute balance delta but mark method.
        if self.deposits is None and self.withdrawals is None:
            # Prefer interest-only when interest is known and we lack flows.
            if self.interest_received is not None:
                self.capital_gain = subtract(
                    self.interest_received or 0.0, self.interest_paid or 0.0
                )
                self.gain_method = GainMethod.INTEREST_ONLY
                return
            self.capital_gain = subtract(self.end_balance, self.start_balance)
            self.gain_method = GainMethod.BALANCE_DELTA_INCOMPLETE
            return
        balance_flow_return = add(
            subtract(self.end_balance, self.start_balance, deposits), withdrawals
        )
        net_interest = subtract(
            self.interest_received or 0.0, self.interest_paid or 0.0
        )
        net_dividends = subtract(
            self.dividends_gross or 0.0, self.withholding_tax or 0.0
        )
        # The balance movement already contains cash income after withholding.
        # Keep market value change separate so gross dividends can be included
        # exactly once in taxable actual return.
        self.capital_gain = subtract(balance_flow_return, net_interest, net_dividends)
        self.gain_method = GainMethod.BALANCE_FLOW

    @property
    def actual_return_component(self) -> float | None:
        """Contribution to combined actual return for this fact."""
        if (
            self.gain_method == GainMethod.BALANCE_FLOW
            and self.start_balance is not None
            and self.end_balance is not None
            and self.deposits is not None
            and self.withdrawals is not None
        ):
            return (
                self.end_balance
                - self.start_balance
                - self.deposits
                + self.withdrawals
                + (self.dividends_gross or 0.0)
                + (self.interest_received or 0.0)
                - (self.interest_paid or 0.0)
            )
        parts: list[float] = []
        if self.interest_received is not None or self.interest_paid is not None:
            parts.append(
                subtract(self.interest_received or 0.0, self.interest_paid or 0.0)
            )
        if self.dividends_gross is not None:
            parts.append(self.dividends_gross)
        if self.gain_method == GainMethod.INTEREST_ONLY:
            # Already counted via interest above.
            pass
        elif self.capital_gain is not None and self.gain_method in (
            GainMethod.BALANCE_FLOW,
            GainMethod.EXPLICIT,
            GainMethod.EARNED_RETURN,
        ):
            # For investments, capital_gain is market value change net of flows
            # and separately reported income.
            if self.gain_method == GainMethod.EARNED_RETURN:
                parts = [self.capital_gain]
            else:
                parts.append(self.capital_gain)
        if not parts:
            return None
        return add(*parts)
