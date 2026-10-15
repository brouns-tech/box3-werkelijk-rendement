from __future__ import annotations

import hashlib
import re
from importlib.metadata import version
from contextlib import closing
import threading
from pathlib import Path


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


_PDF_LOCK = threading.Lock()


def extraction_profile() -> str:
    """Version the native extractor and layout algorithm for safe reprocessing."""
    return f"pdfium-layout-v2/parsers-v5/pypdfium2-{version('pypdfium2')}"


def extract_text(path: Path, max_pages: int | None = None) -> tuple[str, int]:
    """Use the same bundled, position-based extractor in CLI and desktop builds.

    PDFium is not thread-safe. Keep all native handles inside this lock and
    release them explicitly. Extraction errors are reported, never replaced by
    an unvalidated fallback with different financial-data semantics.
    """
    import pypdfium2 as pdfium
    from wr.pdf_layout import layout_page

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


_NL_AMOUNT = re.compile(
    r"""
    (?<![A-Za-z0-9])
    (-?)
    (?:
        \d{1,3}(?:\.\d{3})+(?:,\d{1,2})?   # 1.234,56 or 1.234
      | \d+(?:,\d{1,2})?                  # 1234,56 or 12
    )
    (?![A-Za-z0-9])
    """,
    re.VERBOSE,
)

_EN_AMOUNT = re.compile(
    r"""
    (?<![A-Za-z0-9])
    (-?)
    (?:
        \d{1,3}(?:,\d{3})+(?:\.\d{1,2})?
      | \d+(?:\.\d{1,2})?
    )
    (?![A-Za-z0-9])
    """,
    re.VERBOSE,
)


def parse_nl_amount(raw: str) -> float | None:
    """Parse Dutch-formatted amount like 1.234,56 or -98.913 (dot = thousands)."""
    s = raw.strip().replace("€", "").replace("EUR", "").replace(" ", "")
    if not s:
        return None
    # OCR-ish junk sometimes appears; keep digits/separators/sign.
    s = re.sub(r"[^\d.,\-]", "", s)
    if not s or s in {"-", ".", ","}:
        return None
    negative = s.startswith("-")
    s = s.lstrip("-")
    if "," in s and "." in s:
        # 1.234,56
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        # 1234,56
        s = s.replace(",", ".")
    elif "." in s:
        parts = s.split(".")
        # Dutch thousands: 204.895 or 1.234.567 — final group length 3, no decimals
        if all(p.isdigit() for p in parts) and all(len(p) == 3 for p in parts[1:]):
            s = "".join(parts)
        # else keep as decimal (e.g. 14.29 unlikely in tax ints, but allow)
    try:
        val = float(s)
    except ValueError:
        return None
    return -val if negative else val


def parse_en_amount(raw: str) -> float | None:
    s = raw.strip().replace("€", "").replace("$", "").replace("EUR", "").replace("USD", "").replace(" ", "")
    s = re.sub(r"[^\d.,\-]", "", s)
    if not s:
        return None
    negative = s.startswith("-")
    s = s.lstrip("-")
    if "," in s and "." in s:
        s = s.replace(",", "")
    elif "," in s and "." not in s:
        # ambiguous; treat as thousands if 1,234 style
        if re.fullmatch(r"\d{1,3}(,\d{3})+", s):
            s = s.replace(",", "")
        else:
            s = s.replace(",", ".")
    try:
        val = float(s)
    except ValueError:
        return None
    return -val if negative else val


def find_nl_amounts(text: str) -> list[float]:
    out: list[float] = []
    for m in _NL_AMOUNT.finditer(text):
        v = parse_nl_amount(m.group(0))
        if v is not None:
            out.append(v)
    return out


def normalize_iban(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "", value).upper()


def normalize_account_id(value: str) -> str:
    cleaned = value.strip()
    if re.search(r"[A-Z]{2}\d{2}", cleaned.replace(".", "").replace(" ", ""), re.I):
        return normalize_iban(cleaned)
    return re.sub(r"\s+", "", cleaned).lower()
