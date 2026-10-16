"""Synchronize taxpayer editor widgets with imported and saved workspace data."""
from __future__ import annotations

import streamlit as st

from wr.models.identities import HouseholdSettings


_REVISION = "_taxpayer_editor_revision"
_SOURCE = "_taxpayer_editor_source"
_WIDGET_PREFIX = "taxpayer_input_"


def prepare_taxpayer_editor(database: str, household: HouseholdSettings, names: list[str]) -> None:
    source = (database, household, tuple(names))
    if st.session_state.get(_SOURCE) == source:
        return
    # Reusing keys lets Streamlit restore deleted state from the browser. Rotate
    # identities when the backing data changes, rather than merely deleting keys.
    st.session_state[_REVISION] = st.session_state.get(_REVISION, 0) + 1
    st.session_state[_SOURCE] = source
    # Callbacks from the previous widget generation must not save the refreshed
    # editor after imported names or profiles have changed.
    st.session_state.pop("taxpayer_assignment_changed", None)
    st.session_state.pop("taxpayer_save_requested", None)
    for key in list(st.session_state):
        if key.startswith(_WIDGET_PREFIX):
            del st.session_state[key]


def taxpayer_widget_key(field: str) -> str:
    return f"{_WIDGET_PREFIX}{st.session_state[_REVISION]}_{field}"


def refresh_taxpayer_editor() -> None:
    st.session_state.pop(_SOURCE, None)
    st.session_state.pop("taxpayer_assignment_changed", None)
    st.session_state.pop("taxpayer_save_requested", None)


def clear_workspace_ui_state() -> None:
    # Preserve the counter so reset cannot reuse the browser's previous keys.
    revision = st.session_state.get(_REVISION, 0)
    st.session_state.clear()
    st.session_state[_REVISION] = revision
