"""Outlook .msg e-mails, read without Outlook (test files are built by tests/cfbwrite.py)."""

from __future__ import annotations

import io
import struct
import uuid
import zipfile
from pathlib import Path

from PIL import Image

from app.catalog import offers_for
from app.jobs import build_jobs
from app.settings import Settings
from app.worker import run_job
from tests.cfbwrite import bin_prop, build, text_prop


def _png() -> bytes:
    b = io.BytesIO()
    Image.new("RGB", (40, 30), "red").save(b, "PNG")
    return b.getvalue()


def make_msg(path: Path, big_attachment: bool = False) -> Path:
    when = 133_700_000_000_000_000  # a FILETIME (2024)
    props = b"\0" * 32 + struct.pack("<IIQ", 0x00390040, 0, when)  # top-level: 32-byte header, then entries
    attach_data = (b"Report line\n" * 600) if big_attachment else b"Minutes of the meeting"
    tree = dict([
        text_prop(0x0037, "Picnic on Sunday"),
        text_prop(0x0C1A, "Asha Rao"), text_prop(0x5D01, "asha@example.com"),
        text_prop(0x0E04, "Ravi Kumar"),
        text_prop(0x1000, "Hi Ravi, the picnic starts at noon by the lake. Bring the blue umbrella."),
        bin_prop(0x1013, b"<html><body><p>Hi Ravi, the picnic starts at <b>noon</b> by the lake. Bring the blue "
                         b"umbrella.</p><img src='cid:map1'></body></html>"),
        ("__properties_version1.0", props),
    ])
    tree["__recip_version1.0_#00000000"] = dict([
        text_prop(0x3001, "Ravi Kumar"), text_prop(0x39FE, "ravi@example.com"),
        ("__properties_version1.0", b"\0" * 8 + struct.pack("<IIQ", 0x0C150003, 0, 1))])
    tree["__attach_version1.0_#00000000"] = dict([
        text_prop(0x3707, "Minutes.txt"), text_prop(0x370E, "text/plain"), bin_prop(0x3701, attach_data)])
    tree["__attach_version1.0_#00000001"] = dict([
        text_prop(0x3707, "map.png"), text_prop(0x370E, "image/png"), text_prop(0x3712, "map1"),
        bin_prop(0x3701, _png())])
    path.write_bytes(build(tree))
    return path


def _run(files, label):
    offers, _ = offers_for(files, Settings())
    offer = next((o for o in offers if o.target.label == label), None)
    assert offer is not None, [o.target.label for o in offers]
    job = build_jobs(offer, {o.key: o.default for o in offer.options}, Settings())[0]
    job["id"] = uuid.uuid4().hex[:12]
    res = run_job(job)
    assert res["ok"], res.get("error")
    return Path(res["output"])


def test_msg_reads_as_an_email(tmp_path):
    import email
    from email import policy

    from app.engines.msgfile import to_eml

    msg = email.message_from_bytes(to_eml(make_msg(tmp_path / "Picnic.msg")), policy=policy.default)
    assert msg["Subject"] == "Picnic on Sunday" and "asha@example.com" in msg["From"]
    assert "ravi@example.com" in msg["To"] and msg["Date"]
    names = [p.get_filename() for p in msg.iter_attachments()]
    assert names == ["Minutes.txt"]  # the picture shown in the body isn't an attachment
    html = msg.get_body(("html",)).get_content()
    assert "noon" in html


def test_msg_to_pdf_text_and_attachments(tmp_path):
    import pymupdf

    src = make_msg(tmp_path / "Picnic.msg", big_attachment=True)  # a big attachment: ordinary sectors too
    pdf = _run([src], "PDF")
    with pymupdf.open(pdf) as d:
        text = " ".join(p.get_text() for p in d)
    assert "Picnic on Sunday" in text and "blue umbrella" in text and "Asha Rao" in text
    zipped = _run([src], "Attachments")
    with zipfile.ZipFile(zipped) as z:
        assert z.namelist() == ["Minutes.txt"] and z.read("Minutes.txt").startswith(b"Report line")
