"""Entry point launched by the Claude desktop app."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

for stream in (sys.stdin, sys.stdout, sys.stderr):
    stream.reconfigure(encoding="utf-8")

from connector import server  # noqa: E402

if __name__ == "__main__":
    server.main()
