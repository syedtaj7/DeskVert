"""ZIP and extract.

- zip:     the selected files -> one .zip (deflate level 6; already-compressed
           files like JPG or MP4 are stored as-is, which saves time and CPU)
- extract: .zip with Python's zipfile (safe paths, CRC checked); everything
           else (7z, rar, tar, gz, xz, bz2, zst, cab, iso) with Windows' own
           tar.exe (libarchive). Single-file .gz/.bz2/.xz use Python directly.
- tozip:   any of those archives -> a standard .zip

Every output is read back and checked before it's kept.
"""

from __future__ import annotations

import bz2
import gzip
import lzma
import os
import re
import shutil
import subprocess
import zipfile
from pathlib import Path

from ..errors import ConversionError, VerificationError
from ..paths import long_path

# Already compressed: deflating them again wastes CPU for ~0% gain.
STORED_EXTS = {
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".avif", ".heic", ".heif", ".mp3", ".m4a", ".aac", ".ogg", ".opus",
    ".flac", ".mp4", ".m4v", ".mkv", ".mov", ".webm", ".avi", ".zip", ".7z", ".rar", ".gz", ".bz2", ".xz", ".zst",
    ".docx", ".xlsx", ".pptx", ".odt", ".ods", ".odp", ".epub", ".jar", ".apk", ".cab", ".msi", ".pdf",
}
SINGLE_FILE = {".gz": gzip.open, ".bz2": bz2.open, ".xz": lzma.open}
TAR_LIKE = {".tar.gz", ".tar.bz2", ".tar.xz", ".tar.zst"}
BAD_CHARS = re.compile(r'[<>:"|?*\x00-\x1f]')


def _human(n: int) -> str:
    for unit, size in (("GB", 1_000_000_000), ("MB", 1_000_000), ("KB", 1000)):
        if n >= size:
            return f"{n / size:.1f} {unit}"
    return f"{n} bytes"


def _need_space(folder: Path, needed: int) -> None:
    try:
        free = shutil.disk_usage(long_path(folder)).free
    except OSError:
        return
    if free < needed + 50_000_000:
        raise ConversionError(f"Not enough free disk space: about {_human(needed)} is needed, "
                              f"{_human(free)} is free.")


def _files_under(folder: Path) -> list[Path]:
    out = []
    for root, _dirs, files in os.walk(long_path(folder)):
        out += [Path(root) / f for f in files]
    return out


def _rel(path: Path, base: Path) -> str:
    return os.path.relpath(long_path(path), long_path(base)).replace(os.sep, "/")


# ---------------------------------------------------------------- zip

def _write_zip(items: list[tuple[Path, str]], out: Path, notes: list[str]) -> None:
    """items = [(file on disk, name inside the zip)]"""
    total = sum(os.path.getsize(long_path(p)) for p, _ in items)
    _need_space(out.parent, total)
    with zipfile.ZipFile(long_path(out), "w", allowZip64=True) as z:
        for path, name in items:
            stored = Path(name).suffix.lower() in STORED_EXTS
            z.write(long_path(path), name, compress_type=zipfile.ZIP_STORED if stored else zipfile.ZIP_DEFLATED,
                    compresslevel=None if stored else 6)
    # Read every file back: zipfile checks each CRC while reading.
    with zipfile.ZipFile(long_path(out)) as z:
        bad = z.testzip()
        if bad:
            raise VerificationError(f"{bad} is damaged inside the zip")
        sizes = {i.filename: i.file_size for i in z.infolist() if not i.is_dir()}
    for path, name in items:
        if sizes.get(name) != os.path.getsize(long_path(path)):
            raise VerificationError(f"{name} is missing or the wrong size inside the zip")
    after = os.path.getsize(long_path(out))
    n = len(items)
    notes.append(f"Checked: {n} file{'s' if n != 1 else ''}, {_human(total)} → {_human(after)}.")


def make_zip(sources: list[Path], out: Path, notes: list[str]) -> None:
    items, used = [], set()
    for p in sources:
        name, k = p.name, 2
        while name.lower() in used:  # same name from different folders
            name, k = f"{p.stem} ({k}){p.suffix}", k + 1
        used.add(name.lower())
        items.append((p, name))
    _write_zip(items, out, notes)


# ---------------------------------------------------------------- extract

def _is_tar_like(src: Path) -> bool:
    n = src.name.lower()
    return any(n.endswith(e) for e in TAR_LIKE) or src.suffix.lower() in (".tgz", ".tbz", ".tbz2", ".txz")


