"""Settings files: INI, .env and Java .properties, as JSON or YAML.

- INI:        sections become groups: {"section": {"key": "value"}}
- .env:       KEY=value lines (quotes, "export", comments understood)
- properties: key=value or key: value (escapes and continued lines understood)

Values stay text, exactly as written (a settings file doesn't say what's a number).
The new file is read back and must hold exactly the same keys and values.
"""

from __future__ import annotations

import configparser
import json
import re
from pathlib import Path

from ..errors import ConversionError, VerificationError
from ..paths import long_path


def kind(path: Path) -> str:
    name = path.name.lower()
    if name == ".env" or name.startswith(".env.") or path.suffix.lower() == ".env":
        return "env"
    return {".ini": "ini", ".properties": "properties"}.get(path.suffix.lower(), "")


def _text(src: Path) -> str:
    raw = Path(long_path(src)).read_bytes()
    for enc in ("utf-8-sig", "utf-16"):
        try:
            if enc == "utf-16" and not raw.startswith((b"\xff\xfe", b"\xfe\xff")):
                continue
            return raw.decode(enc)
        except UnicodeDecodeError:
            pass
    return raw.decode("cp1252", errors="replace")


def read_ini(text: str) -> dict:
    cp = configparser.ConfigParser(interpolation=None, strict=False, allow_no_value=True,
                                   delimiters=("=", ":"), comment_prefixes=(";", "#"), inline_comment_prefixes=None)
    cp.optionxform = str  # keep the keys' capitals
    try:
        cp.read_string(text if re.match(r"\s*\[", text) or not text.strip() else "[DEFAULT]\n" + text)
    except configparser.Error as e:
        raise ConversionError(f"This INI file can't be read: {str(e).splitlines()[0]}") from e
    data: dict = {}
    defaults = dict(cp.defaults())
    if defaults:
        data["DEFAULT"] = defaults
    for sec in cp.sections():
        data[sec] = {k: v for k, v in cp.items(sec, raw=True) if k not in defaults or cp.get(sec, k, raw=True)
                     != defaults[k]}
    return data


_ENV = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_.-]*)\s*=\s*(.*)$")


def read_env(text: str) -> dict:
    data: dict = {}
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        i += 1
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        m = _ENV.match(line)
        if not m:
            raise ConversionError(f"Line {i} isn't KEY=value: “{line.strip()[:60]}”.")
        key, val = m.group(1), m.group(2).strip()
        if val[:1] in ("'", '"'):
            q = val[0]
            body = val[1:]
            while q not in body.replace("\\" + q, "") and i < len(lines):  # a quoted value over several lines
                body += "\n" + lines[i]
                i += 1
            end = body.rfind(q)
            if end < 0:
                raise ConversionError(f"The value of {key} has no closing quote.")
            val = body[:end]
            if q == '"':
                val = val.replace("\\n", "\n").replace('\\"', '"').replace("\\\\", "\\")
        else:
            val = re.sub(r"\s+#.*$", "", val)  # a comment after the value
        data[key] = val
    return data


def read_properties(text: str) -> dict:
    data: dict = {}
    logical: list[str] = []
    buf = ""
    for line in text.splitlines():
        s = line.lstrip() if not buf else line.lstrip()
        if not buf and (not s or s[0] in "#!"):
            continue
        trailing = len(s) - len(s.rstrip("\\"))
        if trailing % 2 == 1:  # an odd number of backslashes: the line continues
            buf += s[:-1]
            continue
        logical.append(buf + s)
        buf = ""
    if buf:
        logical.append(buf)
    for line in logical:
        m = re.match(r"((?:\\.|[^=:\s\\])+)\s*[=:\s]\s*(.*)$", line, re.S) or re.match(r"((?:\\.|[^=:\s\\])+)$", line)
        if not m:
            continue
        key = _unescape(m.group(1))
        data[key] = _unescape(m.group(2) if m.lastindex and m.lastindex >= 2 else "")
    return data


def _unescape(s: str) -> str:
    def rep(m):
        c = m.group(1)
        if c.startswith("u"):
            return chr(int(c[1:], 16))
        return {"t": "\t", "n": "\n", "r": "\r", "f": "\f"}.get(c, c)

    return re.sub(r"\\(u[0-9a-fA-F]{4}|.)", rep, s)


READERS = {"ini": read_ini, "env": read_env, "properties": read_properties}


def convert(sources: list[Path], out: Path, fmt: str, opts: dict) -> list[str]:
    src = sources[0]
    k = kind(src)
    if k not in READERS:
        raise ConversionError("This isn't an INI, .env or .properties file.")
    data = READERS[k](_text(src))
    if not data:
        raise ConversionError("There are no settings in this file.")
    if fmt == "json":
        Path(long_path(out)).write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        back = json.loads(Path(long_path(out)).read_text(encoding="utf-8"))
    elif fmt == "yaml":
        import yaml

        Path(long_path(out)).write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False,
                                                       default_flow_style=False), encoding="utf-8")
        back = yaml.safe_load(Path(long_path(out)).read_text(encoding="utf-8"))
    else:
        raise ConversionError(f"Unknown settings conversion: {fmt}")
    if back != data:
        raise VerificationError("the settings changed on the way")
    n = sum(len(v) if isinstance(v, dict) else 1 for v in data.values())
    groups = sum(isinstance(v, dict) for v in data.values())
    what = f"{n} setting{'s' if n != 1 else ''}" + (f" in {groups} section{'s' if groups != 1 else ''}" if groups else "")
    notes = [f"Checked: {what}, every key and value exactly as written (as text)."]
    if k == "env" and fmt in ("json", "yaml"):
        notes.append("This file may hold passwords or keys: the new file holds them too.")
    return notes
