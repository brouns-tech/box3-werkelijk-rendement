"""Typed processing notifications, kept separate from coverage failures."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import json
from typing import Any


class NotificationType(str, Enum):
    ASSUMPTION = "assumption"
    WARNING = "warning"


@dataclass(frozen=True)
class FactNotification:
    type: NotificationType
    code: str
    details: dict[str, Any] = field(default_factory=dict)


def fact_notifications(fact) -> list[FactNotification]:
    """Read the same typed notifications from parsed and persisted facts."""
    raw = fact["extra"] if "extra" in fact.keys() else None
    extra = json.loads(raw or "{}") if isinstance(raw, str) else (raw or {})
    return [FactNotification(NotificationType(item["type"]), item["code"], item.get("details", {}))
            for item in extra.get("notifications", [])]
