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


def _make_extras(folder: Path) -> dict[str, Path]:
    """Small files for the everyday tools: a CSV, JSON, Markdown and a picture of text."""
    from PySide6.QtGui import QColor, QFont, QImage, QPainter

    files = {"csv": folder / "Prices.csv", "json": folder / "Settings.json", "md": folder / "Read me.md",
             "scan": folder / "Receipt.png"}
    files["csv"].write_text("item,qty,price\nApple,3,1.20\nPear,10,0.8\n", encoding="utf-8")
    files["json"].write_text('{"name":"Tapshift","tools":["zip","ocr"],"ratio":1.10}', encoding="utf-8")
    files["md"].write_text("# Read me\n\nA **short** document with a list:\n\n- one\n- two\n", encoding="utf-8")
    img = QImage(1400, 500, QImage.Format.Format_RGB32)
    img.fill(QColor("white"))
    p = QPainter(img)
    p.setPen(QColor("black"))
    p.setFont(QFont("Arial", 40))
    for i, line in enumerate(("Corner Bakery receipt", "Two coffees and one croissant", "Total paid 9.40")):
        p.drawText(60, 120 + i * 120, line)
    p.end()
    img.save(str(files["scan"]))
    return files


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
    extras = _make_extras(folder / "samples")
    results = []
    t0 = time.perf_counter()
    with ProcessPoolExecutor(max_workers=1, mp_context=mp.get_context("spawn"), initializer=init_worker,
                             initargs=(25,)) as pool:

        def case(files: list[Path], label: str, options: dict | None = None, name: str = "") -> Path | None:
            name = name or f"{files[0].name}->{label}"
            offers, _ = offers_for(files, s)
            offer = next((o for o in offers if o.target.label == label), None)
            if offer is None:
                results.append({"case": name, "ok": False, "error": "not offered"})
                return None
            opts = {o.key: o.default for o in offer.options}
            opts.update(options or {})
            job = build_jobs(offer, opts, s)[0]
            job["id"] = uuid.uuid4().hex[:12]
            r = pool.submit(run_job, job).result(timeout=300)
            results.append({"case": name, "ok": r.get("ok"), "output": r.get("output"),
                            "error": r.get("error"), "notes": r.get("notes")})
            return Path(r["output"]) if r.get("ok") else None

        for name, label in plan:
            case([samples / name], label)
        case([samples / "Mountains.jpg"], "Compress", {"format": "JPG", "mode": "size", "target_kb": 50})
        # PDF tools on the PDF we just made
        pdf = next((Path(r["output"]) for r in results if r["case"] == "Mountains.jpg->PDF" and r["ok"]), None)
        if pdf:
            for label in ("PNG", "Split"):
                case([pdf], label, name=f"pdf->{label}")
            case([pdf], "Numbers", name="pdf->Numbers")
            locked = case([pdf], "Lock", {"password": "selftest"}, name="pdf->Lock")
            if locked:
                case([locked], "Unlock", {"password": "selftest"}, name="pdf->Unlock")
        # Zip and extract, data, Markdown, text recognition
        zipped = case([samples / "Sunset.png", samples / "Mountains.jpg"], "ZIP", name="2 images->ZIP")
        if zipped:
            case([zipped], "Extract", name="zip->Extract")
        case([extras["csv"]], "XLSX")
        case([extras["json"]], "Tidy")
        case([extras["md"]], "PDF")
        case([extras["scan"]], "Read text")
    report = {"ok": all(r["ok"] for r in results), "seconds": round(time.perf_counter() - t0, 1),
              "frozen": bool(getattr(sys, "frozen", False)), "results": results}
    (folder / "selftest.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return 0 if report["ok"] else 1
