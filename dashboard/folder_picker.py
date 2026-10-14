"""Adapt Streamlit Explorer's selection to the editable document-folder field."""
from __future__ import annotations

from pathlib import Path

import streamlit as st
from dashboard.explorer_compat import DirPicker


def _reset_picker() -> None:
    # DirPicker retains its last selection. A fresh instance prevents it from
    # overwriting subsequent text edits and allows selecting the same path again.
    st.session_state["folder_picker_generation"] = st.session_state.get("folder_picker_generation", 0) + 1


def folder_path_input(project_root: Path) -> tuple[str, bool]:
    raw = st.session_state.get("document_folder", "").strip()
    try:
        start = Path(raw).expanduser() if raw else project_root
        if not start.is_absolute():
            start = project_root / start
        start = start.resolve()
        while not start.is_dir() and start != start.parent:
            start = start.parent
    except (OSError, ValueError):
        start = project_root

    # Reserve the field above the picker while processing selection before the
    # text widget is instantiated, so its session state can be updated safely.
    path_row = st.container()
    key = f"document_picker_{st.session_state.get('folder_picker_generation', 0)}"
    try:
        selected = DirPicker(key=key, start_path=str(start))
    except OSError as exc:
        st.error(f"Cannot browse this folder: {exc}")
        _reset_picker()
        selected = None
    if selected:
        st.session_state["document_folder"] = str(Path(selected).resolve())
        st.session_state["folder_selected"] = True
        _reset_picker()
        st.rerun()
    with path_row:
        field, action, _ = st.columns([4, 1.5, 4.5], vertical_alignment="bottom")
        root = field.text_input(
            "Document folder", key="document_folder", on_change=_reset_picker,
            help="Paste a folder path or browse. Relative paths start at this workspace; ~ refers to your home folder.",
        )
        save = action.button("Save folder", key="save_folder")
    return root, save
