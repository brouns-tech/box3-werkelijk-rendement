from __future__ import annotations

import re

from wr.models.parsing import Classification
from wr.parsers import classification_rules
from wr.parsers.base import ClassificationRule
from wr.parsers.common import guess_tax_year


CLASSIFICATION_RULES: tuple[ClassificationRule, ...] = classification_rules()


def classify(text: str) -> Classification | None:
    """Classify a document through the registered institution plugins."""
    normalized = re.sub(r"[ \t]+", " ", text.lower())
    for rule in CLASSIFICATION_RULES:
        if rule.detector(normalized):
            return Classification(rule.issuer, rule.doc_type) if rule.supported else None
    return None


__all__ = ["CLASSIFICATION_RULES", "Classification", "classify", "guess_tax_year"]
