#!/usr/bin/env python3
"""Fail fast when the reproducible embedded CJK font setup is incomplete."""

from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[2]
FONT = ROOT / "app" / "edge_walker" / "ew_font_cjk_18.c"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"FAIL: {message}")


def main() -> None:
    require(FONT.is_file(), "embedded CJK font is missing")
    require(FONT.stat().st_size > 1_000_000, "embedded CJK font looks truncated")
    font_text = FONT.read_text(encoding="utf-8", errors="ignore")
    require("ew_font_cjk_18" in font_text, "unexpected LVGL font symbol")
    require("SourceHanSansCN-Bold.ttf" in font_text, "font provenance is missing")

    cmake = (ROOT / "app" / "edge_walker" / "CMakeLists.txt").read_text()
    makefile = (ROOT / "app" / "edge_walker" / "Makefile").read_text()
    notice = (ROOT / "NOTICE").read_text(encoding="utf-8")
    license_file = ROOT / "THIRD_PARTY_LICENSES" / "SourceHanSans-OFL-1.1.txt"
    require("ew_font_cjk_18.c" in cmake and "ew_font_cjk_18.c" in makefile,
            "embedded font is not in both build systems")
    require("Source Han Sans" in notice and "Open Font License" in notice,
            "NOTICE lacks font attribution/license")
    require(license_file.is_file() and "SIL OPEN FONT LICENSE" in
            license_file.read_text(encoding="utf-8"),
            "full Source Han Sans OFL license is missing")

    tracked = subprocess.run(
        ["git", "ls-files", "--error-unmatch", FONT.relative_to(ROOT).as_posix()],
        cwd=ROOT, capture_output=True, check=False,
    )
    require(tracked.returncode == 0,
            "embedded font is not tracked by Git; add it before submission")

    font_files = subprocess.run(
        ["git", "ls-files", "*.ttf", "*.otf"], cwd=ROOT,
        capture_output=True, text=True, check=True,
    ).stdout.splitlines()
    require(not font_files, f"runtime font binaries must not be committed: {font_files}")
    print("PASS: embedded font is present, attributed, tracked, and build-linked")


if __name__ == "__main__":
    main()
