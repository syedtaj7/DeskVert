"""Run any command under Deskvert's hard CPU cap (Windows job object), so heavy
tasks like building the release don't slow the laptop down.
Usage: python tools/capped.py <percent> <command...>"""

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.lowimpact import cap_this_process  # noqa: E402

percent = int(sys.argv[1])
cap_this_process(percent)
sys.exit(subprocess.call(sys.argv[2:]))
