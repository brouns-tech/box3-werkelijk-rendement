"""Workspace settings and local document-folder selection."""
from __future__ import annotations

from pathlib import Path

import streamlit as st

from dashboard.folder_picker import folder_path_input
from wr.config import PartnerSettings, resolve_db_path, save_settings
from wr.identities import effective_partners, identity_slot, observed_names
from wr.import_pipeline import run_import
from wr.recommend import rebuild_recommendations


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
            # Rebuild the editor from saved settings and newly detected names.
            for key in list(st.session_state):
                if key.startswith(("canonical_", "aliases_", "identity_")):
                    del st.session_state[key]
            st.rerun()
    if st.session_state.pop("folder_saved", False):
        st.success("Document folder saved.")
    if "import_summary" in st.session_state:
        st.info(st.session_state.pop("import_summary"))


def taxpayers_ui(cfg, conn) -> PartnerSettings:
    st.subheader("Taxpayers")
    st.caption("Settings are saved in this workspace and reused across sessions. Existing TOML settings are used until you save here.")
    partners = effective_partners(conn, cfg.partners)
    names = observed_names(conn)

    st.info("Detected identities are best guesses based on names. Review shared initials and add nicknames as aliases. Fiscal partnership and allocation come from each tax return.")
    columns = st.columns(2)
    values = {}
    for slot, column in zip(("a", "b"), columns):
        fallback = "First taxpayer" if slot == "a" else "Second taxpayer (optional)"
        current = getattr(partners, f"partner_{slot}") or ""
        column.markdown(f"**{st.session_state.get(f'canonical_{slot}', current) or fallback}**")
        values[slot] = column.text_input("Canonical name", value=current, key=f"canonical_{slot}")
        values[f"aliases_{slot}"] = column.text_area(
            "Aliases (one per line)", value="\n".join(partners.aliases_for(slot)),
            key=f"aliases_{slot}",
        )
    st.caption("For one identity, clear the second name and assign its spellings to the remaining person. Two identities do not imply full-year fiscal partnership.")
    labels = {
        "unassigned": "Unassigned",
        "a": values["a"].strip() or "First taxpayer (enter a name above)",
        "b": values["b"].strip() or "Second taxpayer (enter a name above)",
    }
    assignments = {}
    if names:
        st.markdown("**Names found in documents**")
        st.caption("Choose the person each spelling belongs to, or leave it unassigned. These assignments take precedence over the alias text above. Source names are preserved.")
        for name in names:
            options = ["unassigned", "a", "b"]
            slot = identity_slot(name, partners) or "unassigned"
            assignments[name] = st.selectbox(
                name, options, index=options.index(slot), format_func=labels.get,
                key=f"identity_{name}",
            )
    if st.button("Save settings and update analysis", key="save_settings"):
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
        except (ValueError, OSError) as exc:
            st.error(str(exc))
        else:
            st.session_state["settings_saved"] = True
            st.rerun()
    if st.session_state.pop("settings_saved", False):
        st.success("Settings saved.")
    return partners
