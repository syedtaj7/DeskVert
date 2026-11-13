"""Moving a finished, checked output next to the original without ever
overwriting anything.

Outputs are built in a private work folder. Only after they pass the safety
checks are they moved to the destination under a name that doesn't exist yet
(``photo.webp``, then ``photo (1).webp``...). The source file is only ever read.
Folder outputs (one image per page...) follow the same rules.
"""

from __future__ import annotations

import errno
import hashlib
import os
import shutil
import uuid
from pathlib import Path

from .errors import ConversionError
from .paths import fallback_output_dir, long_path, work_root

ERROR_NOT_SAME_DEVICE = 17
_WRITE_DENIED = {5, 19, 82}  # access denied, write-protected, cannot make


def candidate_names(stem: str, ext: str):
    yield f"{stem}{ext}"
    n = 1
    while n < 10000:
        yield f"{stem} ({n}){ext}"
        n += 1


def make_workdir(src_folder: Path, job_id: str) -> Path:
    """A scratch folder on the same drive as the destination when possible, so
    the final move is an atomic rename instead of a copy."""
    root = work_root()
    if os.path.splitdrive(str(root.absolute()))[0].lower() == os.path.splitdrive(str(src_folder.absolute()))[0].lower():
        d = root / job_id
        d.mkdir(parents=True, exist_ok=True)
        return d
    try:
        d = src_folder / f".deskvert-{job_id}"
        d.mkdir()
        _set_hidden(d)
        return d
    except OSError:
        d = root / job_id
        d.mkdir(parents=True, exist_ok=True)
        return d


def _set_hidden(p: Path) -> None:
    if os.name == "nt":
        import ctypes

        ctypes.windll.kernel32.SetFileAttributesW(long_path(p), 0x2)


def _sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(long_path(p), "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _place(tmp: Path, folder: Path, stem: str, ext: str) -> Path:
    staged: Path | None = None
    try:
        for name in candidate_names(stem, ext):
            final = folder / name
            if os.path.lexists(long_path(final)):
                continue
            src = staged or tmp
            try:
                # os.rename refuses to replace an existing file on Windows, so a
                # file that appears at the last moment is never overwritten.
                os.rename(long_path(src), long_path(final))
                return final
            except FileExistsError:
                continue
            except OSError as e:
                if getattr(e, "winerror", None) == ERROR_NOT_SAME_DEVICE or e.errno == errno.EXDEV:
                    # Different drive: copy next to the destination first, check
                    # the copy is identical, then rename it into place.
                    staged = folder / f".{stem}.{uuid.uuid4().hex[:8]}.partial"
                    if os.path.isdir(long_path(tmp)):
                        shutil.copytree(long_path(tmp), long_path(staged))
                        pairs = [(f, staged / f.relative_to(tmp)) for f in Path(tmp).rglob("*") if f.is_file()]
                    else:
                        shutil.copyfile(long_path(tmp), long_path(staged))
                        pairs = [(Path(tmp), staged)]
                    for a, b in pairs:
                        if os.path.getsize(long_path(a)) != os.path.getsize(long_path(b)) or _sha256(a) != _sha256(b):
                            raise ConversionError("Copying to the destination drive produced a different file.")
                    continue
                raise
        raise ConversionError("Couldn't find a free file name in the destination folder.")
    finally:
        if staged is not None and os.path.lexists(long_path(staged)):
            try:
                if os.path.isdir(long_path(staged)):
                    shutil.rmtree(long_path(staged), ignore_errors=True)
                else:
                    os.remove(long_path(staged))
            except OSError:
                pass


def commit(tmp: Path, src: Path, stem: str, ext: str, keep_modified_date: bool = True,
           dest: Path | None = None) -> tuple[Path, bool]:
    """Move ``tmp`` (a file or a folder) next to ``src``, or into ``dest`` when given.
    Returns (final_path, used_fallback_folder)."""
    used_fallback = False
    try:
        final = _place(tmp, dest or src.parent, stem, ext)
    except PermissionError:
        final, used_fallback = _place(tmp, fallback_output_dir(), stem, ext), True
    except OSError as e:
        if getattr(e, "winerror", None) in _WRITE_DENIED or e.errno in (errno.EACCES, errno.EROFS):
            final, used_fallback = _place(tmp, fallback_output_dir(), stem, ext), True
        else:
            raise
    if keep_modified_date and not os.path.isdir(long_path(final)):
        try:
            st = os.stat(long_path(src))
            os.utime(long_path(final), ns=(st.st_atime_ns, st.st_mtime_ns))
        except OSError:
            pass
    return final, used_fallback
