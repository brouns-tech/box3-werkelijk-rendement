"""Minimal offline diagnostic for installed and frozen applications."""
from __future__ import annotations

import json
from pathlib import Path
import sqlite3
from zipfile import ZipFile


def _write_probe_pdf(path: Path) -> None:
    from pypdf import PdfWriter
    from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

    writer = PdfWriter()
    page = writer.add_blank_page(width=900, height=900)
    font = DictionaryObject({
        NameObject("/Type"): NameObject("/Font"),
        NameObject("/Subtype"): NameObject("/Type1"),
        NameObject("/BaseFont"): NameObject("/Courier"),
    })
    page[NameObject("/Resources")] = DictionaryObject({
        NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)}),
    })
    stream = DecodedStreamObject()
    stream.set_data(b"\n".join([
        b"BT /F1 10 Tf 20 850 Td 14 TL",
        b"(ING Jaaroverzicht 2024) Tj T*",
        b"(ING Oranje Spaarrekening: H 000-00000 Hr ALEX EXAMPLE) Tj T*",
        b"(Saldo op 01-01-2024 1.000,00) Tj T*",
        b"(Saldo op 31-12-2024 1.012,34) Tj T*",
        b"(Rente, ontvangen in 2024 12,34) Tj T*",
        b"ET",
    ]))
    page[NameObject("/Contents")] = writer._add_object(stream)
    writer.write(path)


def run_selfcheck(directory: Path) -> None:
    from dashboard.explorer_compat import DirPicker
    from wr.calculations.service import recompute
    from wr.desktop.storage import app_version, prepare_workspace
    from wr.documents.extraction import extract_text
    from wr.export import write_audit_export
    from wr.importing.pipeline import run_import
    from wr.parsers import PLUGINS
    from wr.workspace.settings import load_settings

    directory.mkdir(parents=True, exist_ok=True)
    result_path = directory / "smoke-result.json"
    result_path.unlink(missing_ok=True)
    if not callable(DirPicker):
        raise RuntimeError("Desktop folder-picker dependency is unavailable")
    config = prepare_workspace(directory)
    documents = directory / "selfcheck-documents"
    documents.mkdir(exist_ok=True)
    source = documents / "diagnostic.pdf"
    _write_probe_pdf(source)
    text, pages = extract_text(source)
    if pages != 1 or "ING Jaaroverzicht 2024" not in text:
        raise RuntimeError("PDFium could not extract the diagnostic PDF")
    database = load_settings(config).resolved_db_path
    report = run_import(documents, database)
    if report.failed or report.parsed + report.duplicate != 1:
        raise RuntimeError("Diagnostic PDF import did not produce a parsed document")
    recompute(database)
    with sqlite3.connect(database) as conn:
        portfolio = conn.execute(
            "SELECT known_combined_actual_return, source_fact_count FROM yearly_portfolio WHERE tax_year=2024"
        ).fetchone()
    if portfolio != (12.34, 1):
        raise RuntimeError("Diagnostic portfolio calculation did not produce the expected result")
    export = write_audit_export(database, directory / "audit.zip")
    with ZipFile(export) as bundle:
        required = {"manifest.json", "source_facts.csv", "yearly_summary.csv"}
        if not required.issubset(bundle.namelist()) or bundle.testzip() is not None:
            raise RuntimeError("Diagnostic audit export is incomplete or corrupt")
    result_path.write_text(json.dumps({
        "version": app_version(), "parsers": len(PLUGINS),
        "pdf_backend": "pdfium", "config": str(config),
    }), encoding="utf-8")
