from __future__ import annotations

import hashlib
import re
import shutil
import subprocess
from pathlib import Path


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def extract_text(path: Path, max_pages: int | None = None) -> tuple[str, int | None]:
    """Extract PDF text. Prefer pdftotext; fall back to pypdf."""
    if shutil.which("pdftotext"):
        cmd = ["pdftotext", "-layout", str(path), "-"]
        if max_pages is not None:
            cmd = ["pdftotext", "-layout", "-f", "1", "-l", str(max_pages), str(path), "-"]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
            if proc.returncode == 0 and proc.stdout.strip():
                page_count = _count_form_feeds(proc.stdout)
                return proc.stdout, page_count or None
        except OSError:
            pass

    from pypdf import PdfReader

    reader = PdfReader(str(path))
    pages = reader.pages
    if max_pages is not None:
        pages = pages[:max_pages]
    text = "\n".join((p.extract_text() or "") for p in pages)
    return text, len(reader.pages)


def _count_form_feeds(text: str) -> int:
    return text.count("\x0c") + (1 if text.strip() else 0)


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
