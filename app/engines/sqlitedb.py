"""SQLite databases (the files many apps keep their data in) as tables you can open.

- xlsx: one sheet per table
- csv:  one CSV per table, in a new folder

The database is opened read-only, without even a lock file: the original can't
change. Pictures and other binary values are written as "(binary, N bytes)".
Every table is read back from the new file(s) and compared, row by row.
"""

from __future__ import annotations

import csv
import re
import sqlite3
from pathlib import Path

from ..errors import ConversionError, VerificationError
from ..paths import long_path

EXCEL_MAX_ROWS = 1_048_575  # plus the header row


def _connect(src: Path) -> sqlite3.Connection:
    with open(long_path(src), "rb") as f:
        if f.read(16) != b"SQLite format 3\x00":
            raise ConversionError("This isn't a SQLite database (some apps use .db for other kinds of data).")
    uri = Path(src).absolute().as_uri() + "?mode=ro&immutable=1"
    try:
        return sqlite3.connect(uri, uri=True)
    except sqlite3.Error as e:
        raise ConversionError(f"This database can't be opened ({e}).") from e


def _value(v):
    if isinstance(v, bytes):
        return f"(binary, {len(v):,} bytes)"
    if isinstance(v, int) and not isinstance(v, bool) and abs(v) >= 10 ** 15:
        return str(v)  # Excel keeps 15 digits: longer numbers stay exact as text
    if isinstance(v, str):
        return re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", v)  # control characters Excel can't store
    return v


def read_tables(src: Path) -> list[tuple[str, list[str], list[list]]]:
    con = _connect(src)
    try:
        names = [r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
        if not names:
            raise ConversionError("This database has no tables.")
        out = []
        for name in names:
            cur = con.execute(f'SELECT * FROM "{name.replace(chr(34), chr(34) * 2)}"')
            cols = [d[0] for d in cur.description]
            rows = [[_value(v) for v in row] for row in cur]
            out.append((name, cols, rows))
        return out
    except sqlite3.DatabaseError as e:
        raise ConversionError(f"This database is damaged or encrypted ({e}).") from e
    finally:
        con.close()


def _sheet_names(names: list[str]) -> list[str]:
    used, out = set(), []
    for n in names:
        base = re.sub(r"[\[\]:*?/\\]", "_", n)[:31] or "Table"
        name, k = base, 2
        while name.lower() in used:
            tail = f" ({k})"
            name, k = base[:31 - len(tail)] + tail, k + 1
        used.add(name.lower())
        out.append(name)
    return out


def to_xlsx(src: Path, out: Path, notes: list[str]) -> None:
    from openpyxl import Workbook, load_workbook
    from openpyxl.styles import Font

    tables = read_tables(src)
    big = [n for n, _c, rows in tables if len(rows) > EXCEL_MAX_ROWS]
    if big:
        raise ConversionError(f"The table {big[0]} has more rows than Excel holds. Use CSV per table instead.")
    names = _sheet_names([t[0] for t in tables])
    wb = Workbook(write_only=True)
    bold = Font(bold=True)
    from openpyxl.cell import WriteOnlyCell

    for sheet, (_n, cols, rows) in zip(names, tables):
        ws = wb.create_sheet(sheet)
        ws.freeze_panes = "A2"
        head = []
        for c in cols:
            cell = WriteOnlyCell(ws, value=str(c))
            cell.font = bold
            head.append(cell)
        ws.append(head)
        for r in rows:
            cells = []
            for v in r:
                cell = WriteOnlyCell(ws, value=v)
                if isinstance(v, str):
                    cell.data_type = "s"  # never a formula
                cells.append(cell)
            ws.append(cells)
    wb.save(long_path(out))

    def norm(row) -> list:
        row = [None if v == "" else v for v in row]
        while row and row[-1] is None:
            row.pop()
        return row

    back = load_workbook(long_path(out), read_only=True)
    try:
        if len(back.worksheets) != len(tables):
            raise VerificationError("a table is missing from the workbook")
        for ws, (name, cols, rows) in zip(back.worksheets, tables):
            got = [norm(r) for r in ws.iter_rows(values_only=True)]
            want = [norm(cols)] + [norm(r) for r in rows]
            while got and not got[-1]:
                got.pop()
            while want and not want[-1]:
                want.pop()
            if got != want:
                raise VerificationError(f"the table {name} doesn't match the database")
    finally:
        back.close()
    _note(tables, notes, "one sheet each")


def to_csvs(src: Path, out_dir: Path, notes: list[str]) -> None:
    tables = read_tables(src)
    out_dir.mkdir(parents=True, exist_ok=True)
    for file, (name, cols, rows) in zip(_sheet_names([t[0] for t in tables]), tables):
        path = out_dir / f"{file}.csv"
        with open(long_path(path), "w", encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f)
            w.writerow(cols)
            w.writerows([["" if v is None else v for v in r] for r in rows])
        with open(long_path(path), encoding="utf-8-sig", newline="") as f:
            back = list(csv.reader(f))
        want = [[str(c) for c in cols]] + [["" if v is None else str(v) for v in r] for r in rows]
        if back != want:
            raise VerificationError(f"the table {name} doesn't match the database")
    _note(tables, notes, "one CSV each, in a new folder")


def _note(tables, notes: list[str], how: str) -> None:
    n_rows = sum(len(r) for _n, _c, r in tables)
    blobs = sum(1 for _n, _c, rows in tables for r in rows for v in r if isinstance(v, str)
                and v.startswith("(binary, "))
    notes.append(f"Checked: {len(tables)} table{'s' if len(tables) != 1 else ''}, {n_rows:,} rows, {how}. "
                 "The database was only read.")
    if blobs:
        notes.append(f"{blobs:,} binary values (like pictures) are shown as their size.")


def convert(sources: list[Path], out: Path, fmt: str, opts: dict) -> list[str]:
    notes: list[str] = []
    if fmt == "xlsx":
        to_xlsx(sources[0], out, notes)
    elif fmt == "csv":
        to_csvs(sources[0], out, notes)
    else:
        raise ConversionError(f"Unknown database conversion: {fmt}")
    return notes
