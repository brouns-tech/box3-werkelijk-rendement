from __future__ import annotations

import json
import sqlite3

from wr.identities.matching import name_tokens


def observed_names(conn: sqlite3.Connection) -> list[str]:
    names: set[str] = set()
    for row in conn.execute("SELECT filer_name, partner_a_name, partner_b_name FROM tax_returns"):
        names.update(name.strip() for name in row if name and name.strip())
    for row in conn.execute("SELECT holder_names FROM account_year_facts"):
        names.update(name.strip() for name in json.loads(row[0] or "[]") if name.strip())
    return sorted((n for n in names if name_tokens(n) and n.casefold() not in {"unknown", "onbekend", "partner_a", "partner_b"}), key=lambda n: (name_tokens(n), n))


def tax_identity_names(conn: sqlite3.Connection) -> set[str]:
    return {
        name for row in conn.execute("SELECT filer_name, partner_a_name, partner_b_name FROM tax_returns")
        for name in row if name and name_tokens(name) and name.casefold() not in {"unknown", "onbekend", "partner_a", "partner_b"}
    }


def filer_names(conn: sqlite3.Connection) -> set[str | None]:
    return {row[0] for row in conn.execute("SELECT filer_name FROM tax_returns")}
