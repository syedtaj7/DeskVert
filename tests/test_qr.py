"""The QR encoder against values published for the standard, and read back by its own reader."""

from __future__ import annotations

import pytest

from app.engines import qr


def test_reed_solomon_matches_the_standard_example():
    # "HELLO WORLD", version 1-Q: data codewords and their 13 error-correction codewords
    data = [32, 91, 11, 120, 209, 114, 220, 77, 67, 64, 236, 17, 236]
    assert qr.rs_encode(data, 13) == [168, 72, 22, 82, 217, 54, 156, 0, 46, 15, 180, 122, 16]
    assert qr.rs_syndromes_ok(data + qr.rs_encode(data, 13), 13)
    assert not qr.rs_syndromes_ok(data + [0] * 13, 13)


def test_format_and_version_bits_match_the_standard():
    assert f"{qr.bch_format('M', 0):015b}" == "101010000010010"
    assert f"{qr.bch_format('L', 0):015b}" == "111011111000100"
    assert f"{qr.bch_format('Q', 0):015b}" == "011010101011111"
    assert f"{qr.bch_format('H', 0):015b}" == "001011010001001"
    assert f"{qr.bch_version(7):018b}" == "000111110010010100"


@pytest.mark.parametrize("version", range(1, 21))
def test_every_version_fills_exactly(version):
    sym = qr.Symbol(version)
    ec_len, groups = qr.BLOCKS_M[version]
    total = sum(c * s for c, s in groups) + ec_len * sum(c for c, _ in groups)
    spots = len(list(sym.data_positions()))
    assert spots - total * 8 in (0, 3, 4, 7)


@pytest.mark.parametrize("text", ["https://example.com", "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                                  "https://मराठी.भारत/पान?q=ü", "x" * 300, "https://a.test/" + "p" * 640])
def test_round_trip(tmp_path, text):
    sym = qr.make(text)
    assert qr.read_back(sym.dark) == text
    out = tmp_path / "code.png"
    qr.render(sym, out)
    assert qr.read_back(qr.from_picture(out, sym.size)) == text


def test_too_long():
    with pytest.raises(Exception, match="too long"):
        qr.make("x" * 700)


def test_a_flipped_module_is_caught():
    sym = qr.make("https://example.com/check")
    x, y = next(sym.data_positions())
    sym.dark[y][x] = not sym.dark[y][x]
    with pytest.raises(Exception, match="error check"):
        qr.read_back(sym.dark)
