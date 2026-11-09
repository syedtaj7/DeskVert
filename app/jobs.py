"""Queues conversions and runs them in worker processes.

- Batches run one after another; files within a batch run in parallel.
- Workers run at below-normal priority so the laptop stays responsive.
- The worker pool shuts down after a minute idle, freeing all memory.
- If a damaged file crashes a decoder, only that worker dies: the remaining
  files are retried one at a time and the bad file is reported.
"""

from __future__ import annotations

import logging
import multiprocessing as mp
import queue
import shutil
import threading
import uuid
from concurrent.futures import CancelledError, ProcessPoolExecutor, as_completed
from concurrent.futures.process import BrokenProcessPool
from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtCore import QObject, Signal

from .catalog import Offer
from .paths import work_root
from .settings import Settings
from .worker import estimate_compression, init_worker, progress_file, run_job

log = logging.getLogger(__name__)

POOL_IDLE_SECONDS = 60


@dataclass
class Batch:
    label: str
    jobs: list[dict]
    skipped_same: int = 0
    results: list[dict] = field(default_factory=list)


def build_jobs(offer: Offer, options: dict, settings: Settings) -> list[dict]:
    from .toolbox import output_ext

    t = offer.target

    def job(sources: list[Path], stem: str) -> dict:
        return {
            "id": uuid.uuid4().hex[:12],
            "sources": [str(s) for s in sources],
            "target": t.key,
            "ext": output_ext(t, sources[0], options),
            "out_stem": stem,
            "options": options,
            # Tools that make a modified copy get today's date; plain conversions keep the original's date.
            "keep_modified_date": settings.keep_modified_date and not t.suffix and t.key != "archive.zip",
            "folder": bool(t.folder),
        }

    if t.folder:
        return [job([s], f"{s.stem} ({t.folder})") for s in offer.sources]
    if t.combine:
        first = offer.sources[0]
        stem = first.stem if len(offer.sources) == 1 else f"{first.stem} and {len(offer.sources) - 1} more"
        return [job(offer.sources, stem + t.suffix)]
    suffix = options.get("name_suffix") or t.suffix  # e.g. " (form photo)" for an upload preset
    return [job([s], s.stem + suffix) for s in offer.sources]


class _Relay(QObject):
    done = Signal(object)


