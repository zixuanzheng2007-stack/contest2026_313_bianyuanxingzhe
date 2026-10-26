"""Generate the embedded GB2312 LVGL font from a local Source Han Sans TTF."""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path


def gb2312_symbols() -> str:
    chars: set[str] = set()
    for high in range(0xA1, 0xF8):
        for low in range(0xA1, 0xFF):
            try:
                text = bytes((high, low)).decode("gb2312")
            except UnicodeDecodeError:
                continue
            if text and ord(text[0]) >= 0x80:
                chars.add(text[0])
    return "".join(sorted(chars, key=ord))


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser()
    parser.add_argument("font", type=Path)
    parser.add_argument(
        "--output", type=Path,
        default=root / "app" / "edge_walker" / "ew_font_cjk_18.c",
    )
    args = parser.parse_args()
    if not args.font.is_file():
        raise SystemExit(f"font not found: {args.font}")

    symbols = gb2312_symbols()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    command = [
        "npx.cmd", "--yes", "lv_font_conv",
        "--size", "18", "--bpp", "2", "--format", "lvgl",
        "--font", str(args.font), "--range", "0x20-0x7e",
        "--symbols", symbols, "--no-kerning",
        "--no-compress",
        "--lv-font-name", "ew_font_cjk_18",
        "--output", str(args.output),
    ]
    subprocess.run(command, check=True)
    print(f"generated {args.output} ({len(symbols)} GB2312 symbols)")


if __name__ == "__main__":
    main()
