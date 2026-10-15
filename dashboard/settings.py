"""Workspace settings and local document-folder selection."""
from __future__ import annotations

from pathlib import Path
import os
import sqlite3
from dataclasses import replace

import streamlit as st

from dashboard.localization import ui_text as t

from dashboard.folder_picker import folder_path_input
from dashboard.ui_state import prepare_taxpayer_editor, refresh_taxpayer_editor, taxpayer_widget_key
from dashboard.ownership import editor_key, editor_styles
from wr.config import ChildSettings, PartnerSettings, resolve_db_path, save_settings
from wr.identities import effective_partners, identity_slot, observed_names
from wr.import_pipeline import run_import
from wr.recommend import rebuild_recommendations


_EDITOR_STYLE = "<style>" + editor_styles() + """
div[class*="st-key-taxpayer_actions_"] { margin-top: -0.6rem; }
div[class*="st-key-save_field_"] button {
    color: #15803d; border-color: #15803d;
}
div[class*="st-key-discard_field_"] button {
    color: #dc2626; border-color: #dc2626;
}
</style>
"""


def _assignment_changed() -> None:
    # Process the change on the next script run, using its live DB connection.
    st.session_state["taxpayer_assignment_changed"] = True


def _save_requested() -> None:
    st.session_state["taxpayer_save_requested"] = True


def _discard_requested() -> None:
    refresh_taxpayer_editor()
    st.session_state.pop("taxpayer_assignment_changed", None)
    st.session_state.pop("taxpayer_save_requested", None)


def _field_actions(column, field: str, value: str, saved: str) -> None:
    if value == saved:
        return
    with column.container(key=f"taxpayer_actions_{field}", horizontal=True, horizontal_alignment="right", gap="small"):
        st.button("✓", key=f"save_field_{field}", help=t("Save all changes and update analysis"), on_click=_save_requested)
        st.button("✕", key=f"discard_field_{field}", help=t("Discard all unsaved changes"), on_click=_discard_requested)


def _request_child_deletion(index: int) -> None:
    st.session_state["taxpayer_delete_child"] = index


def _editor_widget_key(field: str, initial_value: str) -> str:
    # Session state is the only source of widget values, including restored drafts.
    # Widgets use a None default so Streamlit never sees competing initial values.
    key = taxpayer_widget_key(field)
    st.session_state.setdefault(key, initial_value)
    return key


def _preserve_other_drafts(indices: list[int], deleted: int, names: list[str]) -> None:
    """Keep other edits when deleting a saved child compacts profile indices."""
    remaining = [index for index in indices if index != deleted]
    drafts = {
        "child_indices": [index - (index > deleted) for index in remaining],
        "next_child_index": st.session_state[taxpayer_widget_key("next_child_index")] - 1,
    }
    slots = [("a", "a"), ("b", "b")] + [
        (f"child_{index}", f"child_{index - (index > deleted)}") for index in remaining
    ]
    for old, new in slots:
        for field in ("canonical", "aliases"):
            key = taxpayer_widget_key(f"{field}_{old}")
            if key in st.session_state:
                drafts[f"{field}_{new}"] = st.session_state[key]
    for name in names:
        key = taxpayer_widget_key(f"identity_{name}")
        if key not in st.session_state:
            continue
        slot = st.session_state[key]
        if slot == f"child_{deleted}":
            slot = "unassigned"
        elif slot.startswith("child_"):
            index = int(slot.removeprefix("child_"))
            slot = f"child_{index - (index > deleted)}"
        drafts[f"identity_{name}"] = slot
    st.session_state["_taxpayer_pending_drafts"] = drafts


