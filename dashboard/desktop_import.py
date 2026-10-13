"""Desktop-only import controls; the importer remains UI independent."""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from pathlib import Path

import streamlit as st

from wr.desktop import desktop_request
from wr.desktop_storage import app_version, remember_folder, selected_folder
from wr.import_pipeline import run_import

_IMPORT_LOCK = threading.Lock()


@dataclass
class ImportJob:
    stop: threading.Event = field(default_factory=threading.Event)
    done: threading.Event = field(default_factory=threading.Event)
    outcomes: list = field(default_factory=list)
    report: object = None
    error: str | None = None

    def run(self, folder, cfg):
        if not _IMPORT_LOCK.acquire(blocking=False):
            self.error = "Er loopt al een import in een ander dashboardvenster."
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


def render(cfg):
    directory = cfg.config_path.parent
    st.caption(f"Versie {app_version()} · Volledig lokale verwerking · Gegevens: {directory}")
    st.info("Selecteer een map met jaaroverzichten en aangiften. De bronbestanden blijven ongewijzigd. "
            "Importeren bewijst niet dat uw totale financiële situatie volledig is gedekt.")
    job = st.session_state.get("import_job")
    active = job is not None and not job.done.is_set()
    if st.button("Map selecteren", disabled=active):
        try:
            folder = desktop_request("folder")["folder"]
            if folder:
                remember_folder(directory, folder)
        except Exception as exc:
            st.error(f"Mapselectie mislukt: {exc}")
    folder = selected_folder(directory)
    if folder:
        st.caption(f"Geselecteerde map: {folder}")
    if st.button("Documenten scannen en berekenen", disabled=active or not folder):
        if not Path(folder).is_dir():
            st.error("De geselecteerde map is niet meer beschikbaar. Selecteer een andere map.")
        else:
            job = ImportJob()
            st.session_state.import_job = job
            threading.Thread(target=job.run, args=(folder, cfg), daemon=True).start()
    if st.button("Applicatie afsluiten", disabled=active):
        desktop_request("stop")
        st.stop()
    if job:
        _render_job(job)
        if not job.done.is_set() or job.error:
            st.stop()


@st.fragment(run_every=0.5)
def _render_job(job):
    outcomes = list(job.outcomes)
    if outcomes:
        last = outcomes[-1]
        st.progress(last.index / last.total, text=f"{last.index}/{last.total}: {last.path.name}")
    elif not job.done.is_set():
        st.info("Documenten zoeken…")
    if not job.done.is_set():
        if st.button("Import stoppen na huidig document"):
            job.stop.set()
        st.caption("Reeds geïmporteerde documenten blijven behouden; berekeningen worden bijgewerkt.")
    elif job.error:
        st.error(f"Import mislukt: {job.error}")
    else:
        report = job.report
        st.success(f"{'Gestopt' if report.cancelled else 'Gereed'}: {report.parsed} verwerkt, "
                   f"{report.duplicate} dubbel, {report.skipped} niet herkend, {report.failed} mislukt.")
        if st.button("Dashboard bijwerken"):
            st.rerun()
    if outcomes:
        st.dataframe([{"Bestand": str(o.path), "Status": o.status.value, "Instelling": o.issuer,
                       "Document": o.doc_type, "Jaar": o.tax_year, "Toelichting": o.error}
                      for o in outcomes], hide_index=True)