def _extract_zip(src: Path, out: Path) -> int:
    try:
        z = zipfile.ZipFile(long_path(src))
    except zipfile.BadZipFile as e:
        raise ConversionError("This ZIP is damaged or isn't really a ZIP file.") from e
    with z:
        infos = [i for i in z.infolist() if not i.is_dir()]
        if any(i.flag_bits & 0x1 for i in infos):
            raise ConversionError("This ZIP is password-protected. Open it in File Explorer to type the password.")
        _need_space(out.parent, sum(i.file_size for i in infos))
        out.mkdir(parents=True, exist_ok=True)
        base = Path(os.path.abspath(out))
        written = set()
        for info in infos:
            parts = [BAD_CHARS.sub("_", s).rstrip(" .") or "_" for s in re.split(r"[\\/]+", info.filename)
                     if s not in ("", ".", "..")]
            if not parts:
                continue
            target = base.joinpath(*parts)
            if os.path.commonpath([str(base), os.path.abspath(target)]) != str(base):
                raise ConversionError(f"Unsafe file name in the archive: {info.filename}")
            if str(target).lower() in written:
                raise ConversionError(f"The archive has two files named {'/'.join(parts)}.")
            written.add(str(target).lower())
            target.parent.mkdir(parents=True, exist_ok=True)
            with z.open(info) as fin, open(long_path(target), "wb") as fout:  # CRC checked on read
                shutil.copyfileobj(fin, fout, 1024 * 1024)
            if os.path.getsize(long_path(target)) != info.file_size:
                raise VerificationError(f"{info.filename} came out the wrong size")
    return len(infos)


def _tar() -> str:
    exe = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "tar.exe"
    if not exe.exists():
        raise ConversionError("This kind of archive needs Windows 10 (1803) or newer. ZIP files still work.")
    return str(exe)


def _run_tar(args: list[str]) -> str:
    r = subprocess.run([_tar(), *args], capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
    err = r.stderr.decode("utf-8", "replace")
    if r.returncode != 0:
        low = err.lower()
        if "passphrase" in low or "encrypt" in low or "password" in low:
            raise ConversionError("This archive is password-protected, which Tapshift can't open.")
        if "unrecognized archive format" in low or "not supported" in low or "unsupported" in low:
            raise ConversionError("Windows can't read this kind of archive (some RAR or 7z options aren't "
                                  "supported).")
        detail = "; ".join(line.replace("tar.exe: ", "").strip() for line in err.splitlines()
                           if line.strip() and "Error exit delayed" not in line)
        raise ConversionError(f"The archive couldn't be read; it may be damaged. ({detail[:200]})")
    return r.stdout.decode("utf-8", "replace")


def _extract_tar(src: Path, out: Path) -> int:
    listing = _run_tar(["-tf", str(src)])
    entries = [line for line in listing.splitlines() if line.strip() and not line.endswith(("/", "\\"))]
    if not entries:
        raise ConversionError("The archive is empty.")
    _need_space(out.parent, os.path.getsize(long_path(src)) * 3)
    out.mkdir(parents=True, exist_ok=True)
    _run_tar(["-xf", str(src), "-C", str(out)])  # bsdtar refuses absolute and ../ paths by default
    got = len(_files_under(out))
    if got < len(set(entries)):
        raise VerificationError(f"{got} files extracted, but the archive lists {len(set(entries))}")
    return got


def _extract_single(src: Path, out: Path) -> int:
    opener = SINGLE_FILE[src.suffix.lower()]
    out.mkdir(parents=True, exist_ok=True)
    target = out / (BAD_CHARS.sub("_", src.stem) or "file")
    try:
        with opener(long_path(src), "rb") as fin, open(long_path(target), "wb") as fout:
            shutil.copyfileobj(fin, fout, 1024 * 1024)  # each format checks its own CRC at the end
    except (OSError, EOFError, lzma.LZMAError) as e:
        raise ConversionError(f"The archive is damaged ({e}).") from e
    return 1


def extract(src: Path, out: Path, notes: list[str]) -> None:
    ext = src.suffix.lower()
    if ext == ".zip":
        n = _extract_zip(src, out)
    elif ext in SINGLE_FILE and not _is_tar_like(src):
        n = _extract_single(src, out)
    else:
        n = _extract_tar(src, out)
    if not _files_under(out):
        raise ConversionError("The archive is empty.")
    notes.append(f"Checked: {n} file{'s' if n != 1 else ''} extracted.")


def to_zip(src: Path, out: Path, notes: list[str]) -> None:
    unpacked = out.parent / "unpacked"
    extract(src, unpacked, [])
    files = sorted(_files_under(unpacked))
    _write_zip([(p, _rel(p, unpacked)) for p in files], out, notes)


def convert(sources: list[Path], out: Path, fmt: str, opts: dict) -> list[str]:
    notes: list[str] = []
    if fmt == "zip":
        make_zip(sources, out, notes)
    elif fmt == "extract":
        extract(sources[0], out, notes)
    elif fmt == "tozip":
        to_zip(sources[0], out, notes)
    else:
        raise ConversionError(f"Unknown archive action: {fmt}")
    return notes
