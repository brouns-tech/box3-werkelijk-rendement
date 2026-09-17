from __future__ import annotations

from wr.config import load_config
from wr.pdf import normalize_iban


def has_zero_return_by_product(issuer: str, account_label: str) -> bool:
    return issuer.lower() == "ing" and any(
        product in account_label.lower()
        for product in ("betaalrekening", "creditcardrekening")
    )


def flatex_linked_account() -> str | None:
    try:
        account = load_config().get("accounts", {}).get("flatex_linked_account")
    except FileNotFoundError:
        return None
    return normalize_iban(account) if account else None
