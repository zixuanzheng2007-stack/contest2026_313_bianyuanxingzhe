#!/usr/bin/env python3
"""Run all hardware-free regressions; missing prerequisites are failures."""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent


def run(name: str, command: list[str]) -> bool:
    print(f"\n=== {name} ===", flush=True)
    try:
        result = subprocess.run(command, cwd=ROOT, timeout=180)
    except (OSError, subprocess.TimeoutExpired) as exc:
        print(f"FAIL {name}: {exc}", flush=True)
        return False
    print(f"{'PASS' if result.returncode == 0 else 'FAIL'} {name}", flush=True)
    return result.returncode == 0


def main() -> int:
    missing = []
    if shutil.which("gcc") is None:
        missing.append("GCC (Windows: MSYS2 UCRT64 bin on PATH)")
    for module in ("serial", "tkinter"):
        if importlib.util.find_spec(module) is None:
            missing.append(module)
    if missing:
        print("ENVIRONMENT FAIL: missing " + ", ".join(missing))
        print("Install requirements-test.txt and Python with Tk support; rerun.")
        return 2

    # GCC-generated programs on Windows may depend on DLLs beside gcc.exe.
    os.environ["PATH"] = str(Path(shutil.which("gcc")).parent) + os.pathsep + os.environ.get("PATH", "")
    os.environ["PYTHONUTF8"] = "1"
    results = []
    with tempfile.TemporaryDirectory(prefix="ew_regression_") as directory:
        exe = str(Path(directory) / ("host_smoke.exe" if os.name == "nt" else "host_smoke"))
        source = ROOT / "app/edge_walker"
        built = run("host_smoke build", [
            "gcc", "-std=c99", "-O2", "-Wall", "-Wextra", "-Werror",
            str(source / "host_smoke.c"), str(source / "ew_ld2451.c"), "-o", exe,
        ])
        results.append(built and run("host_smoke", [exe]))
        for script in sorted(HERE.glob("test_*.py")):
            results.append(run(script.name, [sys.executable, str(script)]))
    print(f"\nSUMMARY: {sum(results)}/{len(results)} suites passed")
    return 0 if all(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
