from __future__ import annotations

from wr.config import load_config
from wr.pdf import normalize_iban


def has_zero_return_by_product(issuer: str, account_label: str) -> bool:
    label = account_label.lower()
    return (
        issuer.lower() == "ing"
        and any(product in label for product in ("betaalrekening", "creditcardrekening"))
    ) or (issuer.lower() == "flatex" and label.startswith("flatex cash account"))


def flatex_linked_account() -> str | None:
    try:
        account = load_config().get("accounts", {}).get("flatex_linked_account")
    except FileNotFoundError:
        return None
    return normalize_iban(account) if account else None
