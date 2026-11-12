"""A web clip (text or a table you selected on a page) as plain text: one paragraph per line,
table rows as tab-separated cells. Read back and compared with the clip's own words."""

from __future__ import annotations

from pathlib import Path

from ..errors import ConversionError, VerificationError
from ..paths import long_path

BLOCKS = {"p", "div", "li", "h1", "h2", "h3", "h4", "h5", "h6", "blockquote", "pre", "section", "article",
          "header", "footer", "dt", "dd", "figcaption", "caption", "br", "hr", "tr", "ul", "ol", "table"}
LIST_MARK = "• "


def _body(html: str):
    import lxml.html

    root = lxml.html.document_fromstring(html)
    for bad in root.xpath("//script|//style|//head"):
        bad.drop_tree()
    body = root.find("body")
    return body if body is not None else root


def text_of(html: str) -> str:
    """The words of the clip, laid out as plain text."""
    lines: list[str] = []
    cur: list[str] = []

    def flush():
        line = " ".join("".join(cur).split())
        if line:
            lines.append(line)
        cur.clear()

    def walk(el):
        tag = el.tag if isinstance(el.tag, str) else ""
        if tag == "tr":
            flush()
            cells = [" ".join(c.text_content().split()) for c in el
                     if isinstance(c.tag, str) and c.tag in ("td", "th")]
            if any(cells):
                lines.append("\t".join(cells))
        else:
            if tag in BLOCKS:
                flush()
            if tag == "li":
                cur.append(LIST_MARK)
            if el.text:
                cur.append(el.text)
            for child in el:
                walk(child)
            if tag in BLOCKS:
                flush()
        if el.tail:
            cur.append(el.tail)

    walk(_body(html))
    flush()
    return "\n".join(lines)


def convert(sources: list[Path], out: Path, fmt: str, opts: dict) -> list[str]:
    if fmt in ("pdf", "png"):
        from .webpage import clip

        return clip(Path(long_path(sources[0])), out, fmt)
    if fmt != "txt":
        raise ConversionError(f"Unknown clip conversion: {fmt}")
    html = Path(long_path(sources[0])).read_text(encoding="utf-8", errors="replace")
    text = text_of(html)
    if not text.strip():
        raise ConversionError("There's no text in this selection.")
    Path(long_path(out)).write_text(text + "\n", encoding="utf-8")
    back = Path(long_path(out)).read_text(encoding="utf-8")
    # every word, in order, exactly as in the clip (only the list bullets are added)
    if "".join(back.replace(LIST_MARK, "").split()) != "".join(_body(html).text_content().split()):
        raise VerificationError("the text came out different from the selection")
    n = len(text.splitlines())
    return [f"Checked: {n} line{'s' if n != 1 else ''}, every word as selected."]
