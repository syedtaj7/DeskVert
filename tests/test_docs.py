"""Office documents and PDF tools. Each test runs one conversion, one at a time,
under the 25% CPU cap from conftest.py."""

from __future__ import annotations

import hashlib
import shutil
import uuid
from pathlib import Path

import pytest

from app.catalog import office_installed, offers_for
from app.jobs import build_jobs
from app.settings import Settings
from app.worker import run_job

pytestmark = pytest.mark.skipif(not office_installed("word"), reason="Microsoft Office not installed")


@pytest.fixture(scope="session")
def docs():
    from tests import doc_corpus

    return doc_corpus.build()


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _run(docs, tmp_path, names, label):
    srcs = []
    for n in names:
        shutil.copy2(docs[n], tmp_path / n)
        srcs.append(tmp_path / n)
    offers, _ = offers_for(srcs, Settings())
    offer = next((o for o in offers if o.target.label == label), None)
    assert offer is not None, f"{label} not offered for {names}: {[o.target.label for o in offers]}"
    before = [_sha(s) for s in srcs]
    jobs = build_jobs(offer, {o.key: o.default for o in offer.options}, Settings())
    r = run_job(jobs[0])
    assert [_sha(s) for s in srcs] == before, "source modified"
    return r


@pytest.mark.parametrize("name,label", [
    ("report.docx", "PDF"), ("report.docx", "ODT"), ("report.docx", "TXT"), ("notes.txt", "DOCX"),
    ("budget.xlsx", "ODS"), ("budget.xlsx", "CSV"), ("budget.xlsx", "PDF"),
    ("deck.pptx", "PDF"), ("deck.pptx", "PNG"),
    ("sample.pdf", "TXT"), ("sample.pdf", "PNG"), ("sample.pdf", "Split"),
])
def test_doc_conversion(docs, tmp_path, name, label):
    r = _run(docs, tmp_path, [name], label)
    assert r["ok"], f"{name} -> {label}: {r.get('error')}\n{r.get('detail')}"
    out = Path(r["output"])
    assert out.parent == tmp_path and out.exists()
    assert any(n.startswith("Checked") or "rebuilt" in n for n in r["notes"]), r["notes"]
    assert not [p for p in tmp_path.iterdir() if p.name.startswith(".")]


def test_merge_pdfs(docs, tmp_path):
    r = _run(docs, tmp_path, ["sample.pdf", "second.pdf"], "1 PDF")
    assert r["ok"], r.get("detail")
    import pymupdf

    with pymupdf.open(r["output"]) as d:
        assert d.page_count == 5


@pytest.mark.parametrize("name,label,expect", [
    ("protected.docx", "PDF", "password"),
    ("broken.docx", "PDF", ""),
    ("scanned.pdf", "TXT", "no text"),
])
def test_doc_failures_are_clean(docs, tmp_path, name, label, expect):
    r = _run(docs, tmp_path, [name], label)
    assert not r["ok"]
    assert "Unexpected" not in r["error"], r["error"]
    assert expect in r["error"].lower(), r["error"]
    assert sorted(p.name for p in tmp_path.iterdir()) == [name]


def test_no_office_left_running(docs, tmp_path):
    from app.engines.officeutil import pids_named

    before = {e: pids_named(e) for e in ("WINWORD.EXE", "EXCEL.EXE")}
    r = _run(docs, tmp_path, ["report.docx"], "RTF")
    assert r["ok"], r.get("detail")
    for exe, pids in before.items():
        assert pids_named(exe) <= pids, f"{exe} left running"
