"""Data files: CSV / TSV / JSON / Excel.

- xlsx:   CSV/TSV/JSON -> Excel workbook. A value becomes a number only when
          Excel would show exactly the same text (so 007, 1.50, +44 and long
          IDs stay as written). Text starting with = is never run as a formula.
- json:   CSV/TSV -> a list of records (first row = field names)
- csv:    JSON (a list of records, or a list of lists) -> CSV (UTF-8, opens in Excel)
- tidy / minify: JSON re-flowed. Every value is copied character for character,
          so numbers like 1.10 or 0.1000000000000000055 keep their exact text.

Every output is read back and compared with the source.
"""

from __future__ import annotations

import csv
import io
import json
import re
from decimal import Decimal
from pathlib import Path

from ..errors import ConversionError, VerificationError
from ..paths import long_path

EXCEL_MAX_ROWS, EXCEL_MAX_COLS, EXCEL_MAX_TEXT = 1_048_576, 16_384, 32_767
INT_RE = re.compile(r"-?(0|[1-9]\d{0,14})")  # up to 15 digits: Excel keeps them all
FLOAT_RE = re.compile(r"-?(0|[1-9]\d*)\.\d*[1-9]")  # no trailing zeros (Excel would drop them)


def _n(count: int, word: str) -> str:
    return f"{count:,} {word}{'' if count == 1 else 's'}"


# ---------------------------------------------------------------- reading

def _read_text(src: Path, notes: list[str]) -> str:
    raw = Path(long_path(src)).read_bytes()
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        notes.append("The file wasn't UTF-8, so it was read as Windows (ANSI) text.")
        return raw.decode("cp1252", errors="replace")


def _read_table(src: Path, notes: list[str]) -> list[list[str]]:
    text = _read_text(src, notes)
    if src.suffix.lower() == ".tsv":
        delimiter = "\t"
    else:
        try:
            delimiter = csv.Sniffer().sniff(text[:65536], delimiters=",;\t|").delimiter
        except csv.Error:
            delimiter = ","
        if delimiter != ",":
            notes.append(f"Columns are separated by {'tabs' if delimiter == chr(9) else repr(delimiter)}.")
    rows = list(csv.reader(io.StringIO(text, newline=""), delimiter=delimiter))
    while rows and not any(c.strip() for c in rows[-1]):
        rows.pop()
    if not rows:
        raise ConversionError("The file is empty.")
    return rows


def _load_json(src: Path, notes: list[str]):
    text = _read_text(src, notes)
    try:
        return text, json.loads(text, parse_float=Decimal)
    except json.JSONDecodeError as e:
        raise ConversionError(f"This isn't valid JSON (line {e.lineno}, column {e.colno}: {e.msg}).") from e


def _json_table(data) -> list[list]:
    """A list of records / list of lists / single record -> rows (header first)."""
    if isinstance(data, dict):
        lists = [v for v in data.values() if isinstance(v, list) and v and all(isinstance(x, dict) for x in v)]
        data = lists[0] if len(lists) == 1 else [data]
    if not isinstance(data, list) or not data:
        raise ConversionError("This JSON isn't a table. It needs to be a list of records, like "
                              '[{"name": "A", "age": 3}, ...].')
    if all(isinstance(x, list) for x in data):
        return [list(r) for r in data]
    if not all(isinstance(x, dict) for x in data):
        raise ConversionError("This JSON mixes records with other values, so it can't become a table.")
    columns: dict[str, None] = {}
    for rec in data:
        for k in rec:
            columns.setdefault(k, None)
    header = list(columns)
    return [header] + [[rec.get(k, None) for k in header] for rec in data]


def _json_cell_text(v) -> str:
    if v is None:
        return ""
    if isinstance(v, str):
        return v
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, Decimal)):
        return str(v)
    return json.dumps(v, ensure_ascii=False, default=str)


# ---------------------------------------------------------------- typing

def _number(text: str):
    """The number Excel should hold, or None to keep the text as-is."""
    if INT_RE.fullmatch(text):
        return int(text)
    if FLOAT_RE.fullmatch(text) and len(text.replace("-", "").replace(".", "").lstrip("0")) <= 15:
        f = float(text)
        if repr(f) == text:
            return f
    return None


def _csv_value(text: str):
    if text == "":
        return None
    n = _number(text)
    return text if n is None else n


def _json_value(v):
    if v is None or isinstance(v, (str, bool)):
        return v
    if isinstance(v, int):
        return v if abs(v) < 10 ** 15 else str(v)
    if isinstance(v, Decimal):
        n = _number(str(v))
        return str(v) if n is None else n
    return json.dumps(v, ensure_ascii=False, default=str)


