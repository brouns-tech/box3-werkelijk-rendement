from __future__ import annotations

from collections.abc import Mapping
from typing import TypeVar
import sqlite3

from wr.models.storage import FactRecord
from wr.parsers._schemas import parse_metadata


FactRecordType = TypeVar("FactRecordType", bound=FactRecord)


def fact_from_row(
    row: sqlite3.Row | Mapping[str, object] | FactRecord,
    model: type[FactRecordType] = FactRecord,
) -> FactRecordType:
    if isinstance(row, model):
        return row
    payload = row.model_dump() if isinstance(row, FactRecord) else dict(row)
    issuer = payload.get("issuer", "")
    metadata = payload.get("extra")
    payload["extra"] = parse_metadata(issuer if isinstance(issuer, str) else "", {} if metadata is None or metadata == "" else metadata)
    return model.model_validate(payload)
