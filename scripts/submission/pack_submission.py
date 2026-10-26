#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Assemble contest portal zip (PDF + demo mp4 + photos/)."""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TEAM_SUFFIX = "contest2026_313_bianyuanxingzhe"
MIN_DEMO_SECONDS = 30
MAX_DEMO_SECONDS = 300
SUBMISSION_PHOTOS = (
    "01_正面.jpg",
    "02_接线.jpg",
    "03_运行_SOFT.jpg",
    "04_EW_READY对照.jpg",
)


def material_dir() -> Path:
    hits = list(ROOT.glob("docs/*/*技术报告_V1.0.md"))
    if not hits:
        hits = list(ROOT.glob(f"docs/*/*{TEAM_SUFFIX}.pdf"))
    if not hits:
        raise SystemExit("cannot locate docs submission folder")
    return hits[0].parent


def find_file(mat: Path, name: str) -> Path | None:
    p = mat / name
    return p if p.is_file() else None


def video_duration(path: Path) -> float | None:
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nokey=1:noprint_wrappers=1", str(path)],
            capture_output=True, text=True, check=True,
        )
        return float(result.stdout.strip())
    except (FileNotFoundError, subprocess.CalledProcessError, ValueError):
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Pack contest submission zip")
    parser.add_argument("--out-dir", default="dist")
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()

    mat = material_dir()
    pdf = find_file(mat, f"边缘行者-技术报告-{TEAM_SUFFIX}.pdf")
    mp4 = find_file(mat, f"边缘行者-Demo-{TEAM_SUFFIX}.mp4")
    photos = mat / "photos"

    print("== pack_submission check ==")
    missing: list[str] = []
    for tag, required, label, path in (
        ("P0", True, "tech report PDF", pdf),
        ("P0", True, "demo mp4", mp4),
        ("P1", False, "photos/", photos if photos.is_dir() else None),
    ):
        ok = bool(path and path.exists())
        if label == "photos/" and ok:
            ok = all((photos / name).is_file() for name in SUBMISSION_PHOTOS)
        status = "OK" if ok else "MISSING"
        print(f"[{tag}] {status}  {label}")
        if path:
            print(f"      {path}")
        if not ok and required:
            missing.append(label)

    if mp4:
        duration = video_duration(mp4)
        if duration is None:
            print("[P0] WARN  demo duration not checked (ffprobe unavailable)")
        elif not MIN_DEMO_SECONDS <= duration <= MAX_DEMO_SECONDS:
            print(f"[P0] INVALID demo duration: {duration:.2f}s "
                  f"(expected {MIN_DEMO_SECONDS}-{MAX_DEMO_SECONDS}s)")
            missing.append("valid demo duration")
        else:
            print(f"[P0] OK  demo duration: {duration:.2f}s")

    if args.check_only:
        if missing:
            print(f"\nCheckOnly: still missing P0: {', '.join(missing)}")
            return 2
        print("\nCheck passed (required files present).")
        return 0

    if missing:
        print(f"\nFAIL: missing: {', '.join(missing)}")
        return 1

    out_dir = ROOT / args.out_dir
    staging = out_dir / "submission_staging"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)

    assert pdf and mp4
    shutil.copy2(pdf, staging / pdf.name)
    shutil.copy2(mp4, staging / mp4.name)
    if photos.is_dir():
        photo_out = staging / "photos"
        photo_out.mkdir()
        for name in SUBMISSION_PHOTOS:
            shutil.copy2(photos / name, photo_out / name)

    zip_path = out_dir / f"边缘行者-边缘行者-{TEAM_SUFFIX}.zip"
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for f in staging.rglob("*"):
            if f.is_file():
                zf.write(f, f.relative_to(staging).as_posix())

    print(f"\nWrote {zip_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
