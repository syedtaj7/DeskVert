"""Keep test runs gentle: the test process and every FFmpeg it starts share a
hard 25% CPU cap (Windows job object), at idle priority in efficiency mode,
with 2 encoder threads. Override the cap with TAPSHIFT_TEST_CPU=<percent>.

The full every-format-to-every-format matrix only runs with ``--full``.
"""

import os

os.environ.setdefault("TAPSHIFT_THREADS", "2")

from app.lowimpact import cap_this_process  # noqa: E402

cap_this_process(int(os.environ.get("TAPSHIFT_TEST_CPU", "25")))


def pytest_addoption(parser):
    parser.addoption("--full", action="store_true", help="run the complete conversion matrix (heavy)")


def pytest_configure(config):
    config.full_matrix = config.getoption("--full")
