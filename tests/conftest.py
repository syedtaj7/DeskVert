"""Keep test runs gentle: the test process and every FFmpeg it starts share a
hard 25% CPU cap (Windows job object), at idle priority in efficiency mode,
with 2 encoder threads. Override the cap with DESKVERT_TEST_CPU=<percent>.

The full every-format-to-every-format matrix only runs with ``--full``.
"""

import os
import tempfile

os.environ.setdefault("DESKVERT_THREADS", "2")
# Never touch the real settings, logs or scratch space: importing the UI loads (and saves) settings.
_home = tempfile.mkdtemp(prefix="deskvert-tests-")
os.environ["APPDATA"] = os.path.join(_home, "Roaming")
os.environ["LOCALAPPDATA"] = os.path.join(_home, "Local")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")  # windows are built and driven, never shown
# Offscreen Qt only knows fonts it's told about; without them, documents Qt lays out (e-mails) have no text.
os.environ.setdefault("QT_QPA_FONTDIR", os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "Fonts"))

from app.lowimpact import cap_this_process  # noqa: E402

cap_this_process(int(os.environ.get("DESKVERT_TEST_CPU", "25")))


# One Qt application for the whole run, created before any test loads the image libraries: starting
# Qt after them aborts the process (seen on CI and locally), and the app itself never does that either.
from PySide6.QtWidgets import QApplication  # noqa: E402

_qt_app = QApplication.instance() or QApplication([])


def pytest_addoption(parser):
    parser.addoption("--full", action="store_true", help="run the complete conversion matrix (heavy)")


def pytest_configure(config):
    config.full_matrix = config.getoption("--full")