# ---------------------------------------------------------------- xlsx

def _write_xlsx(rows: list[list], out: Path, notes: list[str], sheet: str) -> list[list]:
    from openpyxl import Workbook
    from openpyxl.cell import WriteOnlyCell
    from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
    from openpyxl.styles import Font
    from openpyxl.utils import get_column_letter

    if len(rows) > EXCEL_MAX_ROWS:
        raise ConversionError(f"Excel holds at most {EXCEL_MAX_ROWS:,} rows; this file has {len(rows):,}.")
    width = max(len(r) for r in rows)
    if width > EXCEL_MAX_COLS:
        raise ConversionError(f"Excel holds at most {EXCEL_MAX_COLS:,} columns; this file has {width:,}.")
    wb = Workbook(write_only=True)
    ws = wb.create_sheet(re.sub(r"[\[\]:*?/\\]", "_", sheet)[:31] or "Sheet1")
    ws.freeze_panes = "A2"
    for c in range(width):  # column widths from the first rows
        longest = max((len(str(r[c])) for r in rows[:200] if c < len(r) and r[c] is not None), default=6)
        ws.column_dimensions[get_column_letter(c + 1)].width = min(60, max(8, longest + 2))
    bold = Font(bold=True)
    cleaned = 0
    expected = []
    for i, row in enumerate(rows):
        cells, want = [], []
        for v in row:
            if isinstance(v, str):
                if ILLEGAL_CHARACTERS_RE.search(v):
                    v, cleaned = ILLEGAL_CHARACTERS_RE.sub("", v), cleaned + 1
                if len(v) > EXCEL_MAX_TEXT:
                    raise ConversionError(f"A cell has more than {EXCEL_MAX_TEXT:,} characters, which Excel "
                                          "can't hold.")
                if v == "":
                    v = None
            cell = WriteOnlyCell(ws, value=v)
            if isinstance(v, str) and cell.data_type != "s":
                cell.data_type = "s"  # never a formula
            if i == 0:
                cell.font = bold
            cells.append(cell)
            want.append(v)
        ws.append(cells)
        expected.append(want)
    wb.save(long_path(out))
    if cleaned:
        notes.append(f"{cleaned} cell(s) had invisible control characters that Excel can't store; they were "
                     "removed.")
    return expected


def _check_xlsx(out: Path, expected: list[list]) -> None:
    from openpyxl import load_workbook

    def trim(row):
        row = list(row)
        while row and row[-1] is None:
            row.pop()
        return row

    wb = load_workbook(long_path(out), read_only=True)
    try:
        got = [trim(r) for r in wb.worksheets[0].iter_rows(values_only=True)]
    finally:
        wb.close()
    want = [trim(r) for r in expected]
    while got and not got[-1]:
        got.pop()
    while want and not want[-1]:
        want.pop()
    if len(got) != len(want):
        raise VerificationError(f"{len(got)} rows in the workbook, expected {len(want)}")
    for i, (a, b) in enumerate(zip(got, want)):
        if a != b or [type(x) for x in a] != [type(x) for x in b]:
            raise VerificationError(f"row {i + 1} doesn't match the source")


def to_xlsx(src: Path, out: Path, notes: list[str]) -> None:
    if src.suffix.lower() == ".json":
        _text, data = _load_json(src, notes)
        rows = [[_json_value(v) for v in r] for r in _json_table(data)]
    else:
        rows = [[_csv_value(c) for c in r] for r in _read_table(src, notes)]
    expected = _write_xlsx(rows, out, notes, src.stem)
    _check_xlsx(out, expected)
    numbers = sum(isinstance(v, (int, float)) and not isinstance(v, bool) for r in expected for v in r)
    notes.insert(0, f"Checked: {_n(len(expected), 'row')} × {_n(max(len(r) for r in expected), 'column')}; "
                    f"{_n(numbers, 'number')}, everything else kept as text.")


# ---------------------------------------------------------------- json / csv

def _unique_headers(header: list[str]) -> list[str]:
    seen: dict[str, int] = {}
    out = []
    for i, h in enumerate(header):
        name = h.strip() or f"column {i + 1}"
        if name in seen:
            seen[name] += 1
            name = f"{name} ({seen[name]})"
        seen.setdefault(name, 1)
        out.append(name)
    return out


