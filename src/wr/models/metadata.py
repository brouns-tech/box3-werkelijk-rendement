from __future__ import annotations

from pydantic import StrictBool

from wr.models.base import Record


class FactMetadata(Record):
    synthetic: bool | None = None
    box3: StrictBool = True
    account_type: str | None = None
    interest_source: str | None = None
    return_assumption: str | None = None
