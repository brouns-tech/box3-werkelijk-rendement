from __future__ import annotations

from enum import Enum

from pydantic import Field, JsonValue

from wr.models.base import Record
from wr.models.storage import FactValues, MoneyField


class AttributeField(str, Enum):
    HOLDERS = "holder_names"
    OWNERSHIP = "ownership"
    CURRENCY = "currency"
    BOX3 = "box3"
    LABEL = "account_label"
    GAIN_METHOD = "gain_method"


class EvidenceStatus(str, Enum):
    MISSING = "missing"
    SINGLE_SOURCE = "single_source"
    AGREEMENT = "agreement"
    CONFLICT = "conflict"
    DERIVED = "derived"


class SourceEvidence(Record):
    fact_id: int
    document_sha256: str
    field: MoneyField | AttributeField
    value: JsonValue


class FieldEvidence(Record):
    field: MoneyField | AttributeField
    status: EvidenceStatus
    value: JsonValue = None
    sources: list[SourceEvidence] = Field(default_factory=list)
    rule: str | None = None


class ReconciledFact(FactValues):
    id: int = 0
    evidence: list[FieldEvidence] = Field(default_factory=list)

    @property
    def has_conflicts(self) -> bool:
        return any(item.status == EvidenceStatus.CONFLICT for item in self.evidence)

    @property
    def source_fact_ids(self) -> list[int]:
        return sorted({source.fact_id for item in self.evidence for source in item.sources})
