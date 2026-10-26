"""Compile and run the pure Stage 2 network fault-classification smoke test."""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "app" / "edge_walker"


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="ew_stage2_") as directory:
        executable = Path(directory) / "stage2_smoke"
        subprocess.run(
            [
                "gcc",
                "-std=c99",
                "-Wall",
                "-Wextra",
                "-Werror",
                "-I",
                str(SOURCE),
                str(SOURCE / "stage2_smoke.c"),
                str(SOURCE / "ew_net_status.c"),
                "-o",
                str(executable),
            ],
            check=True,
        )
        subprocess.run([str(executable)], check=True)


if __name__ == "__main__":
    main()
