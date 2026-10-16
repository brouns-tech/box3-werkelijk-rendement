from __future__ import annotations

from dataclasses import dataclass, field

from wr.models.facts import AccountYearFact
from wr.models.tax import TaxReturnData


@dataclass
class ParseResult:
    issuer: str
    doc_type: str
    tax_year: int | None = None
    facts: list[AccountYearFact] = field(default_factory=list)
    tax_return: TaxReturnData | None = None
    notes: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        for fact in self.facts:
            if "box3" not in fact.extra.model_fields_set:
                raise ValueError(f"Parser {self.issuer} must explicitly classify Box 3 treatment for {fact.account_key}")


@dataclass(frozen=True)
class Classification:
    issuer: str
    doc_type: str
    confidence: float = 1.0
