"""Workspace management controls."""
from __future__ import annotations

import sqlite3
from pathlib import Path
from dataclasses import replace

import streamlit as st

from dashboard.localization import ui_translator
from wr.messages import Message, Messages

from dashboard.ui_state import clear_workspace_ui_state
from wr.workspace import reset_workspace
from wr.config import save_settings
from wr.db import connect, init_db
from wr.parsers import PLUGINS


def _storage_settings_ui(cfg) -> None:
    t = ui_translator()
    st.caption(t.workspace(path=cfg.project_root))
    with st.form("workspace_settings"):
        st.subheader(t(Messages.STORAGE))
        database = st.text_input(
            t(Messages.DATABASE_FILE), value=str(cfg.db_path), key="database_file",
            help=t(Messages.DATABASE_FILE_HELP),
        )
        options = {name: values.model_dump(exclude_unset=True) for name, values in cfg.institution_options.items()}
        with st.expander(t(Messages.ADDITIONAL_OPTIONS), expanded=False):
            for plugin in PLUGINS:
                if not plugin.settings_fields:
                    continue
                st.subheader(plugin.issuer.upper())
                values = options.setdefault(plugin.issuer, {})
                for field in plugin.settings_fields:
                    value = st.text_input(
                        t(field.label) if isinstance(field.label, Message) else field.label,
                        value=str(values.get(field.key, "")),
                        help=(t(field.help) if isinstance(field.help, Message) else field.help) or None,
                        key=f"institution_{plugin.issuer}_{field.key}",
                    ).strip()
                    if value:
                        values[field.key] = value
                    else:
                        values.pop(field.key, None)
            st.caption(t(Messages.INSTITUTION_OPTIONS_HELP))
        saved = st.form_submit_button(t(Messages.SAVE_WORKSPACE_SETTINGS), key="save_workspace_settings")
    if saved:
        try:
            if not database.strip():
                raise ValueError(t(Messages.PROVIDE_A_DATABASE_FILE_PATH))
            updated = replace(cfg, db_path=Path(database.strip()).expanduser(), institution_options=options)
            conn = connect(updated.resolved_db_path)
            try:
                init_db(conn)
            finally:
                conn.close()
            save_settings(updated)
        except (OSError, ValueError, sqlite3.Error) as exc:
            st.error(t.could_not_save_workspace_settings(error=exc))
        else:
            st.session_state["workspace_settings_saved"] = True
            st.rerun()
    if st.session_state.pop("workspace_settings_saved", False):
        st.success(t(Messages.WORKSPACE_SETTINGS_SAVED))


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
    t = ui_translator()
    st.subheader(t(Messages.SETTINGS))
    _storage_settings_ui(cfg)
    if st.session_state.pop("workspace_reset_done", False):
        st.success(t(Messages.WORKSPACE_RESET_CHOOSE_A_DOCUMENT_FOLDER_TO_START_AGAIN))
    st.markdown(_RESET_STYLE, unsafe_allow_html=True)
    with st.container(key="workspace_reset", border=True):
        st.subheader(t(Messages.RESET_WORKSPACE))
        st.write(t(Messages.RESET_WORKSPACE_HELP))
        st.caption(t(Messages.ORIGINAL_PDFS_AND_AUDIT_EXPORTS_STAY_ON_DISK))
        if st.button(t(Messages.RESET_WORKSPACE), type="primary", key="reset_workspace"):
            st.session_state["reset_workspace_pending"] = True
        if st.session_state.get("reset_workspace_pending"):
            st.error(t(Messages.RESET_WORKSPACE_CONFIRMATION))
            confirm, cancel = st.columns(2)
            if confirm.button(t(Messages.DELETE_PROFILES_AND_IMPORTED_DATA), type="primary", key="confirm_reset_workspace"):
                try:
                    reset_workspace(cfg)
                except (OSError, ValueError, sqlite3.Error) as exc:
                    st.error(t.could_not_reset_workspace(error=exc))
                else:
                    clear_workspace_ui_state()
                    st.session_state["workspace_reset_done"] = True
                    st.rerun()
            if cancel.button(t(Messages.CANCEL), key="cancel_reset_workspace"):
                st.session_state.pop("reset_workspace_pending", None)
                st.rerun()
