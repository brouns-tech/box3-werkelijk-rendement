from __future__ import annotations

from difflib import SequenceMatcher
import re
from typing import NamedTuple
import unicodedata

from wr.models.settings import PartnerSettings


NO_MATCH = 0.0
FIRST_NAME_MATCH = 0.8
INITIALS_MATCH = 0.85
FUZZY_NAME_MATCH = 0.9
EXACT_MATCH = 1.0

MIN_IDENTITY_SCORE = FIRST_NAME_MATCH
MIN_IDENTITY_MARGIN = 0.1
GIVEN_NAME_SIMILARITY_THRESHOLD = 0.86
SURNAME_SIMILARITY_THRESHOLD = 0.9


class _IdentityMatch(NamedTuple):
    score: float
    slot: str


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
        return "".join(tokens[:initials]), *tokens[initials:]
    return tokens


def similarity(left: str, right: str) -> float:
    """Return a named match score, from NO_MATCH through EXACT_MATCH."""
    a, b = name_tokens(left), name_tokens(right)
    if not a or not b:
        return NO_MATCH
    if name_key(left) == name_key(right):
        return EXACT_MATCH
    if len(a) == 1 or len(b) == 1:
        short, long = (a, b) if len(a) == 1 else (b, a)
        # First names may match uniquely; surnames alone never establish identity.
        return FIRST_NAME_MATCH if len(short[0]) > 1 and short[0] == long[0] and len(long) > 1 else NO_MATCH
    if a[1:] == b[1:]:
        if a[0][0] != b[0][0]:
            return NO_MATCH
        if len(a[0]) == 1 or len(b[0]) == 1:
            return INITIALS_MATCH
        given_name_similarity = SequenceMatcher(None, a[0], b[0]).ratio()
        return FUZZY_NAME_MATCH if given_name_similarity >= GIVEN_NAME_SIMILARITY_THRESHOLD else NO_MATCH
    # Multiple initials, optionally expanded to full given names.
    if a[-1] == b[-1] and len(a) == len(b):
        if all(x == y or (min(len(x), len(y)) == 1 and x[0] == y[0]) for x, y in zip(a[:-1], b[:-1])):
            return INITIALS_MATCH
    if a[0] == b[0] and len(a[0]) > 1:
        surname_similarity = SequenceMatcher(None, " ".join(a[1:]), " ".join(b[1:])).ratio()
        return FUZZY_NAME_MATCH if surname_similarity >= SURNAME_SIMILARITY_THRESHOLD else NO_MATCH
    return NO_MATCH


def identity_slot(name: str | None, partners: PartnerSettings) -> str | None:
    """Return 'a', 'b', or 'child_<index>' for a unique match, otherwise None."""
    if not name:
        return None
    if any(name_key(name) == name_key(excluded) for excluded in partners.unassigned_names):
        return None
    matches: list[_IdentityMatch] = []
    for slot, canonical in partners.identities():
        if canonical:
            score = max(similarity(name, alias) for alias in (canonical, *partners.aliases_for(slot)))
            matches.append(_IdentityMatch(score=score, slot=slot))
    matches.sort(reverse=True)
    if not matches:
        return None
    best_match = matches[0]
    runner_up = matches[1] if len(matches) > 1 else None
    if best_match.score < MIN_IDENTITY_SCORE:
        return None
    if best_match.score == EXACT_MATCH and (runner_up is None or runner_up.score < EXACT_MATCH):
        return best_match.slot
    if runner_up is not None and best_match.score - runner_up.score < MIN_IDENTITY_MARGIN:
        return None
    return best_match.slot


def same_person(left: str | None, right: str | None) -> bool:
    return bool(left and right and similarity(left, right) >= MIN_IDENTITY_SCORE)
