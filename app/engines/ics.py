"""Calendar files (.ics, from Google Calendar, Outlook, Apple Calendar...) as a table.

One row per event: title, start, end, all day, time zone, location, description,
organizer, repeats. Times are written as they are in the file (no time-zone
conversion), like 2026-11-11 09:30. The table is read back and compared.
"""

from __future__ import annotations

import csv
import re
from pathlib import Path

from ..errors import ConversionError, VerificationError
from ..paths import long_path

COLUMNS = ["Title", "Start", "End", "All day", "Time zone", "Location", "Description", "Organizer", "Repeats"]


def _unfold(text: str) -> list[str]:
    out: list[str] = []
    for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if line[:1] in (" ", "\t") and out:
            out[-1] += line[1:]
        else:
            out.append(line)
    return out


def _unescape(v: str) -> str:
    return re.sub(r"\\([nN,;\\])", lambda m: "\n" if m.group(1) in "nN" else m.group(1), v)


def _when(value: str, params: dict) -> tuple[str, bool, str]:
    """(readable time, all day, time zone)."""
    tz = params.get("TZID", "")
    v = value.strip()
    if params.get("VALUE", "").upper() == "DATE" or re.fullmatch(r"\d{8}", v):
        return f"{v[:4]}-{v[4:6]}-{v[6:8]}", True, tz
    m = re.fullmatch(r"(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})(\d{2})?(Z?)", v)
    if not m:
        return v, False, tz
    y, mo, d, h, mi, s, z = m.groups()
    text = f"{y}-{mo}-{d} {h}:{mi}" + (f":{s}" if s and s != "00" else "")
    return text, False, "UTC" if z else tz


def read_events(text: str) -> list[dict]:
    lines = _unfold(text)
    if not any(line.strip().upper() == "BEGIN:VCALENDAR" for line in lines[:5]):
        raise ConversionError("This isn't a calendar file (.ics).")
    events: list[dict] = []
    cur: dict | None = None
    depth = 0  # alarms and other parts inside an event
    for line in lines:
        if ":" not in line:
            continue
        head, value = line.split(":", 1)
        name, *rest = head.split(";")
        name = name.upper()
        params = {}
        for p in rest:
            if "=" in p:
                k, v = p.split("=", 1)
                params[k.upper()] = v.strip('"')
        if name == "BEGIN":
            if value.strip().upper() == "VEVENT":
                cur, depth = {c: "" for c in COLUMNS}, 0
            elif cur is not None:
                depth += 1
            continue
        if name == "END":
            if value.strip().upper() == "VEVENT" and cur is not None:
                events.append(cur)
                cur = None
            elif cur is not None:
                depth -= 1
            continue
        if cur is None or depth:
            continue
        if name == "SUMMARY":
            cur["Title"] = _unescape(value)
        elif name in ("DTSTART", "DTEND"):
            when, all_day, tz = _when(value, params)
            cur["Start" if name == "DTSTART" else "End"] = when
            if name == "DTSTART":
                cur["All day"] = "yes" if all_day else "no"
                cur["Time zone"] = tz
        elif name == "LOCATION":
            cur["Location"] = _unescape(value)
        elif name == "DESCRIPTION":
            cur["Description"] = _unescape(value)
        elif name == "ORGANIZER":
            cur["Organizer"] = params.get("CN") or re.sub(r"^mailto:", "", value, flags=re.I)
        elif name == "RRULE":
            m = re.search(r"FREQ=(\w+)", value)
            cur["Repeats"] = {"DAILY": "daily", "WEEKLY": "weekly", "MONTHLY": "monthly",
                              "YEARLY": "yearly"}.get(m.group(1).upper(), m.group(1).lower()) if m else "yes"
    if not events:
        raise ConversionError("There are no events in this calendar.")
    events.sort(key=lambda e: e["Start"])
    return events


def _read(src: Path) -> str:
    raw = Path(long_path(src)).read_bytes()
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return raw.decode("cp1252", errors="replace")


def convert(sources: list[Path], out: Path, fmt: str, opts: dict) -> list[str]:
    events = read_events(_read(sources[0]))
    rows = [[re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", e[c]) for c in COLUMNS] for e in events]
    if fmt == "csv":
        with open(long_path(out), "w", encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f)
            w.writerow(COLUMNS)
            w.writerows(rows)
        with open(long_path(out), encoding="utf-8-sig", newline="") as f:
            back = list(csv.reader(f))
        if back != [COLUMNS] + rows:
            raise VerificationError("the table doesn't match the calendar")
    elif fmt == "xlsx":
        from openpyxl import Workbook, load_workbook
        from openpyxl.cell import WriteOnlyCell
        from openpyxl.styles import Font

        wb = Workbook(write_only=True)
        ws = wb.create_sheet("Events")
        ws.freeze_panes = "A2"
        for i, width in enumerate((34, 18, 18, 8, 16, 26, 50, 22, 10)):
            ws.column_dimensions[chr(65 + i)].width = width
        bold = Font(bold=True)
        head = []
        for c in COLUMNS:
            cell = WriteOnlyCell(ws, value=c)
            cell.font = bold
            head.append(cell)
        ws.append(head)
        for r in rows:
            cells = []
            for v in r:
                cell = WriteOnlyCell(ws, value=v or None)
                cell.data_type = "s"
                cells.append(cell)
            ws.append(cells)
        wb.save(long_path(out))
        back_wb = load_workbook(long_path(out), read_only=True)
        try:
            back = [[v or "" for v in r] for r in back_wb.worksheets[0].iter_rows(values_only=True)]
        finally:
            back_wb.close()
        back = [r + [""] * (len(COLUMNS) - len(r)) for r in back]
        if back != [COLUMNS] + rows:
            raise VerificationError("the table doesn't match the calendar")
    else:
        raise ConversionError(f"Unknown calendar conversion: {fmt}")
    repeating = sum(1 for e in events if e["Repeats"])
    notes = [f"Checked: {len(events)} event{'s' if len(events) != 1 else ''}, one row each, sorted by start. "
             "Times are as written in the file."]
    if repeating:
        notes.append(f"{repeating} repeating event{'s' if repeating != 1 else ''} appear once, with how often "
                     "they repeat.")
    return notes
