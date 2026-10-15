"""Desktop-only import controls; the importer remains UI independent."""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from pathlib import Path

import streamlit as st

from wr.desktop.control import desktop_request
from wr.models.desktop import FolderResponse
from wr.desktop.storage import app_version, remember_folder, selected_folder
from wr.i18n import status_label, translator
from wr.messages import Messages
from wr.importing.pipeline import run_import
from dashboard.ui_state import refresh_taxpayer_editor

_IMPORT_LOCK = threading.Lock()


@dataclass
class ImportJob:
    stop: threading.Event = field(default_factory=threading.Event)
    done: threading.Event = field(default_factory=threading.Event)
    outcomes: list = field(default_factory=list)
    report: object = None
    error: str | None = None
    busy: bool = False
    editor_refreshed: bool = False

    def run(self, folder, cfg):
        if not _IMPORT_LOCK.acquire(blocking=False):
            self.busy = True
            self.done.set()
            return
        try:
            self.report = run_import(folder, cfg.resolved_db_path,
                                     partner_config=cfg.partners,
                                     institution_options=cfg.institution_options,
                                     progress=self.outcomes.append, cancelled=self.stop.is_set)
        except Exception as exc:
            self.error = str(exc)
        finally:
            _IMPORT_LOCK.release()
            self.done.set()


def render(cfg, language: str):
    t = translator(language)
    directory = cfg.project_root
    st.caption(t.version_details(version=app_version(), directory=directory))
    st.info(t(Messages.DESKTOP_IMPORT_HELP))
    job = st.session_state.get("import_job")
    active = job is not None and not job.done.is_set()
    if st.button(t(Messages.SELECT_FOLDER), disabled=active, key="select_folder"):
        try:
            response = desktop_request("folder")
            if not isinstance(response, FolderResponse):
                raise ValueError("Unexpected folder response")
            folder = response.folder
            if folder:
                remember_folder(directory, folder)
                st.rerun()
        except Exception as exc:
            st.error(t.folder_selection_failed(error=exc))
    folder = selected_folder(directory)
    if folder:
        st.caption(t.selected_folder(folder=folder))
    if st.button(t(Messages.SCAN_DOCUMENTS_AND_CALCULATE), disabled=active or not folder, key="scan_documents"):
        if not Path(folder).is_dir():
            st.error(t(Messages.SELECTED_FOLDER_UNAVAILABLE))
        else:
            job = ImportJob()
            st.session_state.import_job = job
            threading.Thread(target=job.run, args=(folder, cfg), daemon=True).start()
    if job:
        # Poll only while active. Completion requests one full dashboard rerun,
        # replacing the progress fragment with the refreshed analysis.
        st.fragment(run_every=0.5 if not job.done.is_set() else None)(_render_job)(job, language)
        if not job.done.is_set() or job.error or job.busy:
            st.stop()


def _render_job(job, language: str):
    t = translator(language)
    outcomes = list(job.outcomes)
    if outcomes:
        last = outcomes[-1]
        st.progress(last.index / last.total, text=f"{last.index}/{last.total}: {last.path.name}")
    elif not job.done.is_set():
        st.info(t(Messages.SEARCHING_FOR_DOCUMENTS))
    if not job.done.is_set():
        if st.button(t(Messages.STOP_IMPORT_AFTER_CURRENT_DOCUMENT), key="cancel_import"):
            job.stop.set()
        st.caption(t(Messages.IMPORT_STOP_HELP))
    elif job.busy:
        st.error(t(Messages.IMPORT_BUSY))
    elif job.error:
        st.error(t.import_failed(error=job.error))
    else:
        if not job.editor_refreshed:
            # A fragment rerun cannot render the overview or restore widgets
            # hidden during import. Refresh the entire app once, including for
            # cancelled or duplicate-only scans, and retain the import report.
            refresh_taxpayer_editor()
            job.editor_refreshed = True
            st.rerun(scope="app")
        report = job.report
        st.success(t.import_result(
                     status=t(Messages.STOPPED) if report.cancelled else t(Messages.DONE), parsed=report.parsed,
                     duplicate=report.duplicate, skipped=report.skipped, failed=report.failed))
    if outcomes:
        st.caption(t(Messages.IMPORT_DIAGNOSTICS_HELP))
        st.dataframe([{t(Messages.FILE): str(o.path), t(Messages.STATUS): status_label(o.status.value, language),
                       t(Messages.INSTITUTION): o.issuer, t(Messages.DOCUMENT): status_label(o.doc_type, language),
                       t(Messages.YEAR): o.tax_year, t(Messages.DETAILS): o.error}
                      for o in outcomes], hide_index=True)
