"""Desktop-only import controls; the importer remains UI independent."""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from pathlib import Path

import streamlit as st

from wr.desktop import desktop_request
from wr.desktop_storage import app_version, remember_folder, selected_folder
from wr.i18n import status_label, translator
from wr.import_pipeline import run_import

_IMPORT_LOCK = threading.Lock()


@dataclass
class ImportJob:
    stop: threading.Event = field(default_factory=threading.Event)
    done: threading.Event = field(default_factory=threading.Event)
    outcomes: list = field(default_factory=list)
    report: object = None
    error: str | None = None
    busy: bool = False

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
    directory = cfg.config_path.parent
    st.caption(t("Version {version} · Local processing · Data: {directory}", version=app_version(), directory=directory))
    st.info(t("Select a folder with annual statements and tax returns. Source files stay unchanged. Importing does not prove that your entire financial situation is covered."))
    job = st.session_state.get("import_job")
    active = job is not None and not job.done.is_set()
    if st.button(t("Select folder"), disabled=active, key="select_folder"):
        try:
            folder = desktop_request("folder")["folder"]
            if folder:
                remember_folder(directory, folder)
        except Exception as exc:
            st.error(t("Folder selection failed: {error}", error=exc))
    folder = selected_folder(directory)
    if folder:
        st.caption(t("Selected folder: {folder}", folder=folder))
    if st.button(t("Scan documents and calculate"), disabled=active or not folder, key="scan_documents"):
        if not Path(folder).is_dir():
            st.error(t("The selected folder is no longer available. Select another folder."))
        else:
            job = ImportJob()
            st.session_state.import_job = job
            threading.Thread(target=job.run, args=(folder, cfg), daemon=True).start()
    if st.button(t("Exit application"), disabled=active, key="exit_application"):
        desktop_request("stop")
        st.stop()
    if job:
        _render_job(job, language)
        if not job.done.is_set() or job.error or job.busy:
            st.stop()


@st.fragment(run_every=0.5)
def _render_job(job, language: str):
    t = translator(language)
    outcomes = list(job.outcomes)
    if outcomes:
        last = outcomes[-1]
        st.progress(last.index / last.total, text=f"{last.index}/{last.total}: {last.path.name}")
    elif not job.done.is_set():
        st.info(t("Searching for documents…"))
    if not job.done.is_set():
        if st.button(t("Stop import after current document"), key="cancel_import"):
            job.stop.set()
        st.caption(t("Imported documents are retained; calculations will be updated."))
    elif job.busy:
        st.error(t("Another dashboard window is already importing documents."))
    elif job.error:
        st.error(t("Import failed: {error}", error=job.error))
    else:
        report = job.report
        st.success(t("{status}: {parsed} processed, {duplicate} duplicate, {skipped} unrecognized, {failed} failed.",
                     status=t("Stopped") if report.cancelled else t("Done"), parsed=report.parsed,
                     duplicate=report.duplicate, skipped=report.skipped, failed=report.failed))
        if st.button(t("Refresh dashboard"), key="refresh_dashboard"):
            st.rerun()
    if outcomes:
        st.caption(t("Technical details from the source or parser are shown as recorded."))
        st.dataframe([{t("File"): str(o.path), t("Status"): status_label(o.status.value, language),
                       t("Institution"): o.issuer, t("Document"): status_label(o.doc_type, language),
                       t("Year"): o.tax_year, t("Details"): o.error}
                      for o in outcomes], hide_index=True)