class JobManager(QObject):
    started = Signal(str, int)  # label, total files
    progress = Signal(int, int)  # done, total
    file_started = Signal(str, int, int)  # file name, position (1-based), total
    finished = Signal(object)  # Batch

    def __init__(self, settings: Settings):
        super().__init__()
        self.settings = settings
        self._queue: queue.Queue[Batch | None] = queue.Queue()
        self._pool: ProcessPoolExecutor | None = None
        self._pool_lock = threading.Lock()
        self._idle_timer: threading.Timer | None = None
        self._cancel = threading.Event()
        self._busy = threading.Event()
        self._current: tuple[list[str], set[str]] | None = None
        self._relays: set = set()
        self._thread = threading.Thread(target=self._loop, name="jobs", daemon=True)
        self._thread.start()

    @property
    def busy(self) -> bool:
        return self._busy.is_set() or not self._queue.empty()

    def submit(self, offer: Offer, options: dict) -> None:
        jobs = build_jobs(offer, options, self.settings)
        self._queue.put(Batch(offer.target.label, jobs, offer.skipped_same))

    def cancel(self) -> None:
        self._cancel.set()
        try:
            while True:
                self._queue.get_nowait()
        except queue.Empty:
            pass
        self._kill_pool()

    def shutdown(self) -> None:
        self._queue.put(None)
        self._kill_pool()

    def reset_pool(self) -> None:
        """Drop idle workers so the next conversion picks up new settings (CPU limit)."""
        if not self.busy:
            self._kill_pool()

    def estimate(self, path: str, fmt: str, callback) -> None:
        """Measure compression for one image in a worker (capped like any conversion),
        then call ``callback(result_dict)`` on the UI thread."""
        relay = _Relay()
        relay.done.connect(callback)
        self._relays.add(relay)

        def finished(fut):
            try:
                res = fut.result()
            except Exception as e:  # noqa: BLE001
                res = {"ok": False, "error": str(e)}
            relay.done.emit(res)
            self._relays.discard(relay)

        try:
            fut = self._get_pool().submit(estimate_compression, path, fmt)
            fut.add_done_callback(finished)
            self._schedule_idle_shutdown()
        except Exception as e:  # noqa: BLE001
            relay.done.emit({"ok": False, "error": str(e)})

    # ------------------------------------------------------------ internals

    def _loop(self) -> None:
        while True:
            batch = self._queue.get()
            if batch is None:
                return
            self._busy.set()
            self._cancel.clear()
            try:
                self._run(batch)
            except Exception:
                log.exception("batch failed")
            finally:
                self._busy.clear()
                self.finished.emit(batch)
                self._schedule_idle_shutdown()

    def _new_pool(self, workers: int) -> ProcessPoolExecutor:
        return ProcessPoolExecutor(max_workers=workers, mp_context=mp.get_context("spawn"), initializer=init_worker,
                                   initargs=(self.settings.cpu_percent_per_worker,))

    def _get_pool(self) -> ProcessPoolExecutor:
        with self._pool_lock:
            if self._idle_timer:
                self._idle_timer.cancel()
                self._idle_timer = None
            if self._pool is None:
                self._pool = self._new_pool(self.settings.workers)
            return self._pool

    def _schedule_idle_shutdown(self) -> None:
        with self._pool_lock:
            if self._idle_timer:
                self._idle_timer.cancel()
            self._idle_timer = threading.Timer(POOL_IDLE_SECONDS, self._idle_shutdown)
            self._idle_timer.daemon = True
            self._idle_timer.start()

    def _idle_shutdown(self) -> None:
        if not self.busy:
            with self._pool_lock:
                pool, self._pool = self._pool, None
            if pool:
                pool.shutdown(wait=False, cancel_futures=True)
                log.info("worker pool stopped (idle)")

    def _kill_pool(self) -> None:
        with self._pool_lock:
            pool, self._pool = self._pool, None
        if pool:
            for p in list(getattr(pool, "_processes", {}).values()):
                try:
                    p.terminate()
                except Exception:
                    pass
            pool.shutdown(wait=False, cancel_futures=True)

    def _cancelled(self, job: dict) -> dict:
        return {"id": job["id"], "sources": job["sources"], "ok": False, "error": "Cancelled.", "cancelled": True}

    def fraction_done(self) -> float | None:
        """Overall progress of the running batch, 0..1 (includes partial files)."""
        cur = self._current
        if not cur:
            return None
        ids, finished = cur
        total = 0.0
        for jid in ids:
            if jid in finished:
                total += 1
                continue
            try:
                total += float(progress_file(jid).read_text() or 0)
            except (OSError, ValueError):
                pass
        return total / max(1, len(ids))

    def _run(self, batch: Batch) -> None:
        total = len(batch.jobs)
        self.started.emit(batch.label, total)
        done = 0
        crashed: list[dict] = []
        finished: set[str] = set()
        self._current = ([j["id"] for j in batch.jobs], finished)
        try:
            self._run_inner(batch, total, crashed, finished)
        finally:
            self._current = None

    def _run_inner(self, batch: Batch, total: int, crashed: list, finished: set) -> None:
        done = 0
        pool = self._get_pool()
        # Office documents start a whole Office app: one at a time. Images: per settings.
        heavy = any(j["target"].startswith("doc.") for j in batch.jobs)
        window = 1 if heavy else max(1, self.settings.workers)
        pending = list(batch.jobs)
        futures = {}

        def refill():
            while pending and len([f for f in futures if not f.done()]) < window and not self._cancel.is_set():
                j = pending.pop(0)
                started = total - len(pending)
                srcs = j["sources"]
                name = Path(srcs[0]).name if len(srcs) == 1 else f"{len(srcs)} files"
                self.file_started.emit(name, started, total)
                try:
                    futures[pool.submit(run_job, j)] = j
                except (BrokenProcessPool, RuntimeError):
                    crashed.append(j)  # pool died; retried one at a time below

        def completed():
            seen = set()
            while True:
                refill()
                live = [f for f in futures if f not in seen]
                if not live:
                    for j in pending:  # cancelled before they started
                        batch.results.append(self._cancelled(j))
                    pending.clear()
                    return
                f = next(as_completed(live))
                seen.add(f)
                yield f

        for fut in completed():
            job = futures[fut]
            try:
                res = fut.result()
            except (CancelledError, BrokenProcessPool):
                if self._cancel.is_set():
                    res = self._cancelled(job)
                else:
                    crashed.append(job)
                    continue
            finished.add(job["id"])
            batch.results.append(res)
            done += 1
            self.progress.emit(done, total)

        if crashed:
            with self._pool_lock:
                self._pool = None  # the broken pool can't be reused
            for job in crashed:  # one at a time, so a crash points at its file
                if self._cancel.is_set():
                    batch.results.append(self._cancelled(job))
                    continue
                single = self._new_pool(1)
                try:
                    res = single.submit(run_job, job).result()
                except Exception:
                    res = {
                        "id": job["id"], "sources": job["sources"], "ok": False,
                        "error": "The converter crashed while reading this file. It is probably damaged.",
                    }
                finally:
                    single.shutdown(wait=False, cancel_futures=True)
                batch.results.append(res)
                finished.add(job["id"])
                done += 1
                self.progress.emit(done, total)

        if self._cancel.is_set():
            for job in batch.jobs:
                _remove_workdirs(job)
        for r in batch.results:
            if r.get("ok"):
                log.info("converted %s -> %s %s", r["sources"], r["output"], r.get("notes"))
            elif not r.get("cancelled"):
                log.warning("failed %s: %s\n%s", r["sources"], r.get("error"), r.get("detail", ""))


def _remove_workdirs(job: dict) -> None:
    shutil.rmtree(work_root() / job["id"], ignore_errors=True)
    for p in (progress_file(job["id"]), Path(str(progress_file(job["id"])) + ".tmp")):
        try:
            p.unlink()
        except OSError:
            pass
    src = Path(job["sources"][0])
    shutil.rmtree(src.parent / f".tapshift-{job['id']}", ignore_errors=True)


def clean_stale_workdirs() -> None:
    for d in work_root().iterdir():
        if d.is_dir():
            shutil.rmtree(d, ignore_errors=True)
        else:
            try:
                d.unlink()
            except OSError:
                pass
