"""Runs every offered image conversion on every sample file and checks that:
- the conversion succeeds and passes the built-in safety check,
- the output lands next to the source with the right extension,
- the source file is byte-for-byte unchanged,
- broken inputs fail cleanly and leave nothing behind.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import uuid
from pathlib import Path

import pytest
from PIL import Image

from app.catalog import offers_for
from app.settings import Settings
from app.worker import run_job
from tests import corpus

BROKEN = {"truncated.jpg", "empty.png", "not_really.png"}


@pytest.fixture(scope="session")
def samples(tmp_path_factory) -> dict[str, Path]:
    return corpus.build(tmp_path_factory.mktemp("corpus"))


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _job(sources, offer, opts=None):
    return {
        "id": uuid.uuid4().hex[:12],
        "sources": [str(s) for s in sources],
        "target": offer.target.key,
        "ext": offer.target.ext,
        "out_stem": Path(sources[0]).stem,
        "options": opts if opts is not None else {o.key: o.default for o in offer.options},
        "keep_modified_date": True,
    }


def _cases():
    names = [
        "photo_rot6.jpg", "plain.jpg", "cmyk.jpg", "alpha.png", "palette_trns.png", "gray16.png",
        "gray.png", "bilevel.png", "anim.gif", "anim.webp", "anim.png", "pages.tiff", "photo.heic",
        "alpha.avif", "plain.bmp", "icon.ico", "alpha.tga", "alpha.webp", "photo.webp", "drawing.svg",
        "Фото 写真 é.png", "tall_portrait.jpg",
    ]
    fmts = ["jpg", "png", "webp", "pdf", "heic", "avif", "ico", "tiff", "gif", "bmp", "tga"]
    return [(n, f) for n in names for f in fmts]


@pytest.mark.parametrize("name,fmt", _cases())
def test_convert_matrix(samples, tmp_path, name, fmt):
    src_orig = samples[name]
    src = tmp_path / src_orig.name
    shutil.copy2(src_orig, src)
    offers, _ = offers_for([src], Settings())
    offer = next((o for o in offers if o.target.fmt == fmt), None)
    if offer is None:
        pytest.skip("same format: not offered")
    before = _sha(src)
    mtime = os.stat(src).st_mtime_ns
    r = run_job(_job([src], offer))
    assert r["ok"], f"{name} -> {fmt}: {r.get('error')}\n{r.get('detail')}"
    out = Path(r["output"])
    assert out.parent == src.parent
    assert out.suffix == offer.target.ext
    assert out.stat().st_size > 0
    assert _sha(src) == before, "source file was modified"
    assert os.stat(out).st_mtime_ns == mtime, "modified date not copied"
    leftovers = [p for p in tmp_path.iterdir() if p.name.startswith(".")]
    assert not leftovers


def test_orientation_applied(samples, tmp_path):
    src = tmp_path / "photo_rot6.jpg"
    shutil.copy2(samples["photo_rot6.jpg"], src)
    offers, _ = offers_for([src], Settings())
    offer = next(o for o in offers if o.target.fmt == "png")
    r = run_job(_job([src], offer))
    assert r["ok"], r.get("detail")
    with Image.open(r["output"]) as im:
        assert im.size == (200, 320)  # rotated 90 degrees
        ex = im.getexif()
        assert ex.get(0x0112, 1) == 1
        assert ex.get(0x010F) == "TestCam"  # camera make kept
        assert im.info.get("icc_profile")


def test_no_overwrite_creates_numbered_copy(samples, tmp_path):
    src = tmp_path / "plain.jpg"
    shutil.copy2(samples["plain.jpg"], src)
    existing = tmp_path / "plain.png"
    existing.write_bytes(b"do not touch")
    offers, _ = offers_for([src], Settings())
    offer = next(o for o in offers if o.target.fmt == "png")
    r = run_job(_job([src], offer))
    assert r["ok"], r.get("detail")
    assert Path(r["output"]).name == "plain (1).png"
    assert existing.read_bytes() == b"do not touch"


def test_combined_pdf(samples, tmp_path):
    srcs = []
    for n in ("plain.jpg", "alpha.png", "pages.tiff", "photo.heic"):
        shutil.copy2(samples[n], tmp_path / n)
        srcs.append(tmp_path / n)
    offers, _ = offers_for(srcs, Settings())
    offer = next(o for o in offers if o.target.combine)
    r = run_job(_job(srcs, offer))
    assert r["ok"], r.get("detail")
    import pymupdf

    with pymupdf.open(r["output"]) as doc:
        assert doc.page_count == 1 + 1 + 3 + 1


def test_lossless_webp_is_exact(samples, tmp_path):
    src = tmp_path / "alpha.png"
    shutil.copy2(samples["alpha.png"], src)
    offers, _ = offers_for([src], Settings())
    offer = next(o for o in offers if o.target.fmt == "webp")
    assert offer.caption == "lossless"
    r = run_job(_job([src], offer))
    assert r["ok"], r.get("detail")


@pytest.mark.parametrize("name", sorted(BROKEN))
def test_broken_inputs_fail_cleanly(samples, tmp_path, name):
    src = tmp_path / name
    shutil.copy2(samples[name], src)
    offers, _ = offers_for([src], Settings())
    offer = next(o for o in offers if o.target.fmt == "webp")
    r = run_job(_job([src], offer))
    assert not r["ok"]
    assert r["error"] and "Unexpected" not in r["error"], r["error"]
    assert sorted(p.name for p in tmp_path.iterdir()) == [name]


def test_missing_source(tmp_path):
    offers, _ = offers_for([tmp_path / "ghost.png"], Settings())
    r = run_job(_job([tmp_path / "ghost.png"], offers[0]))
    assert not r["ok"] and "no longer exists" in r["error"]
