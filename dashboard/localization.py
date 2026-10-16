"""Language selector shared by desktop and CLI-launched dashboards."""
from pathlib import Path

import streamlit as st

from wr.desktop.storage import remember_language, remembered_language
from wr.i18n import LANGUAGES, Translator, translator
from wr.messages import Messages


def ui_translator() -> Translator:
    return translator(st.session_state.get("ui_language", "en"))


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

    language = st.selectbox(ui_translator()(Messages.LANGUAGE_TAAL), list(LANGUAGES), format_func=LANGUAGES.__getitem__,
                            key="ui_language", on_change=persist)
    if error := st.session_state.pop("language_error", None):
        st.error(translator(language).could_not_save_language_preference(error=error))
    return language
