"""Start File Formatter (runs in the system tray, no console window).

Kept minimal on purpose: worker processes re-import this file, so it must not
import anything heavy at the top level.
"""

import multiprocessing
import sys

if __name__ == "__main__":
    multiprocessing.freeze_support()
    from app.main import main

    sys.exit(main())
