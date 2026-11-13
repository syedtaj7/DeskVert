"""SHA-256 checksums: a small text file that proves files arrived unchanged.

One line per file, in the standard "sha256sum" form ("<hash> *<name>"), so
other tools (and Deskvert itself) can check the files later. Files from a
selected folder are listed with their path inside it. The files are read twice
and both readings must agree.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

from ..errors import ConversionError, VerificationError
from ..paths import long_path


def sha256(path: Path, progress=None) -> str:
    h = hashlib.sha256()
    with open(long_path(path), "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
            if progress:
                progress(len(chunk))
    return h.hexdigest()


def _names(sources: list[Path], roots: list[str]) -> list[str]:
    tops = [Path(r) for r in roots]
    out = []
    for p in sources:
        base = next((r for r in tops if str(p).lower().startswith(str(r).lower() + os.sep)), None)
        out.append(os.path.relpath(p, base.parent).replace(os.sep, "/") if base else p.name)
    return out


def convert(sources: list[Path], out: Path, fmt: str, opts: dict) -> list[str]:
    if fmt != "sha256":
        raise ConversionError(f"Unknown checksum: {fmt}")
    total = sum(os.path.getsize(long_path(p)) for p in sources) or 1
    done = [0]
    prog = opts.get("_progress_file")

    def step(n: int) -> None:
        done[0] += n
        if prog and done[0] % (64 << 20) < n:  # now and then
            try:
                Path(prog).write_text(f"{min(0.99, done[0] / total / 2):.3f}")
            except OSError:
                pass

    hashes = [sha256(p, step) for p in sources]
    names = _names(sources, opts.get("_roots") or [])
    Path(long_path(out)).write_text("".join(f"{h} *{n}\n" for h, n in zip(hashes, names)), encoding="utf-8",
                                    newline="\n")
    again = [sha256(p, step) for p in sources]  # a second reading: catches a file that's still being written
    if again != hashes:
        raise VerificationError("a file changed while it was being read")
    lines = Path(long_path(out)).read_text(encoding="utf-8").splitlines()
    if lines != [f"{h} *{n}" for h, n in zip(hashes, names)]:
        raise VerificationError("the checksum file doesn't match")
    shown = hashes[0][:16] + "…" if len(hashes) == 1 else f"{len(hashes)} files"
    return [f"Checked: SHA-256 of {shown}, each file read twice and identical both times.",
            "Send the .sha256 file along: anyone can check the files arrived unchanged."]
