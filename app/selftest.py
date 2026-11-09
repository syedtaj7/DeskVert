"""`Tapshift.exe --selftest <folder>`: runs real conversions through the same
worker processes the app uses, and writes selftest.json into <folder>.
Used to check a built release (everything bundled, workers start, engines work)."""

from __future__ import annotations

import json
import multiprocessing as mp
import sys
import time
import uuid
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path


def run(folder: Path) -> int:
    from PySide6.QtGui import QGuiApplication

    from .catalog import offers_for
    from .jobs import build_jobs
    from .main import make_samples
    from .settings import Settings
    from .worker import init_worker, run_job

    _app = QGuiApplication.instance() or QGuiApplication(sys.argv[:1])  # noqa: F841
    folder.mkdir(parents=True, exist_ok=True)
    samples = make_samples(folder / "samples")
    s = Settings()
    plan = [("Sunset.png", "JPG"), ("Sunset.png", "WEBP"), ("Sunset.png", "HEIC"), ("Mountains.jpg", "PDF"),
            ("Mountains.jpg", "ICO")]
    from .catalog import office_installed

    if office_installed("word"):
        plan.append(("Meeting notes.txt", "PDF"))  # Microsoft Word, through COM automation
    results = []
    t0 = time.perf_counter()
    with ProcessPoolExecutor(max_workers=1, mp_context=mp.get_context("spawn"), initializer=init_worker,
                             initargs=(25,)) as pool:
        for name, label in plan:
            offers, _ = offers_for([samples / name], s)
            offer = next((o for o in offers if o.target.label == label), None)
            if offer is None:
                results.append({"case": f"{name}->{label}", "ok": False, "error": "not offered"})
                continue
            job = build_jobs(offer, {o.key: o.default for o in offer.options}, s)[0]
            job["id"] = uuid.uuid4().hex[:12]
            r = pool.submit(run_job, job).result(timeout=300)
            results.append({"case": f"{name}->{label}", "ok": r.get("ok"), "output": r.get("output"),
                            "error": r.get("error"), "notes": r.get("notes")})
        # PDF tools on the PDF we just made
        pdf = next((Path(r["output"]) for r in results if r["case"] == "Mountains.jpg->PDF" and r["ok"]), None)
        if pdf:
            offers, _ = offers_for([pdf], s)
            for label in ("PNG", "Split"):
                offer = next(o for o in offers if o.target.label == label)
                job = build_jobs(offer, {}, s)[0]
                r = pool.submit(run_job, job).result(timeout=300)
                results.append({"case": f"pdf->{label}", "ok": r.get("ok"), "output": r.get("output"),
                                "error": r.get("error")})
    report = {"ok": all(r["ok"] for r in results), "seconds": round(time.perf_counter() - t0, 1),
              "frozen": bool(getattr(sys, "frozen", False)), "results": results}
    (folder / "selftest.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return 0 if report["ok"] else 1
