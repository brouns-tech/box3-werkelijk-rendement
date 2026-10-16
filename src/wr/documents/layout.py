"""Reconstruct statement rows from PDFium word positions, not content-stream order."""
from __future__ import annotations

from contextlib import closing
import ctypes
import math
import statistics

from pypdfium2 import raw


def layout_page(page) -> str:
    with closing(page.get_textpage()) as textpage:
        return _layout_textpage(textpage)


def _layout_textpage(textpage) -> str:
    words = []
    word = []

    def finish():
        if word:
            words.append((
                min(c[4] for c in word),
                statistics.median(c[1] for c in word),
                ''.join(c[2] for c in word),
                statistics.median(c[3] for c in word),
                max(c[5] for c in word),
            ))
            word.clear()
    horizontal = rotated = 0
    for i in range(textpage.count_chars()):
        code = raw.FPDFText_GetUnicode(textpage, i)
        char = chr(code) if code else ''
        if abs(math.sin(raw.FPDFText_GetCharAngle(textpage, i))) > 0.1:
            if char and not char.isspace():
                rotated += 1
            finish()
            continue
        if not char or char.isspace() or code < 32:
            finish()
            continue
        horizontal += 1
        x, y = ctypes.c_double(), ctypes.c_double()
        raw.FPDFText_GetCharOrigin(textpage, i, x, y)
        left, bottom, right, top = textpage.get_charbox(i)
        size = raw.FPDFText_GetFontSize(textpage, i)
        if word and abs(y.value - word[-1][1]) > 2:
            finish()
        word.append((x.value, y.value, char, size, left, right))
    finish()
    if rotated > horizontal:
        raise ValueError('Rotated body text is not supported; review this document layout.')
    if not words:
        return ''
    # Typical character pitch controls table padding, never the numeric values.
    pitch = max(0.1, statistics.median(c[3] for c in words) * 0.45)
    # Two PDF points allow minor baseline differences within a statement row.
    rows = []
    for word in sorted(words, key=lambda c: (-c[1], c[0])):
        if not rows or abs(rows[-1][0] - word[1]) > 2:
            rows.append((word[1], [word]))
        else:
            rows[-1][1].append(word)
    lines = []
    for y, words in rows:
        line = ''
        previous = None
        for left, _, word, size, right in sorted(words, key=lambda c: c[0]):
            if previous is not None:
                gap = left - previous
                line += ' ' * (max(2, round(gap / pitch)) if gap > size * 1.3 else 1)
            line += word
            previous = right
        lines.append(line.rstrip())
    return '\n'.join(lines)
