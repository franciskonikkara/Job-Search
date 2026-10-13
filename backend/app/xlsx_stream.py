"""Memory-safe streaming reader for very large .xlsx files.

The USCIS Employer Data Hub files the user provided are small on disk but huge
uncompressed (100s of MB of XML, ~1M+ rows). openpyxl and pandas load the whole
tree and effectively hang. This module streams the file instead:

  1. Stream `xl/sharedStrings.xml` once with iterparse, building an index->text
     list. This is the one unavoidable in-memory structure, but it holds only
     the strings (not the whole workbook) and each <si> is cleared as we go.
  2. Stream `xl/worksheets/sheet1.xml` row by row, resolving shared-string
     cell references against the list, yielding one row (list of str) at a time.

Only one row is held in memory at a time during iteration, so we can process
millions of rows with bounded memory.
"""
from __future__ import annotations

import zipfile
from collections.abc import Iterator
from xml.etree.ElementTree import iterparse

_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"


def _load_shared_strings(z: zipfile.ZipFile) -> list[str]:
    """Stream sharedStrings.xml into a list. Clears each node to bound memory."""
    strings: list[str] = []
    try:
        info = z.getinfo("xl/sharedStrings.xml")
    except KeyError:
        return strings
    with z.open(info) as fh:
        for _event, el in iterparse(fh, events=("end",)):
            if el.tag == f"{_NS}si":
                # Concatenate all <t> text within this shared-string item.
                strings.append("".join(t.text or "" for t in el.iter(f"{_NS}t")))
                el.clear()
    return strings


def _col_letters(ref: str) -> str:
    """Extract the column letters from a cell reference like 'C12' -> 'C'."""
    out = []
    for ch in ref:
        if ch.isalpha():
            out.append(ch)
        else:
            break
    return "".join(out)


def _col_index(letters: str) -> int:
    """Convert column letters to a 0-based index. 'A'->0, 'B'->1, 'AA'->26."""
    idx = 0
    for ch in letters:
        idx = idx * 26 + (ord(ch.upper()) - ord("A") + 1)
    return idx - 1


def iter_xlsx_rows(
    path: str, sheet_path: str = "xl/worksheets/sheet1.xml"
) -> Iterator[list[str]]:
    """Yield rows (lists of cell strings) from a large xlsx, memory-safely.

    Empty cells are filled so each row's positions line up with the header.
    """
    z = zipfile.ZipFile(path)
    shared = _load_shared_strings(z)

    with z.open(sheet_path) as fh:
        for _event, el in iterparse(fh, events=("end",)):
            if el.tag != f"{_NS}row":
                continue
            cells: dict[int, str] = {}
            max_idx = -1
            for c in el.findall(f"{_NS}c"):
                ref = c.get("r") or ""
                col = _col_index(_col_letters(ref)) if ref else len(cells)
                t = c.get("t")
                value: str | None = None
                v = c.find(f"{_NS}v")
                if t == "s" and v is not None and v.text is not None:
                    i = int(v.text)
                    value = shared[i] if 0 <= i < len(shared) else ""
                elif t == "inlineStr":
                    is_ = c.find(f"{_NS}is")
                    if is_ is not None:
                        value = "".join(tt.text or "" for tt in is_.iter(f"{_NS}t"))
                elif v is not None:
                    value = v.text
                cells[col] = "" if value is None else value
                if col > max_idx:
                    max_idx = col
            row = [cells.get(i, "") for i in range(max_idx + 1)]
            el.clear()
            yield row
