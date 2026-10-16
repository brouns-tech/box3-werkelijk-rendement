from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Callable


class ImportStatus(str, Enum):
    PARSED = "parsed"
    SKIPPED = "skipped"
    DUPLICATE = "duplicate"
    FAILED = "failed"


@dataclass(frozen=True)
class DocumentImportOutcome:
    index: int
    total: int
    path: Path
    status: ImportStatus
    issuer: str | None = None
    doc_type: str | None = None
    tax_year: int | None = None
    error: str | None = None


@dataclass
class ImportReport:
    seen: int = 0
    new: int = 0
    duplicate: int = 0
    parsed: int = 0
    skipped: int = 0
    failed: int = 0
    outcomes: list[DocumentImportOutcome] = field(default_factory=list)
    cancelled: bool = False

    def add(self, outcome: DocumentImportOutcome, *, inserted: bool = False) -> None:
        self.seen += 1
        self.new += int(inserted)
        setattr(self, outcome.status.value, getattr(self, outcome.status.value) + 1)
        self.outcomes.append(outcome)


ProgressCallback = Callable[[DocumentImportOutcome], None]
