#!/usr/bin/env python3
"""Generate the ignored MiMo bootstrap header without printing the key."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

try:
    import winreg
except ImportError:
    winreg = None  # type: ignore


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = ROOT / "app" / "edge_walker" / "ew_mimo_bootstrap.h"


def read_secret(name: str) -> str:
    value = os.environ.get(name, "")
    if value or winreg is None:
        return value
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
            value, _ = winreg.QueryValueEx(key, name)
            return str(value)
    except OSError:
        return ""


def validate_key(value: str) -> None:
    if not value.startswith("tp-"):
        raise ValueError("MIMO_API_KEY must start with tp-")
    if len(value) >= 160:
        raise ValueError("MIMO_API_KEY must be shorter than 160 characters")
    if any(ch.isspace() or ord(ch) < 0x20 or ord(ch) > 0x7E for ch in value):
        raise ValueError("MIMO_API_KEY must contain printable ASCII without spaces")


def write_header(output: Path, key: str) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    temp = output.with_suffix(output.suffix + ".tmp")
    quoted = json.dumps(key, ensure_ascii=True)
    temp.write_text(
        "/* Generated from Host MIMO_API_KEY. Git-ignored; do not log. */\n"
        "#ifndef EDGE_WALKER_EW_MIMO_BOOTSTRAP_H\n"
        "#define EDGE_WALKER_EW_MIMO_BOOTSTRAP_H\n"
        f"#define EW_MIMO_BOOTSTRAP_KEY {quoted}\n"
        "#endif\n",
        encoding="ascii",
        newline="\n",
    )
    temp.replace(output)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--env", default="MIMO_API_KEY")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    key = read_secret(args.env)
    try:
        validate_key(key)
    except ValueError as exc:
        print(f"ERROR: {exc}")
        return 2
    output = args.output.resolve()
    write_header(output, key)
    print(f"MiMo bootstrap generated: {output} (key redacted, length={len(key)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
