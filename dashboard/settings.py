"""Workspace settings and local document-folder selection."""
from __future__ import annotations

from pathlib import Path
import os
import sqlite3
from dataclasses import dataclass
from uuid import UUID, uuid4
from typing import Literal

import streamlit as st

from dashboard.localization import ui_translator
from wr.messages import Messages

from dashboard.folder_picker import folder_path_input
from dashboard.ui_state import prepare_taxpayer_editor, refresh_taxpayer_editor, taxpayer_widget_key
from dashboard.ownership import editor_key, editor_styles
from wr.models.identities import ChildIdentity, HouseholdSettings, IdentityRole, TaxpayerIdentity, TaxpayerPosition
from wr.workspace.settings import resolve_db_path, save_settings
from wr.identities.service import effective_household
from wr.identities.matching import resolve_identity
from wr.storage.identities import observed_names
from wr.importing.pipeline import run_import
from wr.calculations.service import rebuild_recommendations


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
    t = ui_translator()
    if value == saved:
        return
    with column.container(key=f"taxpayer_actions_{field}", horizontal=True, horizontal_alignment="right", gap="small"):
        st.button("✓", key=f"save_field_{field}", help=t(Messages.SAVE_ALL_CHANGES_AND_UPDATE_ANALYSIS), on_click=_save_requested)
        st.button("✕", key=f"discard_field_{field}", help=t(Messages.DISCARD_ALL_UNSAVED_CHANGES), on_click=_discard_requested)


@dataclass(frozen=True)
class _ProfileEditor:
    id: UUID
    position: TaxpayerPosition | None = None
    saved: TaxpayerIdentity | ChildIdentity | None = None

    @property
    def kind(self) -> TaxpayerPosition | IdentityRole:
        return self.position if self.position is not None else IdentityRole.CHILD


IdentitySelection = UUID | Literal["unassigned"]


@dataclass(frozen=True)
class _EditorDrafts:
    profiles: list[_ProfileEditor]
    text: dict[str, str]
    assignments: dict[str, IdentitySelection]


def _request_child_deletion(identifier: UUID) -> None:
    st.session_state["taxpayer_delete_child"] = identifier


def _editor_widget_key(field: str, initial_value: str | UUID) -> str:
    key = taxpayer_widget_key(field)
    st.session_state.setdefault(key, initial_value)
    return key


def _preserve_other_drafts(profiles: list[_ProfileEditor], deleted: UUID, names: list[str]) -> None:
    remaining = [profile for profile in profiles if profile.id != deleted]
    text: dict[str, str] = {}
    assignments: dict[str, IdentitySelection] = {}
    for profile in remaining:
        for field in ("canonical", "aliases"):
            suffix = f"{field}_{profile.id}"
            key = taxpayer_widget_key(suffix)
            if key in st.session_state:
                text[suffix] = st.session_state[key]
    for name in names:
        suffix = f"identity_{name}"
        key = taxpayer_widget_key(suffix)
        if key in st.session_state:
            selected = st.session_state[key]
            assignments[suffix] = "unassigned" if selected == deleted else selected
    st.session_state["_taxpayer_pending_drafts"] = _EditorDrafts(remaining, text, assignments)


def documents_ui(cfg) -> None:
    t = ui_translator()
    if os.environ.get("WR_CONTROL_URL"):
        from dashboard.desktop_import import render
        render(cfg, st.session_state.get("ui_language", "nl"))
        return
    st.subheader(t(Messages.DOCUMENTS))
    st.session_state.setdefault("document_folder", str(cfg.import_root or ""))
    root, save = folder_path_input(cfg.project_root)
    st.caption(t(Messages.DOCUMENT_IMPORT_HELP))
    selected = st.session_state.pop("folder_selected", False)
    do_import = st.button(t(Messages.IMPORT_DOCUMENTS), disabled=not root.strip(), key="import_documents")
    if save or do_import or selected:
        try:
            if not root.strip():
                raise ValueError(t(Messages.CHOOSE_A_DOCUMENT_FOLDER_FIRST))
            folder = Path(root.strip()).expanduser()
            if not folder.is_absolute():
                folder = cfg.project_root / folder
            folder = folder.resolve()
            if not folder.is_dir():
                raise ValueError(t(Messages.THE_DOCUMENT_FOLDER_DOES_NOT_EXIST_OR_IS_NOT_A_DIRECTORY))
            save_settings(cfg, cfg.household, str(folder))
            if do_import:
                with st.spinner(t(Messages.IMPORTING_DOCUMENTS)):
                    report = run_import(
                        folder, resolve_db_path(cfg), household_config=cfg.household,
                        institution_options=cfg.institution_options,
                    )
                st.session_state["import_summary"] = t.import_finished(parsed=report.parsed, duplicate=report.duplicate, skipped=report.skipped, failed=report.failed)
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
        st.success(t(Messages.DOCUMENT_FOLDER_SAVED))
    if "import_summary" in st.session_state:
        st.info(st.session_state.pop("import_summary"))


