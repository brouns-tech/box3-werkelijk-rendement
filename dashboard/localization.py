"""Language selector shared by desktop and CLI-launched dashboards."""
from pathlib import Path

import streamlit as st

from wr.desktop_storage import remember_language, remembered_language
from wr.i18n import LANGUAGES, translate


def select_language(directory: Path, default: str) -> str:
    saved = remembered_language(directory, default)
    if "ui_language" not in st.session_state or saved != st.session_state.get("saved_language"):
        st.session_state.ui_language = saved
    st.session_state.saved_language = saved

    def persist():
        language = st.session_state.ui_language
        try:
            remember_language(directory, language)
            st.session_state.saved_language = language
        except OSError as exc:
            st.session_state.language_error = str(exc)

    language = st.selectbox("Language / Taal", list(LANGUAGES), format_func=LANGUAGES.__getitem__,
                            key="ui_language", on_change=persist)
    if error := st.session_state.pop("language_error", None):
        st.error(translate(language, "Could not save language preference: {error}", error=error))
    return language