def to_json(src: Path, out: Path, notes: list[str]) -> None:
    rows = _read_table(src, notes)
    header = _unique_headers(rows[0])
    width = max(len(r) for r in rows)
    header += [f"column {i + 1}" for i in range(len(header), width)]
    records = []
    for r in rows[1:]:
        r = r + [""] * (len(header) - len(r))
        records.append({h: (_number(v) if _number(v) is not None else v) for h, v in zip(header, r)})
    text = json.dumps(records, ensure_ascii=False, indent=2) + "\n"
    Path(long_path(out)).write_text(text, encoding="utf-8")
    back = json.loads(Path(long_path(out)).read_text(encoding="utf-8"))
    if back != records:
        raise VerificationError("the JSON doesn't match the table")
    for rec, r in zip(back, rows[1:]):
        r = r + [""] * (len(header) - len(r))
        if [str(rec[h]) if not isinstance(rec[h], str) else rec[h] for h in header] != r:
            raise VerificationError("a value changed on the way to JSON")
    if header != rows[0]:
        notes.append("Some column names were empty or repeated, so they were renamed.")
    notes.insert(0, f"Checked: {_n(len(records), 'record')} with {_n(len(header), 'field')}.")


def to_csv(src: Path, out: Path, notes: list[str]) -> None:
    _text, data = _load_json(src, notes)
    rows = [[_json_cell_text(v) for v in r] for r in _json_table(data)]
    buf = io.StringIO(newline="")
    csv.writer(buf, lineterminator="\r\n").writerows(rows)
    Path(long_path(out)).write_bytes(buf.getvalue().encode("utf-8-sig"))  # BOM: Excel reads UTF-8 correctly
    back = list(csv.reader(io.StringIO(Path(long_path(out)).read_text(encoding="utf-8-sig"), newline="")))
    if back != rows:
        raise VerificationError("the CSV doesn't match the JSON")
    nested = any(isinstance(v, (dict, list)) for r in _json_table(data)[1:] for v in r)
    notes.append(f"Checked: {_n(len(rows) - 1, 'row')} × {_n(len(rows[0]), 'column')}.")
    if nested:
        notes.append("Nested values are kept as JSON text in their cell.")


# ---------------------------------------------------------------- tidy / minify

TOKEN_RE = re.compile(r'\s*("(?:[^"\\]|\\.)*"|[{}\[\]:,]|[^\s{}\[\]:,"]+)', re.S)


def _tokens(text: str) -> list[str]:
    tokens, pos = [], 0
    for m in TOKEN_RE.finditer(text):
        if m.start() != pos:
            raise ConversionError("This JSON couldn't be re-flowed.")
        tokens.append(m.group(1))
        pos = m.end()
    if text[pos:].strip():
        raise ConversionError("This JSON couldn't be re-flowed.")
    return tokens


def _reflow(tokens: list[str], indent: str | None) -> str:
    if indent is None:
        return "".join(tokens)
    out, depth, i = [], 0, 0
    while i < len(tokens):
        t = tokens[i]
        if t in "{[" and i + 1 < len(tokens) and tokens[i + 1] == ("}" if t == "{" else "]"):
            out.append(t + tokens[i + 1])
            i += 2
            continue
        if t in "{[":
            depth += 1
            out.append(t + "\n" + indent * depth)
        elif t in "}]":
            depth -= 1
            out.append("\n" + indent * depth + t)
        elif t == ",":
            out.append(",\n" + indent * depth)
        elif t == ":":
            out.append(": ")
        else:
            out.append(t)
        i += 1
    return "".join(out) + "\n"


def reflow(src: Path, out: Path, minify: bool, notes: list[str]) -> None:
    text, data = _load_json(src, notes)
    tokens = _tokens(text)
    result = _reflow(tokens, None if minify else "  ")
    Path(long_path(out)).write_text(result, encoding="utf-8", newline="\n")
    back = Path(long_path(out)).read_text(encoding="utf-8")
    if _tokens(back) != tokens or json.loads(back, parse_float=Decimal) != data:
        raise VerificationError("the data changed while re-flowing")
    before, after = len(text.encode("utf-8")), len(result.encode("utf-8"))
    notes.append(f"Checked: every value is identical. {before:,} → {after:,} bytes.")


def convert(sources: list[Path], out: Path, fmt: str, opts: dict) -> list[str]:
    notes: list[str] = []
    src = sources[0]
    if fmt == "xlsx":
        to_xlsx(src, out, notes)
    elif fmt == "json":
        to_json(src, out, notes)
    elif fmt == "csv":
        to_csv(src, out, notes)
    elif fmt in ("tidy", "minify"):
        reflow(src, out, fmt == "minify", notes)
    else:
        raise ConversionError(f"Unknown data conversion: {fmt}")
    return notes
