"""Runs one conversion. Executed in a separate worker process so heavy
libraries never stay loaded in the tray app, and a damaged file that crashes a
decoder can't take the app down with it."""

from __future__ import annotations

import importlib
import os
import shutil
import traceback
from pathlib import Path

from .errors import ConversionError, VerificationError, friendly
from .paths import long_path
from .safe_write import commit, make_workdir


def init_worker(cpu_percent: int = 25) -> None:
    """Runs once in each worker process: hard CPU cap (shared with every
    engine it starts), idle priority, efficiency mode, kill-on-exit."""
    from .lowimpact import cap_this_process

    try:
        cap_this_process(cpu_percent)
    except Exception:
        pass


def estimate_compression(path: str, fmt: str) -> dict:
    """Preview for the Compress panel: size and quality for each size limit."""
    try:
        from .engines.compress import estimate

        return estimate(Path(path), fmt)
    except BaseException as e:  # noqa: BLE001
        return {"ok": False, "error": friendly(e)}


def progress_file(job_id: str) -> Path:
    from .paths import work_root

    return work_root() / f"{job_id}.progress"


def run_job(job: dict) -> dict:
    """job = {id, sources[], target, ext, out_stem, options{}, keep_modified_date}"""
    sources = [Path(p) for p in job["sources"]]
    engine_name, fmt = job["target"].split(".", 1)
    result = {"id": job["id"], "sources": job["sources"], "ok": False, "notes": []}
    workdir = None
    try:
        for s in sources:
            if not os.path.isfile(long_path(s)):
                raise ConversionError(f"{s.name} no longer exists.")
        dest = Path(job["dest"]) if job.get("dest") else sources[0].parent
        try:
            os.makedirs(long_path(dest), exist_ok=True)  # e.g. the "Converted" folder
        except OSError:
            dest = sources[0].parent
        workdir = make_workdir(dest, job["id"])
        folder_out = bool(job.get("folder"))  # e.g. one image per page, in a new folder
        tmp = workdir / ("output" if folder_out else f"output{job['ext']}")
        engine = importlib.import_module(f"app.engines.{engine_name}")
        opts = dict(job.get("options") or {})
        opts["_progress_file"] = str(progress_file(job["id"]))
        notes = engine.convert(sources, tmp, fmt, opts)
        if folder_out:
            if not tmp.is_dir() or not any(tmp.iterdir()):
                raise VerificationError("no files were produced")
        elif not tmp.exists() or tmp.stat().st_size == 0:
            raise VerificationError("the output file is empty")
        final, fallback = commit(tmp, sources[0], job["out_stem"], "" if folder_out else job["ext"],
                                 job.get("keep_modified_date", True), dest)
        if fallback:
            notes.append(f"The folder couldn't be written to, so it was saved in {final.parent}.")
        result.update(ok=True, output=str(final), notes=notes)
    except BaseException as e:  # noqa: BLE001 - every failure must reach the user
        result.update(error=friendly(e), detail=traceback.format_exc())
    finally:
        if workdir is not None:
            shutil.rmtree(long_path(workdir), ignore_errors=True)
        for p in (progress_file(job["id"]), Path(str(progress_file(job["id"])) + ".tmp")):
            try:
                p.unlink()
            except OSError:
                pass
    return result
