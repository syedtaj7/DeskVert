"""Folders in a selection, where new files are saved, archives that keep a folder's structure,
and the keyboard-layout check. Light: a few tiny files, one worker call each."""

from __future__ import annotations

import uuid
import zipfile
from pathlib import Path

from PIL import Image

from app import selection, winutil
from app.catalog import offers_for
from app.jobs import build_jobs
from app.settings import SUBFOLDER, Settings
from app.worker import run_job


def _tree(tmp_path: Path) -> Path:
    trip = tmp_path / "Trip"
    (trip / "day 1").mkdir(parents=True)
    (trip / ".git").mkdir()
    for name in ("a.png", "day 1/b.png", "day 1/c.png"):
        Image.new("RGB", (40, 30), "teal").save(trip / name)
    (trip / "desktop.ini").write_text("x")
    (trip / "~$draft.docx").write_text("x")
    (trip / ".git" / "config").write_text("x")
    return trip


def _offer(files, label, settings=None):
    offers, _ = offers_for(files, settings or Settings())
    return next(o for o in offers if o.target.label == label)


def _run(jobs):
    out = []
    for j in jobs:
        j["id"] = uuid.uuid4().hex[:12]
        res = run_job(j)
        assert res["ok"], res.get("error")
        out.append(Path(res["output"]))
    return out


def test_folder_expands_to_its_files(tmp_path):
    trip = _tree(tmp_path)
    loose = tmp_path / "loose.png"
    Image.new("RGB", (10, 10)).save(loose)
    files, roots, cut = selection.expand_selection([trip, loose, loose])
    assert roots == [trip] and not cut
    assert sorted(p.name for p in files) == ["a.png", "b.png", "c.png", "loose.png"]  # no ini, lock or dot files


def test_folder_limit_is_reported(tmp_path):
    trip = _tree(tmp_path)
    files, _roots, cut = selection.expand_selection([trip], limit=2)
    assert len(files) == 2 and cut


def test_empty_folder_gives_nothing(tmp_path):
    (tmp_path / "empty").mkdir()
    assert selection.expand_selection([tmp_path / "empty"]) == ([], [tmp_path / "empty"], False)


def test_converted_files_land_next_to_each_original(tmp_path):
    trip = _tree(tmp_path)
    files, _roots, _ = selection.expand_selection([trip])
    outs = _run(build_jobs(_offer(files, "JPG"), {}, Settings()))
    assert sorted(str(o.relative_to(trip)) for o in outs) == ["a.jpg", "day 1\\b.jpg", "day 1\\c.jpg"]


def test_converted_subfolder_setting(tmp_path):
    trip = _tree(tmp_path)
    s = Settings()
    s.save_to = "subfolder"
    outs = _run(build_jobs(_offer([trip / "a.png"], "JPG", s), {}, s))
    assert outs == [trip / SUBFOLDER / "a.jpg"]


def test_converted_folder_is_not_nested(tmp_path):
    trip = _tree(tmp_path)
    s = Settings()
    s.save_to = "subfolder"
    (first,) = _run(build_jobs(_offer([trip / "a.png"], "JPG", s), {}, s))
    (again,) = _run(build_jobs(_offer([first], "PNG", s), {}, s))
    assert again.parent == trip / SUBFOLDER  # not Converted\Converted


def test_chosen_folder_is_used(tmp_path):
    trip = _tree(tmp_path)
    dest = tmp_path / "elsewhere"
    dest.mkdir()
    outs = _run(build_jobs(_offer([trip / "a.png"], "JPG"), {}, Settings(), str(dest)))
    assert outs == [dest / "a.jpg"]
    assert (trip / "a.png").exists()


def test_zip_keeps_the_folder_structure_and_sits_beside_it(tmp_path):
    trip = _tree(tmp_path)
    files, roots, _ = selection.expand_selection([trip])
    jobs = build_jobs(_offer(files, "ZIP"), {"_roots": [str(r) for r in roots]}, Settings())
    (out,) = _run(jobs)
    assert out == tmp_path / "Trip.zip"
    with zipfile.ZipFile(out) as z:
        assert sorted(z.namelist()) == ["Trip/a.png", "Trip/day 1/b.png", "Trip/day 1/c.png"]


def test_other_archives_keep_the_structure_too(tmp_path):
    trip = _tree(tmp_path)
    files, roots, _ = selection.expand_selection([trip])
    for label, ext in (("7Z", ".7z"), ("TAR.GZ", ".tar.gz")):
        (out,) = _run(build_jobs(_offer(files, label), {"_roots": [str(r) for r in roots]}, Settings()))
        assert out == tmp_path / f"Trip{ext}", label


def test_layout_check_answers_yes_or_no():
    assert winutil.ctrl_shift_switches_layout() in (True, False)


def test_send_to_shortcut_is_made_and_removed(tmp_path):
    link = tmp_path / "SendTo" / "Deskvert.lnk"
    winutil.set_sendto(True, link)
    assert link.exists() and link.stat().st_size > 0
    winutil.set_sendto(False, link)
    assert not link.exists()


def test_settings_carry_over_from_the_old_name(tmp_path, monkeypatch):
    """Tapshift became Deskvert (1.14): its settings move over once, the first time Deskvert starts."""
    from app import paths

    monkeypatch.setenv("APPDATA", str(tmp_path))
    (tmp_path / "Tapshift").mkdir()
    (tmp_path / "Tapshift" / "settings.json").write_text('{"theme": "dark"}', encoding="utf-8")
    folder = paths.config_dir()
    assert folder == tmp_path / "Deskvert"
    assert (folder / "settings.json").read_text(encoding="utf-8") == '{"theme": "dark"}'
    (folder / "settings.json").write_text('{"theme": "light"}', encoding="utf-8")
    assert (paths.config_dir() / "settings.json").read_text(encoding="utf-8") == '{"theme": "light"}'  # once only


def test_web_clips_from_before_the_rename_are_still_clips(tmp_path):
    from app import toolbox

    old = tmp_path / "Clip.html"
    old.write_bytes(b'<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="generator" content="Tapshift web clip">'
                    b'</head><body><p>hello</p></body></html>')
    assert toolbox.is_web_clip(old)


def test_an_installed_copy_is_found_from_windows_record(tmp_path, monkeypatch):
    """No unins000.exe next to Deskvert.exe, but Windows' uninstall record says it was installed here."""
    import sys
    import winreg

    from app import winutil

    app_dir = tmp_path / "Programs" / "Deskvert"
    app_dir.mkdir(parents=True)
    (app_dir / "Deskvert.exe").write_bytes(b"MZ")
    elsewhere = tmp_path / "uninstall" / "unins000.exe"
    elsewhere.parent.mkdir()
    elsewhere.write_bytes(b"MZ")
    record = {"InstallLocation": str(app_dir) + "\\", "UninstallString": f'"{elsewhere}"'}

    class Key:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(app_dir / "Deskvert.exe"))
    monkeypatch.setattr(winreg, "OpenKey", lambda hive, key: Key() if winutil.INSTALLER_ID in key else None)
    monkeypatch.setattr(winreg, "QueryValueEx", lambda k, name: (record[name], 1))
    assert winutil.uninstaller() == elsewhere
    record["InstallLocation"] = str(tmp_path / "somewhere else")  # another copy's record: not this one
    assert winutil.uninstaller() is None
