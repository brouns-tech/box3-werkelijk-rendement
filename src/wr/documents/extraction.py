from __future__ import annotations

from contextlib import closing
from importlib.metadata import version
from pathlib import Path
import threading


_PDF_LOCK = threading.Lock()


def extraction_profile() -> str:
    """Version the native extractor and layout algorithm for safe reprocessing."""
    return f"pdfium-layout-v2/parsers-v3/pypdfium2-{version('pypdfium2')}"


def extract_text(path: Path, max_pages: int | None = None) -> tuple[str, int]:
    """Use the same bundled, position-based extractor in CLI and desktop builds.

    PDFium is not thread-safe. Keep all native handles inside this lock and
    release them explicitly. Extraction errors are reported, never replaced by
    an unvalidated fallback with different financial-data semantics.
    """
    import pypdfium2 as pdfium
    from wr.documents.layout import layout_page

    if max_pages is not None and max_pages < 0:
        raise ValueError("max_pages must be non-negative")
    with _PDF_LOCK, pdfium.PdfDocument(path) as document:
        count = len(document)
        selected = count if max_pages is None else min(count, max_pages)
        texts = []
        for index in range(selected):
            with closing(document[index]) as page:
                texts.append(layout_page(page))
        return "\n\f\n".join(texts), count