def documents_ui(cfg) -> None:
    if os.environ.get("WR_CONTROL_URL"):
        from dashboard.desktop_import import render
        render(cfg, st.session_state.get("ui_language", "nl"))
        return
    st.subheader(t("Documents"))
    st.session_state.setdefault("document_folder", str(cfg.import_root or ""))
    root, save = folder_path_input(cfg.project_root)
    st.caption(t("Choose a folder on the computer running the app. Imports scan PDFs in that folder and its subfolders directly. The path is remembered across sessions."))
    selected = st.session_state.pop("folder_selected", False)
    do_import = st.button(t("Import documents"), disabled=not root.strip(), key="import_documents")
    if save or do_import or selected:
        try:
            if not root.strip():
                raise ValueError(t("Choose a document folder first."))
            folder = Path(root.strip()).expanduser()
            if not folder.is_absolute():
                folder = cfg.project_root / folder
            folder = folder.resolve()
            if not folder.is_dir():
                raise ValueError(t("The document folder does not exist or is not a directory."))
            save_settings(cfg, cfg.partners, str(folder))
            if do_import:
                with st.spinner(t("Importing documents…")):
                    report = run_import(
                        folder, resolve_db_path(cfg), partner_config=cfg.partners,
                        institution_options=cfg.institution_options,
                    )
                st.session_state["import_summary"] = t("Import finished: {parsed} parsed, {duplicate} duplicates, {skipped} skipped, {failed} failed.", parsed=report.parsed, duplicate=report.duplicate, skipped=report.skipped, failed=report.failed)
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
        st.success(t("Document folder saved."))
    if "import_summary" in st.session_state:
        st.info(st.session_state.pop("import_summary"))


