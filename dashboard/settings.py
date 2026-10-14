"""Workspace settings and local document-folder selection."""
from __future__ import annotations

from pathlib import Path
import sqlite3

import streamlit as st

from dashboard.folder_picker import folder_path_input
from dashboard.ui_state import prepare_taxpayer_editor, refresh_taxpayer_editor, taxpayer_widget_key
from wr.config import ChildSettings, PartnerSettings, resolve_db_path, save_settings
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

    st.info("Tax returns identify primary taxpayers and fiscal partners. Other distinct account holders are suggested as minor children; review these guesses, especially missing adult returns and shared initials. Fiscal partnership and allocation come from each tax return.")
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
    st.subheader("Minor children (assets attributed to parents)")
    st.caption("Minderjarige kinderen: use this category for children whose Box 3 assets are attributed to the parents. Their documents appear as joint (purple) in the overview. Review ages and parental authority for the relevant tax year.")
    count_key = taxpayer_widget_key("child_count")
    st.session_state.setdefault(count_key, len(partners.children))
    if st.button("Add child", key="add_child"):
        st.session_state[count_key] += 1
    child_slots = [f"child_{index}" for index in range(st.session_state[count_key])]
    # Rows of at most two cards support an arbitrary number of children.
    for start in range(0, len(child_slots), 2):
        columns = st.columns(min(2, len(child_slots) - start))
        for index, column in enumerate(columns, start=start):
            slot = f"child_{index}"
            child = partners.children[index] if index < len(partners.children) else None
            canonical_key = taxpayer_widget_key(f"canonical_{slot}")
            column.markdown(f"**{st.session_state.get(canonical_key, child.canonical_name if child else '') or f'Child {index + 1}'}**")
            values[slot] = column.text_input("Canonical name", value=child.canonical_name if child else "", key=canonical_key)
            values[f"aliases_{slot}"] = column.text_area(
                "Aliases (one per line)", value="\n".join(child.aliases) if child else "",
                key=taxpayer_widget_key(f"aliases_{slot}"),
            )
    if child_slots:
        st.caption("To remove a child, clear the canonical name and aliases, and set its document names to Unassigned or another person.")
    save = st.button("Save settings and update analysis", key="save_settings")
    labels = {
        "unassigned": "Unassigned",
        "a": values["a"].strip() or "First taxpayer (enter a name above)",
        "b": values["b"].strip() or "Second taxpayer (enter a name above)",
    }
    labels.update({slot: values[slot].strip() or f"Child {index + 1} (enter a name above)" for index, slot in enumerate(child_slots)})
    slots = ["a", "b", *child_slots]
    assignments = {}
    if names:
        st.markdown("**Names found in documents**")
        st.caption("Assignments save and update the analysis immediately, including any name or alias edits above. These assignments take precedence over the alias text. Source names are preserved.")
        for index, name in enumerate(names):
            options = ["unassigned", *slots]
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
                for slot in slots
            }
            for name, assignment in assignments.items():
                for slot in slots:
                    aliases[slot].discard(name)
                if assignment != "unassigned":
                    aliases[assignment].add(name)
            updated = PartnerSettings(
                partner_a=values["a"].strip() or None,
                partner_b=values["b"].strip() or None,
                partner_a_aliases=tuple(sorted(aliases["a"] - {values["a"].strip()})),
                partner_b_aliases=tuple(sorted(aliases["b"] - {values["b"].strip()})),
                unassigned_names=tuple(name for name, assignment in assignments.items() if assignment == "unassigned"),
                children=tuple(
                    ChildSettings(values[slot].strip(), tuple(sorted(aliases[slot] - {values[slot].strip()})))
                    for slot in child_slots if values[slot].strip()
                ),
            )
            if any(aliases[slot] and not values[slot].strip() for slot in child_slots):
                raise ValueError("Provide a child name before assigning aliases or documents.")
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
