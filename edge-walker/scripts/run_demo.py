#!/usr/bin/env python3
"""无板全链路演示入口。"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from edge_walker.cli import main

if __name__ == "__main__":
    main()
