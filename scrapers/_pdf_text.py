"""Pure-stdlib PDF text extractor — county-side helper.

Implements minimal PDF text extraction using only the standard library
(`re`, `zlib`). Decompresses FlateDecode streams and extracts text from
the `(...) Tj` and `[(...)(...)] TJ` operators. Sufficient for the
county-side PDF sources (PBFCM tax-resale list, Smith County District
Clerk Registry & Trust Accounts / Excess Proceeds report) which use
straightforward ActiveReports- or LaTeX-generated PDFs.

Not a general-purpose PDF parser. Skips encrypted PDFs, ASCII85/LZW
streams, type 3 fonts, and complex content streams. For those the
framework's documented PDF readers (`pdfplumber`, `PyMuPDF`) are the
right tools — but they're external deps; this stays stdlib-only so the
adapters that use it remain stdlib-pure.
"""
from __future__ import annotations

import re
import zlib

_STREAM_RE = re.compile(rb'<<(.{0,2000}?)>>\s*stream\r?\n(.*?)\r?\nendstream', re.S)
_TJ_RE = re.compile(rb'\(((?:\\.|[^\\)])*)\)\s*Tj')
_TJARR_RE = re.compile(rb'\[([^\]]*)\]\s*TJ')
_TJARR_PIECE_RE = re.compile(rb'\(((?:\\.|[^\\)])*)\)')


def _unescape(b: bytes) -> bytes:
    return (b
            .replace(b'\\(', b'(').replace(b'\\)', b')')
            .replace(b'\\\\', b'\\').replace(b'\\n', b'\n')
            .replace(b'\\t', b'\t').replace(b'\\r', b''))


def extract_text(pdf_bytes: bytes) -> str:
    """Extract text from a PDF as one concatenated string. Falls through
    silently on streams that aren't FlateDecode-compressed text streams."""
    out: list = []
    for m in _STREAM_RE.finditer(pdf_bytes):
        dict_part, data = m.group(1), m.group(2)
        if b'FlateDecode' in dict_part:
            try:
                data = zlib.decompress(data)
            except zlib.error:
                try:
                    data = zlib.decompress(data, -15)  # raw deflate
                except Exception:
                    continue
        for t in _TJ_RE.findall(data):
            try:
                out.append(_unescape(t).decode('utf-8', errors='replace'))
            except Exception:
                pass
        for arr in _TJARR_RE.findall(data):
            for piece in _TJARR_PIECE_RE.findall(arr):
                try:
                    out.append(_unescape(piece).decode('utf-8', errors='replace'))
                except Exception:
                    pass
    return ''.join(out)
