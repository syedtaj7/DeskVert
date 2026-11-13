"""Report a problem: nothing personal in what's shown, and a GitHub link that always works."""

from __future__ import annotations

import os
import urllib.parse

from app import report


def test_names_folders_and_files_are_hidden(monkeypatch):
    home = os.path.expanduser("~")
    user = os.path.basename(home)
    line = (rf"converted ['{home}\Documents\Bank statement March.pdf'] -> {home}\Documents\Converted\x.docx "
            f"by {user}, mail me at someone@example.com")
    out = report.scrub(line)
    assert home.lower() not in out.lower() and "Bank statement" not in out and "someone@example.com" not in out
    assert "%USERPROFILE%" in out and "<file>.pdf" in out and "<file>.docx" in out
    if len(user) >= 3:
        assert user.lower() not in out.lower()


def test_issue_link_is_filled_in_and_never_too_long(tmp_path, monkeypatch):
    log = tmp_path / "app.log"
    log.write_text("\n".join(f"2026-11-13 10:00:{i:02d} INFO tapshift: step {i} " + "x" * 200 for i in range(60)),
                   encoding="utf-8")
    monkeypatch.setattr(report, "log_dir", lambda: tmp_path)
    body = report.issue_body("Word files fail to convert.")
    assert "Word files fail" in body and "Tapshift" in body and "step 59" in body
    url = report.issue_url("Word to PDF fails", body)
    assert url.startswith("https://github.com/") and "/issues/new?" in url and len(url) <= report.MAX_URL
    q = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
    assert q["title"] == ["Word to PDF fails"]
    assert "Word files fail to convert." in q["body"][0] and "step 59" in q["body"][0]  # the newest lines stay
    without = report.issue_body("x", include_log=False)
    assert "Recent log" not in without


def test_report_window_shows_what_will_be_shared(monkeypatch, tmp_path):
    from PySide6.QtWidgets import QApplication

    monkeypatch.setattr(report, "log_dir", lambda: tmp_path)
    QApplication.instance() or QApplication([])
    from app.ui.report import ReportWindow

    w = ReportWindow("Couldn't convert: the file is damaged")
    assert "the file is damaged" in w.preview.toPlainText()
    w.with_log.setChecked(False)
    assert "Recent log" not in w.preview.toPlainText()
    w.close()
