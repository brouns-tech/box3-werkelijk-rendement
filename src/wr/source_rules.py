from __future__ import annotations

def has_zero_return_by_product(issuer: str, account_label: str) -> bool:
    label = account_label.lower()
    return (
        issuer.lower() == "ing"
        and any(product in label for product in ("betaalrekening", "creditcardrekening"))
    ) or (issuer.lower() == "flatex" and label.startswith("flatex cash account"))
