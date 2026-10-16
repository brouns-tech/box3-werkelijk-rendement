"""Reset imported workspace data and saved identity preferences."""
from __future__ import annotations

from wr.models.settings import HouseholdSettings, Settings
from wr.storage.connection import connect
from wr.storage.migrations import init_db
from wr.workspace.settings import resolve_db_path, save_settings


def reset_workspace(settings: Settings) -> None:
    """Clear app-owned records while preserving source files and database setup."""
    conn = connect(resolve_db_path(settings))
    try:
        init_db(conn)
        with conn:
            for table in (
                "taxpayer_tax_results",
                "yearly_portfolio",
                "reconciled_facts",
                "account_year_facts",
                "tax_returns",
                "documents",
            ):
                conn.execute(f"DELETE FROM {table}")
            conn.execute("DELETE FROM sqlite_sequence WHERE name IN ('account_year_facts', 'tax_returns')")
            # Saving inside the transaction rolls back deletions on a write error.
            save_settings(settings, HouseholdSettings(), "", institution_options={})
    finally:
        conn.close()
