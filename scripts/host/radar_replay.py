#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Replay timestamped raw UART bytes using the actual C safety pipeline.

Usage: python scripts/host/radar_replay.py input.csv [--confirm-frames 3]
CSV schema: timestamp_ms,raw_hex. Timestamps are uint32 decimal milliseconds;
equal times and forward uint32 wrap are allowed, gaps must be <= 2147483647ms.
Hex may be contiguous or space separated; an empty field advances time only.
Blank lines and # comments are allowed. Output is a decision CSV on stdout.
Fixtures under fixtures/radar_safety are SYNTHETIC and are not road evidence.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "app/edge_walker"


def build_replay(destination: Path, confirm_frames: int = 1) -> Path:
    """Build production code, never a Python translation of radar policy."""
    if not 1 <= confirm_frames <= 255:
        raise ValueError("confirm_frames must be between 1 and 255")
    compiler = shutil.which("gcc")
    if compiler is None:
        raise RuntimeError("GCC is required (Windows: add MSYS2 UCRT64 bin to PATH)")
    executable = destination / ("host_replay.exe" if os.name == "nt" else "host_replay")
    subprocess.run([
        compiler, "-std=c99", "-O2", "-Wall", "-Wextra", "-Werror",
        f"-DEW_CONFIRM_FRAMES={confirm_frames}",
        str(SOURCE / "host_replay.c"), str(SOURCE / "ew_ld2451.c"),
        "-o", str(executable), "-lm",
    ], check=True)
    return executable


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("input", help="CSV input path, or - for standard input")
    parser.add_argument("--confirm-frames", type=int, default=1,
                        help="compile-time fresh-frame confirmation count (1..255, default 1)")
    parser.add_argument("--output", type=Path, help="decision CSV path (default: stdout)")
    args = parser.parse_args()
    if not 1 <= args.confirm_frames <= 255:
        parser.error("--confirm-frames must be between 1 and 255")
    compiler = shutil.which("gcc")
    if compiler:
        os.environ["PATH"] = str(Path(compiler).parent) + os.pathsep + os.environ.get("PATH", "")
    try:
        with tempfile.TemporaryDirectory(prefix="ew_radar_replay_") as directory:
            executable = build_replay(Path(directory), args.confirm_frames)
            if args.output:
                # Publish only a successful replay; invalid input must not
                # replace a previous evidence CSV with a partial result.
                destination = args.output.resolve()
                descriptor, name = tempfile.mkstemp(prefix=".ew_replay_", suffix=".csv",
                                                    dir=destination.parent)
                temporary = Path(name)
                try:
                    with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as output:
                        result = subprocess.run([str(executable), args.input], stdout=output)
                    if result.returncode == 0:
                        temporary.replace(destination)
                    return result.returncode
                finally:
                    temporary.unlink(missing_ok=True)
            return subprocess.run([str(executable), args.input]).returncode
    except (OSError, RuntimeError, ValueError, subprocess.CalledProcessError) as exc:
        print(f"radar_replay: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
