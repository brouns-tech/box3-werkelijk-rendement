"""Workspace settings and local document-folder selection."""
from __future__ import annotations

from pathlib import Path
import sqlite3

import streamlit as st

from dashboard.folder_picker import folder_path_input
from dashboard.ui_state import prepare_taxpayer_editor, refresh_taxpayer_editor, taxpayer_widget_key
from wr.config import PartnerSettings, resolve_db_path, save_settings
from wr.identities import effective_partners, identity_slot, observed_names
from wr.import_pipeline import run_import
from wr.recommend import rebuild_recommendations


_UNASSIGNED_STYLE = """
<style>
div[class*="st-key-unassigned_name_"] {
    background-color: rgba(173, 106, 106, 0.4);
    border-left: 3px solid #ad6a6a;
    border-radius: 6px;
    padding: 0.5rem 0.75rem;
}
div[class*="st-key-unassigned_name_"] [data-baseweb="select"] > div {
    border-color: rgba(173, 106, 106, 0.5);
}
</style>
"""


def _assignment_changed() -> None:
    # Process the change on the next script run, using its live DB connection.
    st.session_state["taxpayer_assignment_changed"] = True


def documents_ui(cfg) -> None:
    st.subheader("Documents")
    st.session_state.setdefault("document_folder", str(cfg.import_root or ""))
    root, save = folder_path_input(cfg.project_root)
    st.caption("Choose a folder on the computer running the app. Imports scan PDFs in that folder and its subfolders directly. The path is remembered across sessions.")
    selected = st.session_state.pop("folder_selected", False)
    do_import = st.button("Import documents", disabled=not root.strip(), key="import_documents")
    if save or do_import or selected:
        try:
            if not root.strip():
                raise ValueError("Choose a document folder first.")
            folder = Path(root.strip()).expanduser()
            if not folder.is_absolute():
                folder = cfg.project_root / folder
            folder = folder.resolve()
            if not folder.is_dir():
                raise ValueError("The document folder does not exist or is not a directory.")
            save_settings(cfg, cfg.partners, str(folder))
            if do_import:
                with st.spinner("Importing documents…"):
                    report = run_import(
                        folder, resolve_db_path(cfg), partner_config=cfg.partners,
                        institution_options=cfg.institution_options,
                    )
                st.session_state["import_summary"] = f"Import finished: {report.parsed} parsed, {report.duplicate} duplicates, {report.skipped} skipped, {report.failed} failed."
            else:
                st.session_state["folder_saved"] = True
        except (OSError, ValueError) as exc:
            st.error(str(exc))
        else:
            if not do_import:
                st.rerun()
            refresh_taxpayer_editor()
            st.rerun()
    if st.session_state.pop("folder_saved", False):
        st.success("Document folder saved.")
    if "import_summary" in st.session_state:
        st.info(st.session_state.pop("import_summary"))


def taxpayers_ui(cfg, conn) -> PartnerSettings:
    st.subheader("Taxpayers")
    st.caption("Taxpayer names and aliases are saved in this workspace and reused across sessions.")
    partners = effective_partners(conn, cfg.partners)
    names = observed_names(conn)
    prepare_taxpayer_editor(str(cfg.resolved_db_path), partners, names)

    st.info("Detected identities are best guesses based on names. Review shared initials and add nicknames as aliases. Fiscal partnership and allocation come from each tax return.")
    st.markdown(_UNASSIGNED_STYLE, unsafe_allow_html=True)
    columns = st.columns(2)
    values = {}
    for slot, column in zip(("a", "b"), columns):
        fallback = "First taxpayer" if slot == "a" else "Second taxpayer (optional)"
        current = getattr(partners, f"partner_{slot}") or ""
        canonical_key = taxpayer_widget_key(f"canonical_{slot}")
        column.markdown(f"**{st.session_state.get(canonical_key, current) or fallback}**")
        values[slot] = column.text_input("Canonical name", value=current, key=canonical_key)
        values[f"aliases_{slot}"] = column.text_area(
            "Aliases (one per line)", value="\n".join(partners.aliases_for(slot)),
            key=taxpayer_widget_key(f"aliases_{slot}"),
        )
    st.caption("For one identity, clear the second name and assign its spellings to the remaining person. Two identities do not imply full-year fiscal partnership.")
    save = st.button("Save settings and update analysis", key="save_settings")
    labels = {
        "unassigned": "Unassigned",
        "a": values["a"].strip() or "First taxpayer (enter a name above)",
        "b": values["b"].strip() or "Second taxpayer (enter a name above)",
    }
    assignments = {}
    if names:
        st.markdown("**Names found in documents**")
        st.caption("Assignments save and update the analysis immediately, including any name or alias edits above. These assignments take precedence over the alias text. Source names are preserved.")
        for index, name in enumerate(names):
            options = ["unassigned", "a", "b"]
            slot = identity_slot(name, partners) or "unassigned"
            key = taxpayer_widget_key(f"identity_{name}")
            unassigned = st.session_state.get(key, slot) == "unassigned"
            with st.container(key=f"{'unassigned' if unassigned else 'assigned'}_name_{index}"):
                assignments[name] = st.selectbox(
                    name, options, index=options.index(slot), format_func=labels.get,
                    key=key, on_change=_assignment_changed,
                )
    changed = st.session_state.pop("taxpayer_assignment_changed", False)
    if save or changed:
        try:
            aliases = {
                slot: {alias.strip() for alias in values[f"aliases_{slot}"].splitlines() if alias.strip()}
                for slot in ("a", "b")
            }
            for name, assignment in assignments.items():
                for slot in ("a", "b"):
                    aliases[slot].discard(name)
                if assignment != "unassigned":
                    aliases[assignment].add(name)
            updated = PartnerSettings(
                partner_a=values["a"].strip() or None,
                partner_b=values["b"].strip() or None,
                partner_a_aliases=tuple(sorted(aliases["a"] - {values["a"].strip()})),
                partner_b_aliases=tuple(sorted(aliases["b"] - {values["b"].strip()})),
                unassigned_names=tuple(name for name, assignment in assignments.items() if assignment == "unassigned"),
            )
            save_settings(cfg, updated, str(cfg.import_root or ""))
            rebuild_recommendations(conn, updated)
        except (ValueError, OSError, sqlite3.Error) as exc:
            st.error(str(exc))
        else:
            st.session_state["settings_saved"] = True
            st.rerun()
    if st.session_state.pop("settings_saved", False):
        st.success("Settings saved.")
    return partners
