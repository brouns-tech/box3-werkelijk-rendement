"""Keep Streamlit Explorer 0.1.0's path widget compatible with session state."""
from __future__ import annotations

import streamlit as st
import streamlit_explorer


class _ExplorerStreamlit:
    """Scope the upstream workaround to Explorer, without changing Streamlit."""

    def __getattr__(self, name):
        return getattr(st, name)

    def text_input(self, label, **kwargs):
        key = kwargs.get("key")
        # Up/Back navigation assigns the path through session state. Explorer
        # also passes value=current, which causes a duplicate-value warning.
        # Once state exists, let it be the sole source of the widget's value.
        if key and key.endswith("_path_input_key") and key in st.session_state:
            kwargs.pop("value", None)
        return st.text_input(label, **kwargs)


# Only Explorer's module-level Streamlit reference uses this adapter. Its
# fragments keep using it on subsequent reruns; application widgets are untouched.
streamlit_explorer.st = _ExplorerStreamlit()
DirPicker = streamlit_explorer.DirPicker
