"""Workspace management controls."""
from __future__ import annotations

import sqlite3
from pathlib import Path
from dataclasses import replace

import streamlit as st

from dashboard.ui_state import clear_workspace_ui_state
from wr.workspace import reset_workspace
from wr.config import save_settings
from wr.db import connect, init_db
from wr.parsers import PLUGINS


def _storage_settings_ui(cfg) -> None:
    st.caption(f"Workspace: {cfg.project_root}")
    with st.form("workspace_settings"):
        st.subheader("Storage")
        database = st.text_input(
            "Database file", value=str(cfg.db_path), key="database_file",
            help="Relative paths start at this workspace. Choosing a different file opens a different dataset; existing database files stay on disk.",
        )
        options = {name: dict(values) for name, values in cfg.institution_options.items()}
        with st.expander("Additional options", expanded=False):
            for plugin in PLUGINS:
                if not plugin.settings_fields:
                    continue
                st.subheader(plugin.issuer.upper())
                values = options.setdefault(plugin.issuer, {})
                for field in plugin.settings_fields:
                    value = st.text_input(
                        field.label, value=str(values.get(field.key, "")), help=field.help,
                        key=f"institution_{plugin.issuer}_{field.key}",
                    ).strip()
                    if value:
                        values[field.key] = value
                    else:
                        values.pop(field.key, None)
            st.caption("Institution options apply when documents are parsed. To apply changes to existing documents, reset the workspace and import them again.")
        saved = st.form_submit_button("Save workspace settings", key="save_workspace_settings")
    if saved:
        try:
            if not database.strip():
                raise ValueError("Provide a database file path.")
            updated = replace(cfg, db_path=Path(database.strip()).expanduser(), institution_options=options)
            conn = connect(updated.resolved_db_path)
            try:
                init_db(conn)
            finally:
                conn.close()
            save_settings(updated)
        except (OSError, ValueError, sqlite3.Error) as exc:
            st.error(f"Could not save workspace settings: {exc}")
        else:
            st.session_state["workspace_settings_saved"] = True
            st.rerun()
    if st.session_state.pop("workspace_settings_saved", False):
        st.success("Workspace settings saved.")


_RESET_STYLE = """
<style>
.st-key-workspace_reset button[data-testid="stBaseButton-primary"] {
    background-color: #b91c1c;
    border-color: #b91c1c;
    color: #ffffff;
}
.st-key-workspace_reset button[data-testid="stBaseButton-primary"]:hover,
.st-key-workspace_reset button[data-testid="stBaseButton-primary"]:focus {
    background-color: #991b1b;
    border-color: #991b1b;
    color: #ffffff;
}
</style>
"""


def workspace_settings_ui(cfg) -> None:
    st.subheader("Settings")
    _storage_settings_ui(cfg)
    if st.session_state.pop("workspace_reset_done", False):
        st.success("Workspace reset. Choose a document folder to start again.")
    st.markdown(_RESET_STYLE, unsafe_allow_html=True)
    with st.container(key="workspace_reset", border=True):
        st.subheader("Reset workspace")
        st.write("Remove all taxpayer profiles, aliases, imported document records, extracted data, analysis results, institution options, and the saved document folder.")
        st.caption("Original PDFs and audit exports stay on disk.")
        if st.button("Reset workspace", type="primary", key="reset_workspace"):
            st.session_state["reset_workspace_pending"] = True
        if st.session_state.get("reset_workspace_pending"):
            st.error("This permanently deletes all imported data and profiles from this workspace. You will need to import your documents again.")
            confirm, cancel = st.columns(2)
            if confirm.button("Delete profiles and imported data", type="primary", key="confirm_reset_workspace"):
                try:
                    reset_workspace(cfg)
                except (OSError, ValueError, sqlite3.Error) as exc:
                    st.error(f"Could not reset workspace: {exc}")
                else:
                    clear_workspace_ui_state()
                    st.session_state["workspace_reset_done"] = True
                    st.rerun()
            if cancel.button("Cancel", key="cancel_reset_workspace"):
                st.session_state.pop("reset_workspace_pending", None)
                st.rerun()