def taxpayers_ui(cfg, conn) -> PartnerSettings:
    st.subheader(t("Taxpayers"))
    st.caption(t("Taxpayer names and aliases are saved in this workspace and reused across sessions."))
    partners = effective_partners(conn, cfg.partners)
    names = observed_names(conn)
    prepare_taxpayer_editor(str(cfg.resolved_db_path), partners, names)
    for field, value in st.session_state.pop("_taxpayer_pending_drafts", {}).items():
        st.session_state[taxpayer_widget_key(field)] = value
    indices_key = taxpayer_widget_key("child_indices")
    st.session_state.setdefault(indices_key, list(range(len(partners.children))))
    next_index_key = taxpayer_widget_key("next_child_index")
    st.session_state.setdefault(next_index_key, len(partners.children))
    delete_index = st.session_state.pop("taxpayer_delete_child", None)
    if delete_index is not None:
        if delete_index < len(partners.children):
            child = partners.children[delete_index]
            removed_names = {child.canonical_name, *child.aliases}
            removed_names.update(name for name in names if identity_slot(name, partners) == f"child_{delete_index}")
            updated = replace(
                partners, children=tuple(child for index, child in enumerate(partners.children) if index != delete_index),
                unassigned_names=tuple(sorted(set(partners.unassigned_names) | removed_names)),
            )
            try:
                save_settings(cfg, updated)
                rebuild_recommendations(conn, updated)
            except (ValueError, OSError, sqlite3.Error) as exc:
                st.error(str(exc))
            else:
                _preserve_other_drafts(st.session_state[indices_key], delete_index, names)
                refresh_taxpayer_editor()
                st.rerun()
        else:
            st.session_state[indices_key].remove(delete_index)
            for name in names:
                key = taxpayer_widget_key(f"identity_{name}")
                if st.session_state.get(key) == f"child_{delete_index}":
                    st.session_state[key] = "unassigned"

    st.info(t("Review taxpayer and child suggestions from imported documents. Tax returns provide fiscal partnership and allocation when available; otherwise the partnership setting below applies."))
    st.markdown(_EDITOR_STYLE, unsafe_allow_html=True)
    columns = st.columns(2)
    values = {}
    for slot, column in zip(("a", "b"), columns):
        column = column.container(key=editor_key(slot, "profile"))
        fallback = t("First taxpayer") if slot == "a" else t("Second taxpayer (optional)")
        current = getattr(partners, f"partner_{slot}") or ""
        canonical_key = _editor_widget_key(f"canonical_{slot}", current)
        column.markdown(f"**{st.session_state.get(canonical_key, current) or fallback}**")
        values[slot] = column.text_input(t("Canonical name"), value=None, key=canonical_key)
        _field_actions(column, f"canonical_{slot}", values[slot], current)
        values[f"aliases_{slot}"] = column.text_area(
            t("Aliases (one per line)"), value=None,
            key=_editor_widget_key(f"aliases_{slot}", "\n".join(partners.aliases_for(slot))),
        )
        _field_actions(column, f"aliases_{slot}", values[f"aliases_{slot}"], "\n".join(partners.aliases_for(slot)))
    partnership = st.checkbox(
        t("Assume full-year fiscal partnership when no tax return is available"),
        value=partners.assume_fiscal_partnership,
        key=taxpayer_widget_key("assume_fiscal_partnership"),
        on_change=_assignment_changed,
        help=t("Applies to years without tax returns when both taxpayers are named. Tax-return evidence takes precedence. No tax allocation is assumed."),
    )
    st.caption(t("For one identity, clear the second name and assign its spellings to the remaining person."))
    st.subheader(t("Minor children (assets attributed to parents)"))
    st.caption(t("Minderjarige kinderen: use this category for children whose Box 3 assets are attributed to the parents. Their documents appear as joint (purple) in the overview. Review ages and parental authority for the relevant tax year."))
    if st.button(t("Add child"), key="add_child"):
        st.session_state[indices_key].append(st.session_state[next_index_key])
        st.session_state[next_index_key] += 1
    child_slots = [f"child_{index}" for index in st.session_state[indices_key]]
    # Always allocate two columns, including the last row with one child.
    for start in range(0, len(child_slots), 2):
        columns = st.columns(2)
        for slot, column in zip(child_slots[start:start + 2], columns):
            column = column.container(key=editor_key(slot, f"profile_{slot}"))
            index = int(slot.removeprefix("child_"))
            child = partners.children[index] if index < len(partners.children) else None
            canonical_key = _editor_widget_key(f"canonical_{slot}", child.canonical_name if child else "")
            column.markdown(f"**{st.session_state.get(canonical_key, child.canonical_name if child else '') or t('Child {number}', number=index + 1)}**")
            values[slot] = column.text_input(t("Canonical name"), value=None, key=canonical_key)
            _field_actions(column, f"canonical_{slot}", values[slot], child.canonical_name if child else "")
            values[f"aliases_{slot}"] = column.text_area(
                t("Aliases (one per line)"), value=None,
                key=_editor_widget_key(f"aliases_{slot}", "\n".join(child.aliases) if child else ""),
            )
            _field_actions(column, f"aliases_{slot}", values[f"aliases_{slot}"], "\n".join(child.aliases) if child else "")
            column.button(t("Delete child"), key=f"delete_{slot}", on_click=_request_child_deletion, args=(index,))
    labels = {
        "unassigned": t("Unassigned"),
        "a": values["a"].strip() or t("First taxpayer (enter a name above)"),
        "b": values["b"].strip() or t("Second taxpayer (enter a name above)"),
    }
    labels.update({slot: values[slot].strip() or t("Child {number} (enter a name above)", number=index + 1) for index, slot in enumerate(child_slots)})
    slots = ["a", "b", *child_slots]
    assignments = {}
    if names:
        st.subheader(t("Names found in documents"))
        st.caption(t("Assignments save and update the analysis immediately, including any name or alias edits above. These assignments take precedence over the alias text. Source names are preserved."))
        for index, name in enumerate(names):
            options = ["unassigned", *slots]
            slot = identity_slot(name, partners) or "unassigned"
            key = _editor_widget_key(f"identity_{name}", slot)
            # Empty/stale browser state is not an ownership decision. Keep the
            # existing suggestion; explicit Unassigned remains a valid choice.
            if st.session_state.get(key) not in options:
                st.session_state[key] = slot
            assigned_slot = st.session_state.get(key, slot)
            with st.container(key=editor_key(assigned_slot, f"name_{index}")):
                selected = st.selectbox(
                    name, options, index=None, format_func=labels.get,
                    key=key, on_change=_assignment_changed,
                )
                assignments[name] = selected if selected in options else slot
    changed = st.session_state.pop("taxpayer_assignment_changed", False)
    save = st.session_state.pop("taxpayer_save_requested", False)
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
                assume_fiscal_partnership=partnership,
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
                raise ValueError(t("Provide a child name before assigning aliases or documents."))
            save_settings(cfg, updated, str(cfg.import_root or ""))
            rebuild_recommendations(conn, updated)
        except (ValueError, OSError, sqlite3.Error) as exc:
            st.error(str(exc))
        else:
            st.session_state["settings_saved"] = True
            st.rerun()
    if st.session_state.pop("settings_saved", False):
        st.success(t("Settings saved."))
    return partners
