"""QR codes for links: a picture anyone can scan with a phone camera.

Written from the QR standard (ISO/IEC 18004, Model 2), byte mode, error correction
level M (about 15 % of the code can be damaged and it still scans), versions 1-20
(up to 666 bytes: any link). The code is then *read back* from the picture by an
independent reader below: format bits, every Reed-Solomon block and the text itself
must come out right before the file is saved.
"""

from __future__ import annotations

from pathlib import Path

from ..errors import ConversionError, VerificationError
from ..paths import long_path

# ---------------------------------------------------------------- tables (level M)

# version -> (EC codewords per block, [(number of blocks, data codewords per block), ...])
BLOCKS_M = {
    1: (10, [(1, 16)]), 2: (16, [(1, 28)]), 3: (26, [(1, 44)]), 4: (18, [(2, 32)]), 5: (24, [(2, 43)]),
    6: (16, [(4, 27)]), 7: (18, [(4, 31)]), 8: (22, [(2, 38), (2, 39)]), 9: (22, [(3, 36), (2, 37)]),
    10: (26, [(4, 43), (1, 44)]), 11: (30, [(1, 50), (4, 51)]), 12: (22, [(6, 36), (2, 37)]),
    13: (22, [(8, 37), (1, 38)]), 14: (24, [(4, 40), (5, 41)]), 15: (24, [(5, 41), (5, 42)]),
    16: (28, [(7, 45), (3, 46)]), 17: (28, [(10, 46), (1, 47)]), 18: (26, [(9, 43), (4, 44)]),
    19: (26, [(3, 44), (11, 45)]), 20: (26, [(3, 41), (13, 42)]),
}
ALIGN = {1: [], 2: [6, 18], 3: [6, 22], 4: [6, 26], 5: [6, 30], 6: [6, 34], 7: [6, 22, 38], 8: [6, 24, 42],
         9: [6, 26, 46], 10: [6, 28, 50], 11: [6, 30, 54], 12: [6, 32, 58], 13: [6, 34, 62], 14: [6, 26, 46, 66],
         15: [6, 26, 48, 70], 16: [6, 26, 50, 74], 17: [6, 30, 54, 78], 18: [6, 30, 56, 82], 19: [6, 30, 58, 86],
         20: [6, 34, 62, 90]}
