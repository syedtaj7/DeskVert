"""AutoCAD DWG drawings, through the free ODA File Converter (Open Design Alliance) when it's installed.

DWG is AutoCAD's closed format and no small open library reads it well, so Deskvert asks the converter people
already use for this: ODA File Converter turns the DWG into a DXF (in a private folder), and Deskvert's own
drawing engine takes it from there. Nothing is installed or downloaded by Deskvert itself.
"""

from __future__ import annotations

import glob
import os
import shutil
import subprocess
from pathlib import Path

from ..errors import ConversionError
from ..paths import long_path

GET_IT = "https://www.opendesign.com/guestfiles/oda_file_converter"


def find_oda() -> str | None:
    """ODAFileConverter.exe, if it's installed (DESKVERT_ODA can point at it)."""
    env = os.environ.get("DESKVERT_ODA")
    if env and os.path.isfile(env):
        return env
    found = []
    for base in (os.environ.get("ProgramFiles", ""), os.environ.get("ProgramFiles(x86)", ""),
                 os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs")):
        if base:
            found += glob.glob(os.path.join(base, "ODA", "ODAFileConverter*", "ODAFileConverter.exe"))
    return sorted(found)[-1] if found else None  # the newest version when there are several


def dwg_to_dxf(src: Path, work: Path, timeout: float = 180) -> Path:
    """The drawing as a DXF in ``work`` (ODA File Converter runs hidden, on a copy of the file)."""
    exe = find_oda()
    if exe is None:
        raise ConversionError("DWG drawings need the free ODA File Converter. Install it from opendesign.com and "
                              "Deskvert uses it by itself.")
    inbox, outbox = work / "dwg-in", work / "dwg-out"
    for d in (inbox, outbox):
        shutil.rmtree(d, ignore_errors=True)
        d.mkdir(parents=True)
    copy = inbox / ("drawing" + src.suffix.lower())
    shutil.copyfile(long_path(src), copy)
    # in folder, out folder, version, type, recurse (0), audit and fix (1), files to take
    cmd = [exe, str(inbox), str(outbox), "ACAD2018", "DXF", "0", "1", "*.DWG"]
    try:
        subprocess.run(cmd, timeout=timeout, capture_output=True, creationflags=0x08000000)  # CREATE_NO_WINDOW
    except subprocess.TimeoutExpired as e:
        raise ConversionError("ODA File Converter took too long with this drawing.") from e
    except OSError as e:
        raise ConversionError(f"ODA File Converter couldn't be started ({e}).") from e
    made = sorted(outbox.glob("*.dxf")) + sorted(outbox.glob("*.DXF"))
    if not made or made[0].stat().st_size == 0:
        raise ConversionError("ODA File Converter couldn't read this DWG drawing; it may be damaged or from a "
                              "newer AutoCAD than the converter knows.")
    return made[0]
