"""Regression test for the ignored MiMo bootstrap generator."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "host" / "generate_mimo_bootstrap.py"


def main() -> None:
    secret = "tp-test-bootstrap-key"
    with tempfile.TemporaryDirectory() as tmp:
        output = Path(tmp) / "ew_mimo_bootstrap.h"
        env = os.environ.copy()
        env["EW_TEST_MIMO_KEY"] = secret
        run = subprocess.run(
            [sys.executable, str(SCRIPT), "--env", "EW_TEST_MIMO_KEY",
             "--output", str(output)],
            check=True,
            capture_output=True,
            text=True,
            env=env,
        )
        header = output.read_text(encoding="ascii")
        assert secret in header
        assert secret not in run.stdout
        assert "key redacted" in run.stdout
    print("PASS: MiMo bootstrap generation and log redaction")


if __name__ == "__main__":
    main()