EC_BITS = {"L": 1, "M": 0, "Q": 3, "H": 2}
MASKS = [
    lambda x, y: (x + y) % 2 == 0,
    lambda x, y: y % 2 == 0,
    lambda x, y: x % 3 == 0,
    lambda x, y: (x + y) % 3 == 0,
    lambda x, y: (x // 3 + y // 2) % 2 == 0,
    lambda x, y: x * y % 2 + x * y % 3 == 0,
    lambda x, y: (x * y % 2 + x * y % 3) % 2 == 0,
    lambda x, y: ((x + y) % 2 + x * y % 3) % 2 == 0,
]

# ---------------------------------------------------------------- GF(256) and Reed-Solomon

EXP = [0] * 512
LOG = [0] * 256
_v = 1
for _i in range(255):
    EXP[_i] = _v
    LOG[_v] = _i
    _v <<= 1
    if _v & 0x100:
        _v ^= 0x11D
for _i in range(255, 512):
    EXP[_i] = EXP[_i - 255]


def gf_mul(a: int, b: int) -> int:
    return 0 if a == 0 or b == 0 else EXP[LOG[a] + LOG[b]]


def rs_generator(degree: int) -> list[int]:
    """Coefficients of (x - a^0)(x - a^1)...(x - a^(degree-1)), highest power first."""
    g = [1]
    for i in range(degree):
        g = [a ^ gf_mul(b, EXP[i]) for a, b in zip(g + [0], [0] + g)]
    return g


def rs_encode(data: list[int], degree: int) -> list[int]:
    """The error-correction codewords for one block (the remainder of data * x^degree / g)."""
    g = rs_generator(degree)
    rem = list(data) + [0] * degree
    for i in range(len(data)):
        c = rem[i]
        if c:
            for j in range(1, len(g)):
                rem[i + j] ^= gf_mul(g[j], c)
    return rem[len(data):]


def rs_syndromes_ok(block: list[int], degree: int) -> bool:
    """A reader's check: a correct block evaluates to 0 at a^0 ... a^(degree-1)."""
    for i in range(degree):
        s = 0
        for c in block:
            s = gf_mul(s, EXP[i]) ^ c
        if s:
            return False
    return True


# ---------------------------------------------------------------- format and version bits

def bch_format(ec: str, mask: int) -> int:
    data = EC_BITS[ec] << 3 | mask
    rem = data
    for _ in range(10):
        rem = (rem << 1) ^ ((rem >> 9) * 0x537)
    return (data << 10 | rem) ^ 0x5412


def bch_version(version: int) -> int:
    rem = version
    for _ in range(12):
        rem = (rem << 1) ^ ((rem >> 11) * 0x1F25)
    return version << 12 | rem


# ---------------------------------------------------------------- the symbol

class Symbol:
    def __init__(self, version: int):
        self.version = version
        self.size = version * 4 + 17
        n = self.size
        self.dark = [[False] * n for _ in range(n)]
        self.fixed = [[False] * n for _ in range(n)]
        self._function_patterns()

    def set(self, x: int, y: int, dark: bool) -> None:
        self.dark[y][x] = dark
        self.fixed[y][x] = True

    def _function_patterns(self) -> None:
        n = self.size
        for i in range(n):  # timing
            self.set(6, i, i % 2 == 0)
            self.set(i, 6, i % 2 == 0)
        for cx, cy in ((3, 3), (n - 4, 3), (3, n - 4)):  # finders with their separators
            for dy in range(-4, 5):
                for dx in range(-4, 5):
                    x, y = cx + dx, cy + dy
                    if 0 <= x < n and 0 <= y < n:
                        d = max(abs(dx), abs(dy))
                        self.set(x, y, d not in (2, 4))
        pos = ALIGN[self.version]
        for i, ax in enumerate(pos):
            for j, ay in enumerate(pos):
                if (i, j) in ((0, 0), (0, len(pos) - 1), (len(pos) - 1, 0)):
                    continue
                for dy in range(-2, 3):
                    for dx in range(-2, 3):
                        self.set(ax + dx, ay + dy, max(abs(dx), abs(dy)) != 1)
        self.draw_format(0)  # reserved now, written for real once the mask is chosen
        if self.version >= 7:
            bits = bch_version(self.version)
            for i in range(18):
                bit = bool(bits >> i & 1)
                a, b = n - 11 + i % 3, i // 3
                self.set(a, b, bit)
                self.set(b, a, bit)

    def draw_format(self, bits: int) -> None:
        n = self.size

        def bit(i):
            return bool(bits >> i & 1)

        for i in range(6):
            self.set(8, i, bit(i))
        self.set(8, 7, bit(6))
        self.set(8, 8, bit(7))
        self.set(7, 8, bit(8))
        for i in range(9, 15):
            self.set(14 - i, 8, bit(i))
        for i in range(8):
            self.set(n - 1 - i, 8, bit(i))
        for i in range(8, 15):
            self.set(8, n - 15 + i, bit(i))
        self.set(8, n - 8, True)  # always dark

    def data_positions(self):
        """Free modules in the standard zigzag order (two columns at a time, up then down)."""
        n = self.size
        right = n - 1
        while right >= 1:
            if right == 6:
                right = 5
            upward = (right + 1) & 2 == 0
            for vert in range(n):
                y = n - 1 - vert if upward else vert
                for j in range(2):
                    x = right - j
                    if not self.fixed[y][x]:
                        yield x, y
            right -= 2

    def place(self, codewords: list[int]) -> None:
        bits = [(c >> (7 - k)) & 1 for c in codewords for k in range(8)]
        spots = list(self.data_positions())
        rem = len(spots) - len(bits)
        if rem not in (0, 3, 4, 7):  # the standard's remainder bits; anything else is a wrong table
            raise VerificationError(f"version {self.version} has {len(spots)} free modules for {len(bits)} bits")
        for (x, y), b in zip(spots, bits + [0] * rem):
            self.dark[y][x] = bool(b)

    def apply_mask(self, mask: int) -> None:
        f = MASKS[mask]
        for y in range(self.size):
            for x in range(self.size):
                if not self.fixed[y][x] and f(x, y):
                    self.dark[y][x] = not self.dark[y][x]

    def penalty(self) -> int:
        n, m = self.size, self.dark
        score = 0
        lines = [m[y] for y in range(n)] + [[m[y][x] for y in range(n)] for x in range(n)]
        pattern = [True, False, True, True, True, False, True]
        for line in lines:
            run, prev = 0, None
            for v in line:
                if v == prev:
                    run += 1
                else:
                    if run >= 5:
                        score += run - 2
                    run, prev = 1, v
            if run >= 5:
                score += run - 2
            for i in range(n - 6):
                if line[i:i + 7] == pattern:
                    before = line[max(0, i - 4):i]
                    after = line[i + 7:i + 11]
                    if (len(before) == 4 and not any(before)) or (len(after) == 4 and not any(after)):
                        score += 40
        for y in range(n - 1):
            for x in range(n - 1):
                if m[y][x] == m[y][x + 1] == m[y + 1][x] == m[y + 1][x + 1]:
                    score += 3
        dark = sum(sum(r) for r in m)
        score += abs(dark * 20 - n * n * 10) // (n * n) * 10
        return score


def _encode_bits(data: bytes, version: int) -> list[int]:
    ec_len, groups = BLOCKS_M[version]
    capacity = sum(count * size for count, size in groups)
    bits: list[int] = []

    def put(value, length):
        bits.extend((value >> (length - 1 - i)) & 1 for i in range(length))

    put(0b0100, 4)
    put(len(data), 8 if version <= 9 else 16)
    for b in data:
        put(b, 8)
    put(0, min(4, capacity * 8 - len(bits)))
    while len(bits) % 8:
        bits.append(0)
    words = [int("".join(map(str, bits[i:i + 8])), 2) for i in range(0, len(bits), 8)]
    i = 0
    while len(words) < capacity:  # the standard's filler bytes, alternating
        words.append((0xEC, 0x11)[i % 2])
        i += 1
    return words


def _interleave(words: list[int], version: int) -> list[int]:
    ec_len, groups = BLOCKS_M[version]
    blocks, k = [], 0
    for count, size in groups:
        for _ in range(count):
            blocks.append(words[k:k + size])
            k += size
    ecs = [rs_encode(b, ec_len) for b in blocks]
    out = []
    for i in range(max(len(b) for b in blocks)):
        out += [b[i] for b in blocks if i < len(b)]
    for i in range(ec_len):
        out += [e[i] for e in ecs]
    return out


def _version_for(n_bytes: int) -> int:
    for v in range(1, 21):
        capacity = sum(c * s for c, s in BLOCKS_M[v][1])
        header = 4 + (8 if v <= 9 else 16)
        if header + 8 * n_bytes <= capacity * 8:
            return v
    raise ConversionError("That link is too long for a QR code (more than 666 characters).")


def make(text: str) -> Symbol:
    data = text.encode("utf-8")
    version = _version_for(len(data))
    codewords = _interleave(_encode_bits(data, version), version)
    best, best_score = None, None
    for mask in range(8):
        s = Symbol(version)
        s.place(codewords)
        s.apply_mask(mask)
        s.draw_format(bch_format("M", mask))
        score = s.penalty()
        if best_score is None or score < best_score:
            best, best_score = s, score
    return best


# ---------------------------------------------------------------- the independent reader (the check)

def read_back(dark: list[list[bool]]) -> str:
    """Decode a symbol from its modules: the format bits, unmasking, every block's error check, the text."""
    n = len(dark)
    version = (n - 17) // 4
    if version not in BLOCKS_M:
        raise VerificationError("the QR code has an unexpected size")
    fmt = 0
    for i in range(6):
        fmt |= dark[i][8] << i
    fmt |= dark[7][8] << 6 | dark[8][8] << 7 | dark[8][7] << 8
    for i in range(9, 15):
        fmt |= dark[8][14 - i] << i
    mask = next((m for m in range(8) if bch_format("M", m) == fmt), None)
    if mask is None:
        raise VerificationError("the QR code's format bits are wrong")
    template = Symbol(version)  # where the function patterns are (not their values)
    f = MASKS[mask]
    bits = [int(dark[y][x] ^ f(x, y)) for x, y in template.data_positions()]
    ec_len, groups = BLOCKS_M[version]
    sizes = [size for count, size in groups for _ in range(count)]
    total = sum(sizes) + ec_len * len(sizes)
    words = [int("".join(map(str, bits[i * 8:i * 8 + 8])), 2) for i in range(total)]
    blocks = [[] for _ in sizes]
    k = 0
    for i in range(max(sizes)):
        for b, size in enumerate(sizes):
            if i < size:
                blocks[b].append(words[k])
                k += 1
    for i in range(ec_len):
        for b in range(len(sizes)):
            blocks[b].append(words[k])
            k += 1
    for b in blocks:
        if not rs_syndromes_ok(b, ec_len):
            raise VerificationError("a QR code block fails its error check")
    data = [w for b, size in zip(blocks, sizes) for w in b[:size]]
    stream = "".join(f"{w:08b}" for w in data)
    if stream[:4] != "0100":
        raise VerificationError("the QR code isn't in byte mode")
    count_len = 8 if version <= 9 else 16
    n_bytes = int(stream[4:4 + count_len], 2)
    start = 4 + count_len
    raw = bytes(int(stream[start + 8 * i:start + 8 * i + 8], 2) for i in range(n_bytes))
    return raw.decode("utf-8")


# ---------------------------------------------------------------- the picture

def render(sym: Symbol, out: Path, scale: int = 0) -> int:
    from PIL import Image

    border = 4
    scale = scale or max(8, 1000 // (sym.size + 2 * border))
    side = (sym.size + 2 * border) * scale
    im = Image.new("1", (side, side), 1)
    px = im.load()
    for y in range(sym.size):
        for x in range(sym.size):
            if sym.dark[y][x]:
                for dy in range(scale):
                    for dx in range(scale):
                        px[(x + border) * scale + dx, (y + border) * scale + dy] = 0
    im.save(long_path(out), "PNG", optimize=True)
    return side


def from_picture(path: Path, modules: int) -> list[list[bool]]:
    """Sample the saved picture back into modules (the check reads the file, not the memory)."""
    from PIL import Image

    with Image.open(long_path(path)) as im:
        g = im.convert("L")
        side = g.size[0]
        border = 4
        scale = side // (modules + 2 * border)
        return [[g.getpixel(((x + border) * scale + scale // 2, (y + border) * scale + scale // 2)) < 128
                 for x in range(modules)] for y in range(modules)]


def convert(sources: list[Path], out: Path, fmt: str, opts: dict) -> list[str]:
    from .webpage import read_url

    if fmt != "png":
        raise ConversionError(f"Unknown QR code format: {fmt}")
    url = read_url(sources[0])
    sym = make(url)
    side = render(sym, out)
    if read_back(from_picture(out, sym.size)) != url:
        raise VerificationError("the QR code doesn't read back as the link")
    return [f"Checked: the QR code reads back exactly as the link (version {sym.version}, {side}×{side} px, "
            "survives about 15 % damage).", "Point a phone camera at it to open the page."]
