from __future__ import annotations

from difflib import SequenceMatcher
import re
import unicodedata

from wr.models.settings import PartnerSettings


def name_tokens(name: str) -> tuple[str, ...]:
    text = unicodedata.normalize("NFKD", name.casefold())
    text = "".join(c for c in text if not unicodedata.combining(c))
    tokens = re.findall(r"[a-z]+", text)
    while tokens and tokens[0] in {"mr", "mrs", "ms", "dr", "dhr", "mevr", "deheer", "mevrouw"}:
        tokens.pop(0)
    return tuple(tokens)


def name_key(name: str) -> tuple[str, ...]:
    """Ignore case and dots/spaces between leading initials, retaining name boundaries."""
    tokens = name_tokens(name)
    initials = 0
    while initials < len(tokens) and len(tokens[initials]) == 1:
        initials += 1
    if initials > 1:
        return ("".join(tokens[:initials]), *tokens[initials:])
    return tokens


def similarity(left: str, right: str) -> float:
    a, b = name_tokens(left), name_tokens(right)
    if not a or not b:
        return 0.0
    if name_key(left) == name_key(right):
        return 1.0
    if len(a) == 1 or len(b) == 1:
        short, long = (a, b) if len(a) == 1 else (b, a)
        # First names may match uniquely; surnames alone never establish identity.
        return 0.8 if len(short[0]) > 1 and short[0] == long[0] and len(long) > 1 else 0.0
    if a[1:] == b[1:]:
        if a[0][0] != b[0][0]:
            return 0.0
        if len(a[0]) == 1 or len(b[0]) == 1:
            return 0.85
        return 0.9 if SequenceMatcher(None, a[0], b[0]).ratio() >= 0.86 else 0.0
    # Multiple initials, optionally expanded to full given names.
    if a[-1] == b[-1] and len(a) == len(b):
        if all(x == y or (min(len(x), len(y)) == 1 and x[0] == y[0]) for x, y in zip(a[:-1], b[:-1])):
            return 0.85
    if a[0] == b[0] and len(a[0]) > 1:
        return 0.9 if SequenceMatcher(None, " ".join(a[1:]), " ".join(b[1:])).ratio() >= 0.9 else 0.0
    return 0.0


def identity_slot(name: str | None, partners: PartnerSettings) -> str | None:
    if not name:
        return None
    if any(name_key(name) == name_key(excluded) for excluded in partners.unassigned_names):
        return None
    scores = []
    for slot, canonical in partners.identities():
        if canonical:
            score = max(similarity(name, alias) for alias in (canonical, *partners.aliases_for(slot)))
            scores.append((score, slot))
    scores.sort(reverse=True)
    if not scores or scores[0][0] < 0.8:
        return None
    if scores[0][0] == 1.0 and (len(scores) == 1 or scores[1][0] < 1.0):
        return scores[0][1]
    if len(scores) > 1 and scores[0][0] - scores[1][0] < 0.1:
        return None
    return scores[0][1]


def same_person(left: str | None, right: str | None) -> bool:
    return bool(left and right and similarity(left, right) >= 0.8)
