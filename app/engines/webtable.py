"""Tables in web pages (and in web clips dragged out of a browser) as spreadsheets.

- xlsx: every table, one sheet each
- csv:  the biggest table

Merged cells are spread out the way they look (a cell spanning two columns fills
both), numbers become numbers when they plainly are (values like 007 or 1.50 stay
as written). The file is read back and compared cell by cell.
"""

from __future__ import annotations

import csv
from pathlib import Path

from ..errors import ConversionError, VerificationError
from ..paths import long_path


def _text(el) -> str:
    for br in el.iter("br"):
        br.tail = "\n" + (br.tail or "")
    return "\n".join(" ".join(line.split()) for line in "".join(el.itertext()).split("\n")).strip()


def read_tables(src: Path) -> list[list[list[str]]]:
    import lxml.html

    raw = Path(long_path(src)).read_bytes()
    try:
        doc = lxml.html.fromstring(raw)
    except Exception as e:  # noqa: BLE001
        raise ConversionError("This page can't be read.") from e
    tables = []
    for t in doc.iter("table"):
        if any(a.tag == "table" for a in t.iterancestors()):
            continue  # tables inside tables are part of their cell
        grid: dict[tuple[int, int], str] = {}
        r = 0
        for tr in t.iter("tr"):
            if next((a for a in tr.iterancestors() if a.tag == "table"), None) is not t:
                continue
            c = 0
            for cell in tr:
                if cell.tag not in ("td", "th"):
                    continue
                while (r, c) in grid:
                    c += 1
                text = _text(cell)
                try:
                    cs = max(1, min(50, int(cell.get("colspan", "1") or 1)))
                    rs = max(1, min(500, int(cell.get("rowspan", "1") or 1)))
                except ValueError:
                    cs = rs = 1
                for dr in range(rs):
                    for dc in range(cs):
                        grid[(r + dr, c + dc)] = text
                c += cs
            r += 1
        if not grid:
            continue
        rows = max(k[0] for k in grid) + 1
        cols = max(k[1] for k in grid) + 1
        table = [[grid.get((i, j), "") for j in range(cols)] for i in range(rows)]
        table = [row for row in table if any(cell for cell in row)]
        if len(table) >= 1 and cols >= 2 or len(table) >= 2:
            tables.append(table)
    if not tables:
        raise ConversionError("There's no table in this page.")
    return tables


def convert(sources: list[Path], out: Path, fmt: str, opts: dict) -> list[str]:
    from .data import _csv_value

    tables = read_tables(sources[0])
    if fmt == "csv":
        biggest = max(tables, key=lambda t: len(t) * len(t[0]))
        with open(long_path(out), "w", encoding="utf-8-sig", newline="") as f:
            csv.writer(f).writerows(biggest)
        with open(long_path(out), encoding="utf-8-sig", newline="") as f:
            if list(csv.reader(f)) != biggest:
                raise VerificationError("the table doesn't match the page")
        notes = [f"Checked: {len(biggest)} rows × {len(biggest[0])} columns, every cell as on the page."]
        if len(tables) > 1:
            notes.append(f"The biggest of {len(tables)} tables; choose XLSX to get them all.")
        return notes
    if fmt != "xlsx":
        raise ConversionError(f"Unknown table conversion: {fmt}")
    from openpyxl import Workbook, load_workbook
    from openpyxl.cell import WriteOnlyCell
    from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE

    wb = Workbook(write_only=True)
    expected = []
    for k, table in enumerate(tables[:250], 1):
        ws = wb.create_sheet(f"Table {k}")
        want = []
        for row in table:
            cells, vals = [], []
            for text in row:
                v = _csv_value(ILLEGAL_CHARACTERS_RE.sub("", text))
                cell = WriteOnlyCell(ws, value=v)
                if isinstance(v, str):
                    cell.data_type = "s"  # never a formula
                cells.append(cell)
                vals.append(v)
            ws.append(cells)
            want.append(vals)
        expected.append(want)
    wb.save(long_path(out))

    def trim(r) -> list:
        r = list(r)
        while r and r[-1] in (None, ""):
            r.pop()
        return r

    back = load_workbook(long_path(out), read_only=True)
    try:
        for ws, want in zip(back.worksheets, expected):
            if [trim(r) for r in ws.iter_rows(values_only=True)] != [trim(r) for r in want]:
                raise VerificationError(f"{ws.title} doesn't match the page")
    finally:
        back.close()
    cells = sum(len(r) for t in expected for r in t)
    return [f"Checked: {len(expected)} table{'s' if len(expected) != 1 else ''}, {cells:,} cells, one sheet each. "
            "Merged cells are spread out as they look."]
