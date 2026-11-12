"""Jupyter notebooks (.ipynb) as a web page, Markdown or a Python script.

- html: the notes, the code and its results (text and pictures) in one page that
        opens in any browser, no Jupyter needed
- md:   notes as they are, code in fenced blocks, text results below each
- py:   the code, with the notes as comments ("# %%" cells, as editors expect)

The notebook is only read, never run. Every note and every line of code must be
in the new file.
"""

from __future__ import annotations

import base64
import html
import json
from pathlib import Path

from ..errors import ConversionError, VerificationError
from ..paths import long_path
from .officeutil import text_coverage, words


def _src(cell) -> str:
    s = cell.get("source", "")
    return "".join(s) if isinstance(s, list) else str(s)


def _text_outputs(cell) -> list[str]:
    out = []
    for o in cell.get("outputs", []) or []:
        kind = o.get("output_type")
        if kind == "stream":
            t = o.get("text", "")
            out.append("".join(t) if isinstance(t, list) else str(t))
        elif kind in ("execute_result", "display_data"):
            t = (o.get("data") or {}).get("text/plain")
            if t and not any(k.startswith("image/") for k in (o.get("data") or {})):
                out.append("".join(t) if isinstance(t, list) else str(t))
        elif kind == "error":
            out.append(f"{o.get('ename', 'Error')}: {o.get('evalue', '')}")
    return [t.rstrip("\n") for t in out if t.strip()]


def _images(cell) -> list[tuple[str, str]]:
    found = []
    for o in cell.get("outputs", []) or []:
        data = o.get("data") or {}
        for mime in ("image/png", "image/jpeg"):
            if mime in data:
                b64 = data[mime]
                found.append((mime, "".join(b64) if isinstance(b64, list) else str(b64)))
    return found


def read(src: Path) -> tuple[list[dict], str]:
    try:
        nb = json.loads(Path(long_path(src)).read_text(encoding="utf-8-sig"))
    except (ValueError, UnicodeDecodeError) as e:
        raise ConversionError("This notebook is damaged (it isn't valid JSON).") from e
    cells = nb.get("cells")
    if cells is None and nb.get("worksheets"):  # notebooks from 2014 and before
        cells = [c for ws in nb["worksheets"] for c in ws.get("cells", [])]
        for c in cells:
            if c.get("cell_type") == "code" and "input" in c:
                c["source"] = c["input"]
    if not cells:
        raise ConversionError("This notebook has no cells.")
    lang = ((nb.get("metadata") or {}).get("kernelspec") or {}).get("language") or \
        ((nb.get("metadata") or {}).get("language_info") or {}).get("name") or "python"
    return [c for c in cells if c.get("cell_type") in ("markdown", "code", "raw")], lang


def to_markdown(cells: list[dict], lang: str) -> tuple[str, int]:
    out, pictures = [], 0
    for c in cells:
        s = _src(c).rstrip()
        if c["cell_type"] == "code":
            if s:
                out.append(f"```{lang}\n{s}\n```")
            for t in _text_outputs(c):
                out.append(f"```text\n{t}\n```")
            pictures += len(_images(c))
        elif s:
            out.append(s)
    return "\n\n".join(out) + "\n", pictures


def to_python(cells: list[dict]) -> str:
    out = []
    for c in cells:
        s = _src(c).rstrip()
        if not s:
            continue
        if c["cell_type"] == "code":
            out.append("# %%\n" + s)
        else:
            out.append("# %% [markdown]\n" + "\n".join("# " + line if line else "#" for line in s.splitlines()))
    return "\n\n".join(out) + "\n"


def _md_html(text: str) -> str:
    from PySide6.QtGui import QTextDocument

    from .textdoc import _app

    _app()
    doc = QTextDocument()
    doc.setMarkdown(text, QTextDocument.MarkdownFeature.MarkdownDialectGitHub)
    body = doc.toHtml()
    start, end = body.find("<body"), body.rfind("</body>")
    if start < 0 or end < 0:
        return html.escape(text)
    return body[body.find(">", start) + 1:end]


def to_html(cells: list[dict], title: str) -> str:
    from .textdoc import PAGE_CSS

    css = PAGE_CSS + ("pre{padding:10px;border-radius:6px;overflow:auto}.out{background:#fff;border-left:3px solid "
                      "#ddd}.cell{margin:18px 0}img.res{max-width:100%;display:block;margin:8px 0}")
    parts = []
    for c in cells:
        s = _src(c)
        if c["cell_type"] == "code":
            block = f"<pre><code>{html.escape(s)}</code></pre>" if s.strip() else ""
            block += "".join(f'<pre class="out">{html.escape(t)}</pre>' for t in _text_outputs(c))
            block += "".join(f'<img class="res" src="data:{mime};base64,{b64.strip()}">' for mime, b64 in _images(c))
            parts.append(f'<div class="cell">{block}</div>')
        elif s.strip():
            parts.append(f'<div class="cell">{_md_html(s) if c["cell_type"] == "markdown" else html.escape(s)}</div>')
    return (f'<!DOCTYPE html><html><head><meta charset="utf-8"><title>{html.escape(title)}</title>'
            f"<style>{css}</style></head><body>\n" + "\n".join(parts) + "\n</body></html>\n")


def convert(sources: list[Path], out: Path, fmt: str, opts: dict) -> list[str]:
    src = sources[0]
    cells, lang = read(src)
    code = "\n".join(_src(c) for c in cells if c["cell_type"] == "code")
    notes_text = "\n".join(_src(c) for c in cells if c["cell_type"] != "code")
    pictures = sum(len(_images(c)) for c in cells)
    if fmt == "md":
        text, _ = to_markdown(cells, lang)
    elif fmt == "py":
        text = to_python(cells)
    elif fmt == "html":
        text = to_html(cells, src.stem)
    else:
        raise ConversionError(f"Unknown notebook conversion: {fmt}")
    Path(long_path(out)).write_text(text, encoding="utf-8", newline="\n")
    back = Path(long_path(out)).read_text(encoding="utf-8")
    if fmt == "html":
        import lxml.html

        back = " ".join(lxml.html.fromstring(back.encode("utf-8")).itertext())
        for _mime, b64 in (i for c in cells for i in _images(c)):
            try:
                base64.b64decode(b64.strip(), validate=False)
            except Exception as e:  # noqa: BLE001
                raise VerificationError("a picture in the results is damaged") from e
    if code.strip() and not set(words(code)) <= set(words(back)):
        raise VerificationError("some of the code is missing")
    cov = text_coverage(notes_text, back)
    if cov is not None and cov < 0.97:
        raise VerificationError(f"only {cov:.0%} of the notes made it into the new file")
    n_code = sum(1 for c in cells if c["cell_type"] == "code" and _src(c).strip())
    n_notes = sum(1 for c in cells if c["cell_type"] != "code" and _src(c).strip())
    notes = [f"Checked: {n_code} code cell{'s' if n_code != 1 else ''} and {n_notes} note{'s' if n_notes != 1 else ''}, "
             "all included. The notebook wasn't run."]
    if pictures and fmt == "html":
        notes.append(f"{pictures} picture{'s' if pictures != 1 else ''} from the results are inside the page.")
    elif pictures and fmt == "md":
        notes.append(f"{pictures} picture{'s' if pictures != 1 else ''} from the results aren't included (use HTML "
                     "to keep them).")
    elif fmt == "py":
        notes.append("Results aren't included in a script.")
    return notes
