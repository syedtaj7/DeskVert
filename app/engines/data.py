"""Data files: CSV / TSV / JSON / Excel.

- xlsx:   CSV/TSV/JSON -> Excel workbook. A value becomes a number only when
          Excel would show exactly the same text (so 007, 1.50, +44 and long
          IDs stay as written). Text starting with = is never run as a formula.
- json:   CSV/TSV -> a list of records (first row = field names)
- csv:    JSON (a list of records, or a list of lists) -> CSV (UTF-8, opens in Excel)
- tidy / minify: JSON re-flowed. Every value is copied character for character,
          so numbers like 1.10 or 0.1000000000000000055 keep their exact text.
- YAML, TOML, XML and JSON Lines: -> JSON (and from there to CSV / Excel);
  JSON / TOML / XML / JSON Lines -> YAML; a JSON list -> JSON Lines.
  XML becomes {"tag": {"@attribute": ..., "#text": ..., "child": ...}}.
- toml / xml: any of the above (and CSV / TSV / Excel tables, as records) -> TOML or XML.
- tsv / csv: CSV <-> TSV.
- Excel workbooks (read without Excel): the first sheet as records, or every
  sheet as its own CSV ("sheets").
- vCard contacts (.vcf, also old phones' quoted-printable) <-> CSV / Excel.

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


STRUCTURED = {".yaml", ".yml", ".toml", ".xml", ".jsonl", ".ndjson"}


def _plain_data(v):
    """Values every format can hold: dates become ISO text, Decimals stay exact."""
    import datetime

    if isinstance(v, dict):
        return {str(k): _plain_data(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_plain_data(x) for x in v]
    if isinstance(v, (datetime.date, datetime.time, datetime.datetime)):
        return v.isoformat()
    if isinstance(v, float) and (v != v or v in (float("inf"), float("-inf"))):
        return str(v)  # JSON has no NaN or infinity
    return v


def _xml_value(el):
    local = el.tag.rsplit("}", 1)[-1] if isinstance(el.tag, str) else str(el.tag)
    d: dict = {}
    for k, v in el.attrib.items():
        d["@" + k.rsplit("}", 1)[-1]] = v
    for child in el:
        if not isinstance(child.tag, str):
            continue  # comments, processing instructions
        name, value = _xml_value(child)
        if name in d:
            if not isinstance(d[name], list) or not getattr(d[name], "_many", False):
                d[name] = _Many([d[name]])
            d[name].append(value)
        else:
            d[name] = value
    text = (el.text or "").strip()
    if not d:
        return local, text if text else None
    if text:
        d["#text"] = text
    return local, {k: (list(v) if isinstance(v, _Many) else v) for k, v in d.items()}


class _Many(list):
    _many = True


def _load_structured(src: Path, notes: list[str]):
    """(source text, data) for JSON and the other structured formats."""
    ext = src.suffix.lower()
    if ext == ".json":
        return _load_json(src, notes)
    text = _read_text(src, notes)
    try:
        if ext in (".yaml", ".yml"):
            import yaml

            docs = list(yaml.safe_load_all(text))
            data = docs[0] if len(docs) == 1 else docs
            if len(docs) > 1:
                notes.append(f"The file holds {len(docs)} YAML documents; they became a list.")
        elif ext == ".toml":
            import tomllib

            data = tomllib.loads(text)
        elif ext == ".xml":
            import xml.etree.ElementTree as ET

            root = ET.fromstring(text.encode("utf-8"))
            name, value = _xml_value(root)
            data = {name: value}
        else:  # JSON Lines: one JSON value per line
            data = [json.loads(line, parse_float=Decimal) for line in text.splitlines() if line.strip()]
    except ConversionError:
        raise
    except Exception as e:  # noqa: BLE001 - parser errors differ per format
        raise ConversionError(f"This file couldn't be read as {ext[1:].upper()} ({e}).") from e
    if data is None:
        raise ConversionError("The file is empty.")
    return text, _plain_data(data)


def _dumps(data, indent: int | None = 2) -> str:
    """JSON text where exact numbers (Decimal) are written with their original digits, e.g. 2.50."""
    exact: list[str] = []

    def mark(v):
        if isinstance(v, dict):
            return {k: mark(x) for k, x in v.items()}
        if isinstance(v, list):
            return [mark(x) for x in v]
        if isinstance(v, Decimal):
            exact.append(str(v))
            return f"\x00{len(exact) - 1}\x00"
        return v

    text = json.dumps(mark(data), ensure_ascii=False, indent=indent, default=str)
    return re.sub(r'"\\u0000(\d+)\\u0000"', lambda m: exact[int(m.group(1))], text)


def _json_text(data) -> str:
    return _dumps(data) + "\n"


def _norm(v):
    """For comparing: numbers by value (1.10 == 1.1), everything else as is."""
    if isinstance(v, dict):
        return {str(k): _norm(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_norm(x) for x in v]
    if isinstance(v, bool) or v is None or isinstance(v, str):
        return v
    if isinstance(v, (int, float, Decimal)):
        return Decimal(str(v))
    return str(v)


def _same(a, b) -> bool:
    return _norm(a) == _norm(b)


def structured_to_json(src: Path, out: Path, notes: list[str]) -> None:
    data = _load_any(src, notes)
    Path(long_path(out)).write_text(_json_text(data), encoding="utf-8", newline="\n")
    back = json.loads(Path(long_path(out)).read_text(encoding="utf-8"), parse_float=Decimal)
    if not _same(back, data):
        raise VerificationError("the JSON doesn't match the file")
    notes.append("Checked: every value is in the JSON.")


def _yaml_dump(data) -> str:
    import yaml

    class Dumper(yaml.SafeDumper):
        pass

    Dumper.add_representer(Decimal, lambda d, v: d.represent_scalar("tag:yaml.org,2002:float", str(v)))
    return yaml.dump(data, Dumper=Dumper, allow_unicode=True, sort_keys=False, default_flow_style=False, width=100)


def to_yaml(src: Path, out: Path, notes: list[str]) -> None:
    import yaml

    data = _load_any(src, notes)
    Path(long_path(out)).write_text(_yaml_dump(data), encoding="utf-8", newline="\n")
    back = _plain_data(yaml.safe_load(Path(long_path(out)).read_text(encoding="utf-8")))
    if not _same(back, data):
        raise VerificationError("the YAML doesn't match the file")
    notes.append("Checked: every value is in the YAML.")


def to_jsonl(src: Path, out: Path, notes: list[str]) -> None:
    data = _load_any(src, notes)
    if isinstance(data, dict):
        lists = [v for v in data.values() if isinstance(v, list)]
        data = lists[0] if len(lists) == 1 else None
    if not isinstance(data, list):
        raise ConversionError("JSON Lines needs a list (like a list of records).")
    lines = [_dumps(item, indent=None) for item in data]
    Path(long_path(out)).write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    back = [json.loads(x, parse_float=Decimal) for x in Path(long_path(out)).read_text(encoding="utf-8").splitlines()
            if x.strip()]
    if not _same(back, data):
        raise VerificationError("the JSON Lines don't match the file")
    notes.append(f"Checked: {_n(len(lines), 'line')}, one record per line.")


TABLE_EXTS = {".csv", ".tsv", ".xlsx", ".xlsm"}


def _xlsx_rows(src: Path, sheet: int = 0) -> list[list]:
    from openpyxl import load_workbook

    wb = load_workbook(long_path(src), read_only=True, data_only=True)
    try:
        ws = wb.worksheets[sheet]
        rows = [list(r) for r in ws.iter_rows(values_only=True)]
    finally:
        wb.close()
    while rows and not any(v not in (None, "") for v in rows[-1]):
        rows.pop()
    if not rows:
        raise ConversionError("The sheet is empty.")
    return rows


def _records(src: Path, notes: list[str]) -> list[dict]:
    """A table (CSV, TSV or the first sheet of a workbook) as records; the first row names the fields."""
    if src.suffix.lower() in (".xlsx", ".xlsm"):
        rows = [["" if v is None else v for v in r] for r in _xlsx_rows(src)]
        header = _unique_headers([str(h) for h in rows[0]])
        width = max(len(r) for r in rows)
        header += [f"column {i + 1}" for i in range(len(header), width)]
        out = []
        for r in rows[1:]:
            r = list(r) + [""] * (len(header) - len(r))
            out.append({h: (Decimal(repr(v)) if isinstance(v, float) else
                            v.isoformat() if hasattr(v, "isoformat") else v) for h, v in zip(header, r)})
        return out
    rows = _read_table(src, notes)
    header = _unique_headers(rows[0])
    width = max(len(r) for r in rows)
    header += [f"column {i + 1}" for i in range(len(header), width)]
    out = []
    for r in rows[1:]:
        r = r + [""] * (len(header) - len(r))
        out.append({h: (_number(v) if _number(v) is not None else v) for h, v in zip(header, r)})
    return out


def _load_any(src: Path, notes: list[str]):
    """Data from any supported file: structured formats as they are, tables as records."""
    if src.suffix.lower() in TABLE_EXTS:
        return _records(src, notes)
    return _load_structured(src, notes)[1]


# ---------------------------------------------------------------- TOML

_BARE = re.compile(r"[A-Za-z0-9_-]+")


def _toml_key(k) -> str:
    k = str(k)
    return k if _BARE.fullmatch(k) else json.dumps(k, ensure_ascii=False)


def _toml_value(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, (float, Decimal)):
        s = str(v)
        if isinstance(v, float) and s in ("inf", "-inf", "nan"):
            return s
        return s if any(c in s for c in ".eE") or s in ("inf", "-inf", "nan") else s + ".0"
    if isinstance(v, str):
        return json.dumps(v, ensure_ascii=False)
    if isinstance(v, list):
        return "[" + ", ".join(_toml_value(x) for x in v) + "]"
    if isinstance(v, dict):
        return "{" + ", ".join(f"{_toml_key(k)} = {_toml_value(x)}" for k, x in v.items()) + "}"
    return json.dumps(str(v), ensure_ascii=False)


def _drop_none(v):
    if isinstance(v, dict):
        return {k: _drop_none(x) for k, x in v.items() if x is not None}
    if isinstance(v, list):
        return [_drop_none(x) for x in v if x is not None]
    return v


def _toml_dump(d: dict, path: list[str] | None = None) -> list[str]:
    path = path or []
    lines, tables = [], []
    for k, v in d.items():
        if isinstance(v, dict) and v:
            tables.append(("table", k, v))
        elif isinstance(v, list) and v and all(isinstance(x, dict) for x in v):
            tables.append(("array", k, v))
        else:
            lines.append(f"{_toml_key(k)} = {_toml_value(v)}")
    for kind, k, v in tables:
        p = path + [_toml_key(k)]
        if kind == "table":
            lines += ["", f"[{'.'.join(p)}]"] + _toml_dump(v, p)
        else:
            for item in v:
                lines += ["", f"[[{'.'.join(p)}]]"] + _toml_dump(item, p)
    return lines


def to_toml(src: Path, out: Path, notes: list[str]) -> None:
    import tomllib

    data = _load_any(src, notes)
    if not isinstance(data, dict):
        data = {"items": data}
        notes.append("TOML needs named values at the top, so the list is under \"items\".")
    clean = _drop_none(data)
    if _norm(clean) != _norm(data):
        notes.append("TOML has no empty (null) values; those were left out.")
    text = "\n".join(_toml_dump(clean)).lstrip("\n") + "\n"
    Path(long_path(out)).write_text(text, encoding="utf-8", newline="\n")
    try:
        back = tomllib.loads(Path(long_path(out)).read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        raise VerificationError(f"the TOML can't be read back ({e})") from e
    if not _same(_plain_data(back), clean):
        raise VerificationError("the TOML doesn't match the file")
    notes.insert(0, "Checked: every value is in the TOML.")


# ---------------------------------------------------------------- XML

_XML_NAME = re.compile(r"[A-Za-z_][\w.-]*")


def _xml_name(k: str) -> str:
    k = str(k)
    if k.startswith(("@", "#")):
        return k
    s = re.sub(r"[^\w.-]", "_", k)
    return s if _XML_NAME.fullmatch(s) else "_" + s


def _xmlable(v):
    """The data in the shape XML can hold: safe names, lists inside lists wrapped as items."""
    if isinstance(v, dict):
        return {_xml_name(k): _xmlable(x) for k, x in v.items()}
    if isinstance(v, list):
        return [{"item": _xmlable(x)} if isinstance(x, list) else _xmlable(x) for x in v]
    return v


def _xml_norm(v):
    if isinstance(v, dict):
        out = {}
        for k, x in v.items():
            if isinstance(x, list) and not x:
                continue
            out[k] = _xml_norm(x)
        return out or None
    if isinstance(v, list):
        items = [_xml_norm(x) for x in v]
        return items[0] if len(items) == 1 else items
    if v is None or v == "":
        return None
    if isinstance(v, bool):
        return "true" if v else "false"
    return str(v)


def _xml_text(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    return "" if v is None else str(v)


def _xml_write(name: str, v, out: list[str], depth: int) -> None:
    from xml.sax.saxutils import escape, quoteattr

    pad = "  " * depth
    if isinstance(v, list):
        for x in v:
            _xml_write(name, x, out, depth)
        return
    if isinstance(v, dict):
        attrs = "".join(f" {k[1:]}={quoteattr(_xml_text(x))}" for k, x in v.items() if k.startswith("@"))
        kids = [(k, x) for k, x in v.items() if not k.startswith(("@", "#"))]
        text = v.get("#text")
        if not kids:
            out.append(f"{pad}<{name}{attrs}>{escape(_xml_text(text))}</{name}>" if text not in (None, "")
                       else f"{pad}<{name}{attrs}/>")
            return
        out.append(f"{pad}<{name}{attrs}>" + (escape(_xml_text(text)) if text not in (None, "") else ""))
        for k, x in kids:
            _xml_write(k, x, out, depth + 1)
        out.append(f"{pad}</{name}>")
        return
    if v is None or v == "":
        out.append(f"{pad}<{name}/>")
    else:
        out.append(f"{pad}<{name}>{escape(_xml_text(v))}</{name}>")


def to_xml(src: Path, out: Path, notes: list[str]) -> None:
    data = _load_any(src, notes)
    if isinstance(data, dict) and len(data) == 1 and not next(iter(data)).startswith(("@", "#")) \
            and not isinstance(next(iter(data.values())), list):
        root = _xmlable(data)
    else:
        root = _xmlable({"data": data if isinstance(data, dict) else {"item": data}})
    (name, value), = root.items()
    lines = ['<?xml version="1.0" encoding="UTF-8"?>']
    _xml_write(name, value, lines, 0)
    Path(long_path(out)).write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    _text, back = _load_structured(out, notes)
    if _xml_norm(back) != _xml_norm(root):
        raise VerificationError("the XML doesn't match the file")
    notes.insert(0, "Checked: every value is in the XML (XML stores everything as text).")


# ---------------------------------------------------------------- CSV <-> TSV, workbook sheets

def table_to(src: Path, out: Path, delimiter: str, notes: list[str]) -> None:
    rows = _read_table(src, notes)
    buf = io.StringIO(newline="")
    csv.writer(buf, delimiter=delimiter, lineterminator="\r\n").writerows(rows)
    data = buf.getvalue()
    Path(long_path(out)).write_bytes(data.encode("utf-8-sig" if delimiter == "," else "utf-8"))
    back = list(csv.reader(io.StringIO(Path(long_path(out)).read_text(encoding="utf-8-sig"), newline=""),
                           delimiter=delimiter))
    if back != rows:
        raise VerificationError("the table changed")
    notes.append(f"Checked: {_n(len(rows), 'row')}, every cell the same.")


def sheets_to_csv(src: Path, out_dir: Path, notes: list[str]) -> None:
    from openpyxl import load_workbook

    out_dir.mkdir(parents=True, exist_ok=True)
    wb = load_workbook(long_path(src), read_only=True, data_only=True)
    try:
        names = [ws.title for ws in wb.worksheets]
    finally:
        wb.close()
    written = 0
    used: set[str] = set()
    for i, name in enumerate(names):
        try:
            rows = _xlsx_rows(src, i)
        except ConversionError:
            continue  # empty sheet
        text_rows = [["" if v is None else (v.isoformat() if hasattr(v, "isoformat") else
                                            repr(v) if isinstance(v, float) else str(v)) for v in r] for r in rows]
        safe = re.sub(r'[\\/:*?"<>|]', "_", name).strip() or f"Sheet{i + 1}"
        while safe.lower() in used:
            safe += "_"
        used.add(safe.lower())
        buf = io.StringIO(newline="")
        csv.writer(buf, lineterminator="\r\n").writerows(text_rows)
        f = out_dir / f"{safe}.csv"
        Path(long_path(f)).write_bytes(buf.getvalue().encode("utf-8-sig"))
        back = list(csv.reader(io.StringIO(Path(long_path(f)).read_text(encoding="utf-8-sig"), newline="")))
        if back != text_rows:
            raise VerificationError(f"sheet {name} changed")
        written += 1
    if not written:
        raise ConversionError("Every sheet in this workbook is empty.")
    notes.append(f"Checked: {written} sheet{'s' if written != 1 else ''}, one CSV each (values as Excel last "
                 "calculated them).")


# ---------------------------------------------------------------- vCard contacts

VCARD_FIELDS = ["Name", "First name", "Last name", "Phone", "Phone 2", "Phone 3", "Email", "Email 2",
                "Organization", "Title", "Address", "Birthday", "Website", "Note"]


def _vcard_value(params: list[str], value: str) -> str:
    import quopri

    up = [p.upper() for p in params]
    charset = next((p.split("=", 1)[1] for p in params if p.upper().startswith("CHARSET=")), "utf-8")
    if "ENCODING=QUOTED-PRINTABLE" in up or "QUOTED-PRINTABLE" in up:
        try:
            return quopri.decodestring(value.encode("latin-1")).decode(charset, errors="replace")
        except LookupError:
            return quopri.decodestring(value.encode("latin-1")).decode("utf-8", errors="replace")
    if "ENCODING=B" in up or "ENCODING=BASE64" in up:
        return ""  # photos
    return value.replace("\\n", "\n").replace("\\N", "\n").replace("\\,", ",").replace("\\;", ";").replace("\\\\", "\\")


def read_vcards(text: str) -> list[dict]:
    text = text.replace("\r\n", "\n")
    text = re.sub(r"=\n", "", text)  # quoted-printable soft line breaks
    lines = []
    for line in text.split("\n"):
        if line[:1] in (" ", "\t") and lines:
            lines[-1] += line[1:]
        else:
            lines.append(line)
    cards, cur = [], None
    for line in lines:
        if line.upper().startswith("BEGIN:VCARD"):
            cur = {"Phone": [], "Email": []}
        elif line.upper().startswith("END:VCARD"):
            if cur is not None:
                cards.append(cur)
            cur = None
        elif cur is not None and ":" in line:
            head, value = line.split(":", 1)
            name, *params = head.split(";")
            name = name.split(".")[-1].upper()
            v = _vcard_value(params, value)
            if name == "FN":
                cur["Name"] = v
            elif name == "N":
                parts = (v.split(";") + [""] * 5)[:5]
                cur["Last name"], cur["First name"] = parts[0], parts[1]
            elif name == "TEL":
                cur["Phone"].append(v.strip())
            elif name == "EMAIL":
                cur["Email"].append(v.strip())
            elif name == "ORG":
                cur["Organization"] = v.replace(";", ", ").strip(", ")
            elif name == "TITLE":
                cur["Title"] = v
            elif name == "ADR":
                cur["Address"] = ", ".join(x.strip() for x in v.split(";") if x.strip())
            elif name == "BDAY":
                cur["Birthday"] = v
            elif name == "URL":
                cur["Website"] = v
            elif name == "NOTE":
                cur["Note"] = v
    for c in cards:
        if not c.get("Name"):
            c["Name"] = " ".join(x for x in (c.get("First name"), c.get("Last name")) if x).strip()
    if not cards:
        raise ConversionError("No contacts were found in this file.")
    return cards


def vcard_rows(cards: list[dict]) -> list[list[str]]:
    n_phone = max(1, max(len(c["Phone"]) for c in cards))
    n_mail = max(1, max(len(c["Email"]) for c in cards))
    header = ["Name", "First name", "Last name"] + [f"Phone {i + 1}" if i else "Phone" for i in range(n_phone)] + \
             [f"Email {i + 1}" if i else "Email" for i in range(n_mail)] + \
             ["Organization", "Title", "Address", "Birthday", "Website", "Note"]
    rows = [header]
    for c in cards:
        rows.append([c.get("Name", ""), c.get("First name", ""), c.get("Last name", "")] +
                    (c["Phone"] + [""] * n_phone)[:n_phone] + (c["Email"] + [""] * n_mail)[:n_mail] +
                    [c.get(k, "") for k in ("Organization", "Title", "Address", "Birthday", "Website", "Note")])
    return rows


def _vesc(s: str) -> str:
    return s.replace("\\", "\\\\").replace("\n", "\\n").replace(",", "\\,").replace(";", "\\;")


def write_vcards(rows: list[list[str]]) -> tuple[str, int]:
    header = [h.strip().lower() for h in rows[0]]

    def cols(*names):
        return [i for i, h in enumerate(header) if any(h == n or h.startswith(n + " ") for n in names)]

    name_c = cols("name", "full name", "display name", "contact")
    first_c, last_c = cols("first name", "given name", "first"), cols("last name", "family name", "surname", "last")
    phone_c = cols("phone", "mobile", "tel", "telephone", "phone number", "cell")
    mail_c = cols("email", "e-mail", "mail")
    org_c, title_c = cols("organization", "company", "org"), cols("title", "job title")
    adr_c, bday_c = cols("address"), cols("birthday", "bday", "date of birth")
    url_c, note_c = cols("website", "url", "web"), cols("note", "notes")
    if not (name_c or first_c or last_c or phone_c or mail_c):
        raise ConversionError("This CSV has no name, phone or email columns to make contacts from.")
    out, n = [], 0
    for r in rows[1:]:
        r = r + [""] * (len(header) - len(r))

        def first(cs):
            return next((r[i].strip() for i in cs if r[i].strip()), "")
        fn, ln = first(first_c), first(last_c)
        full = first(name_c) or " ".join(x for x in (fn, ln) if x)
        phones = [r[i].strip() for i in phone_c if r[i].strip()]
        mails = [r[i].strip() for i in mail_c if r[i].strip()]
        if not (full or phones or mails):
            continue
        card = ["BEGIN:VCARD", "VERSION:3.0", f"FN:{_vesc(full)}", f"N:{_vesc(ln)};{_vesc(fn)};;;"]
        card += [f"TEL;TYPE=CELL:{_vesc(p)}" for p in phones] + [f"EMAIL;TYPE=INTERNET:{_vesc(m)}" for m in mails]
        for cs, tag in ((org_c, "ORG"), (title_c, "TITLE"), (adr_c, "ADR;TYPE=HOME:;;"), (bday_c, "BDAY"),
                        (url_c, "URL"), (note_c, "NOTE")):
            v = first(cs)
            if v:
                card.append(f"{tag}{'' if tag.endswith(':;;') else ':'}{_vesc(v)}")
        card.append("END:VCARD")
        out.append("\r\n".join(card))
        n += 1
    if not n:
        raise ConversionError("No rows with a name, phone or email were found.")
    return "\r\n".join(out) + "\r\n", n


def vcard_to_table(src: Path, out: Path, fmt: str, notes: list[str]) -> None:
    cards = read_vcards(_read_text(src, notes))
    rows = vcard_rows(cards)
    if fmt == "xlsx":
        expected = _write_xlsx([[v if v != "" else None for v in r] for r in rows], out, notes, "Contacts")
        _check_xlsx(out, expected)
    else:
        buf = io.StringIO(newline="")
        csv.writer(buf, lineterminator="\r\n").writerows(rows)
        Path(long_path(out)).write_bytes(buf.getvalue().encode("utf-8-sig"))
        back = list(csv.reader(io.StringIO(Path(long_path(out)).read_text(encoding="utf-8-sig"), newline="")))
        if back != rows:
            raise VerificationError("the contacts table doesn't match")
    notes.insert(0, f"Checked: {_n(len(cards), 'contact')}, names, phones and emails included.")


def table_to_vcard(src: Path, out: Path, notes: list[str]) -> None:
    rows = _read_table(src, notes) if src.suffix.lower() in (".csv", ".tsv") else \
        [["" if v is None else str(v) for v in r] for r in _xlsx_rows(src)]
    text, n = write_vcards(rows)
    Path(long_path(out)).write_text(text, encoding="utf-8", newline="")
    back = read_vcards(Path(long_path(out)).read_text(encoding="utf-8"))
    if len(back) != n:
        raise VerificationError("contacts are missing")
    notes.append(f"Checked: {_n(n, 'contact')} (vCard 3.0, opens in phones, Outlook and Google Contacts).")


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
    if src.suffix.lower() == ".json" or src.suffix.lower() in STRUCTURED:
        _text, data = _load_structured(src, notes)
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
    _text, data = _load_structured(src, notes)
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
        if src.suffix.lower() in STRUCTURED or src.suffix.lower() in (".xlsx", ".xlsm"):
            structured_to_json(src, out, notes)
        else:
            to_json(src, out, notes)
    elif fmt == "yaml":
        to_yaml(src, out, notes)
    elif fmt == "toml":
        to_toml(src, out, notes)
    elif fmt == "xml":
        to_xml(src, out, notes)
    elif fmt == "tsv":
        table_to(src, out, "\t", notes)
    elif fmt == "csv" and src.suffix.lower() == ".tsv":
        table_to(src, out, ",", notes)
    elif fmt == "sheets":
        sheets_to_csv(src, out, notes)
    elif fmt in ("vcsv", "vxlsx"):
        vcard_to_table(src, out, fmt[1:], notes)
    elif fmt == "vcf":
        table_to_vcard(src, out, notes)
    elif fmt == "jsonl":
        to_jsonl(src, out, notes)
    elif fmt == "csv":
        to_csv(src, out, notes)
    elif fmt in ("tidy", "minify"):
        reflow(src, out, fmt == "minify", notes)
    else:
        raise ConversionError(f"Unknown data conversion: {fmt}")
    return notes