def taxpayers_ui(cfg, conn) -> HouseholdSettings:
    t = ui_translator()
    st.subheader(t(Messages.TAXPAYERS))
    st.caption(t(Messages.TAXPAYER_PROFILES_HELP))
    household = effective_household(conn, cfg.household)
    names = observed_names(conn)
    prepare_taxpayer_editor(str(cfg.resolved_db_path), household, names)
    profiles_key = taxpayer_widget_key("profiles")
    pending = st.session_state.pop("_taxpayer_pending_drafts", None)
    if pending is not None:
        st.session_state[profiles_key] = pending.profiles
        for field, value in (*pending.text.items(), *pending.assignments.items()):
            st.session_state[taxpayer_widget_key(field)] = value
    if profiles_key not in st.session_state:
        taxpayers = []
        for position in TaxpayerPosition:
            saved = household.taxpayer(position)
            taxpayers.append(_ProfileEditor(saved.id if saved else uuid4(), position, saved))
        st.session_state[profiles_key] = taxpayers + [
            _ProfileEditor(child.id, saved=child) for child in household.children
        ]
    profiles = st.session_state[profiles_key]
    deleted = st.session_state.pop("taxpayer_delete_child", None)
    if deleted is not None:
        child = household.identity(deleted)
        if isinstance(child, ChildIdentity):
            removed_names = {child.name, *child.aliases}
            removed_names.update(
                name for name in names
                if (identity := resolve_identity(name, household)) is not None and identity.id == deleted
            )
            updated = HouseholdSettings(
                identities=tuple(identity for identity in household.identities if identity.id != deleted),
                unassigned_names=tuple(sorted(set(household.unassigned_names) | removed_names)),
            )
            try:
                save_settings(cfg, updated)
                rebuild_recommendations(conn, updated)
            except (ValueError, OSError, sqlite3.Error) as exc:
                st.error(str(exc))
            else:
                _preserve_other_drafts(profiles, deleted, names)
                refresh_taxpayer_editor()
                st.rerun()
        else:
            profiles[:] = [profile for profile in profiles if profile.id != deleted]
            for name in names:
                key = taxpayer_widget_key(f"identity_{name}")
                if st.session_state.get(key) == deleted:
                    st.session_state[key] = "unassigned"

    st.info(t(Messages.TAXPAYER_DISCOVERY_HELP))
    st.markdown(_EDITOR_STYLE, unsafe_allow_html=True)
    values: dict[UUID, str] = {}
    aliases_text: dict[UUID, str] = {}

    def render_profile(profile: _ProfileEditor, column, fallback: str) -> None:
        identifier = profile.id
        current = profile.saved.name if profile.saved else ""
        saved_aliases = "\\n".join(profile.saved.aliases) if profile.saved else ""
        column = column.container(key=editor_key(profile.kind, f"profile_{identifier}"))
        canonical_key = _editor_widget_key(f"canonical_{identifier}", current)
        column.markdown(f"**{st.session_state[canonical_key] or fallback}**")
        values[identifier] = column.text_input(t(Messages.CANONICAL_NAME), value=None, key=canonical_key)
        _field_actions(column, f"canonical_{identifier}", values[identifier], current)
        aliases_text[identifier] = column.text_area(
            t(Messages.ALIASES_ONE_PER_LINE), value=None,
            key=_editor_widget_key(f"aliases_{identifier}", saved_aliases),
        )
        _field_actions(column, f"aliases_{identifier}", aliases_text[identifier], saved_aliases)
        if profile.position is None:
            column.button(
                t(Messages.DELETE_CHILD), key=f"delete_{identifier}",
                on_click=_request_child_deletion, args=(identifier,),
            )

    taxpayers = [profile for profile in profiles if profile.position is not None]
    for profile, column in zip(taxpayers, st.columns(2)):
        fallback = t(Messages.FIRST_TAXPAYER) if profile.position is TaxpayerPosition.PRIMARY else t(Messages.SECOND_TAXPAYER_OPTIONAL)
        render_profile(profile, column, fallback)
    st.caption(t(Messages.SINGLE_TAXPAYER_HELP))
    st.subheader(t(Messages.MINOR_CHILDREN_ASSETS_ATTRIBUTED_TO_PARENTS))
    st.caption(t(Messages.MINOR_CHILDREN_HELP))
    if st.button(t(Messages.ADD_CHILD), key="add_child"):
        profiles.append(_ProfileEditor(uuid4()))
    children = [profile for profile in profiles if profile.position is None]
    for start in range(0, len(children), 2):
        for index, (profile, column) in enumerate(zip(children[start:start + 2], st.columns(2)), start=start):
            render_profile(profile, column, t.child(number=index + 1))

    labels: dict[IdentitySelection, str] = {"unassigned": t(Messages.UNASSIGNED)}
    for profile in taxpayers:
        fallback = t(Messages.FIRST_TAXPAYER_ENTER_A_NAME_ABOVE) if profile.position is TaxpayerPosition.PRIMARY else t(Messages.SECOND_TAXPAYER_ENTER_A_NAME_ABOVE)
        labels[profile.id] = values[profile.id].strip() or fallback
    labels.update({
        profile.id: values[profile.id].strip() or t.child_name_placeholder(number=index + 1)
        for index, profile in enumerate(children)
    })
    options: list[IdentitySelection] = ["unassigned", *(profile.id for profile in profiles)]
    assignments: dict[str, IdentitySelection] = {}
    if names:
        st.subheader(t(Messages.NAMES_FOUND_IN_DOCUMENTS))
        st.caption(t(Messages.IDENTITY_ASSIGNMENT_HELP))
        for index, name in enumerate(names):
            suggested = resolve_identity(name, household)
            identifier = suggested.id if suggested is not None else "unassigned"
            key = _editor_widget_key(f"identity_{name}", identifier)
            if st.session_state.get(key) not in options:
                st.session_state[key] = identifier
            selected_id = st.session_state[key]
            profile = next((profile for profile in profiles if profile.id == selected_id), None)
            with st.container(key=editor_key(profile.kind if profile else None, f"name_{index}")):
                selected = st.selectbox(
                    name, options, index=None, format_func=labels.get,
                    key=key, on_change=_assignment_changed,
                )
                assignments[name] = selected if selected in options else identifier
    changed = st.session_state.pop("taxpayer_assignment_changed", False)
    save = st.session_state.pop("taxpayer_save_requested", False)
    if save or changed:
        try:
            aliases = {
                profile.id: {alias.strip() for alias in aliases_text[profile.id].splitlines() if alias.strip()}
                for profile in profiles
            }
            for name, assignment in assignments.items():
                for profile_aliases in aliases.values():
                    profile_aliases.discard(name)
                if assignment != "unassigned":
                    aliases[assignment].add(name)
            identities = []
            for profile in profiles:
                name = values[profile.id].strip()
                if not name:
                    if aliases[profile.id]:
                        if profile.position is None:
                            raise ValueError(t(Messages.PROVIDE_A_CHILD_NAME_BEFORE_ASSIGNING_ALIASES_OR_DOCUMENTS))
                        raise ValueError("Provide a taxpayer name before assigning aliases.")
                    continue
                profile_aliases = tuple(sorted(aliases[profile.id] - {name}))
                identity = (
                    ChildIdentity(id=profile.id, name=name, aliases=profile_aliases)
                    if profile.position is None else
                    TaxpayerIdentity(id=profile.id, name=name, aliases=profile_aliases, position=profile.position)
                )
                identities.append(identity)
            updated = HouseholdSettings(
                identities=tuple(identities),
                unassigned_names=tuple(sorted(
                    (set(household.unassigned_names) | {name for name, assignment in assignments.items() if assignment == "unassigned"})
                    - {name for name, assignment in assignments.items() if assignment != "unassigned"}
                )),
            )
            save_settings(cfg, updated, str(cfg.import_root or ""))
            rebuild_recommendations(conn, updated)
        except (ValueError, OSError, sqlite3.Error) as exc:
            st.error(str(exc))
        else:
            st.session_state["settings_saved"] = True
            st.rerun()
    if st.session_state.pop("settings_saved", False):
        st.success(t(Messages.SETTINGS_SAVED))
    return household
