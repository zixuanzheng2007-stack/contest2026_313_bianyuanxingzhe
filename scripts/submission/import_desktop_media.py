# -*- coding: utf-8 -*-
"""Import contest-related photos/video from Desktop into docs/提交材料/."""
from __future__ import annotations

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DESKTOP = Path.home() / "Desktop"
PHOTOS = ROOT / "docs" / "提交材料" / "photos"
MAT = ROOT / "docs" / "提交材料"
REPORT_ASSETS = MAT / "archive" / "report_work" / "assets" / "extra"

PRIMARY = [
    ("微信图片_20260908192143_34_40.jpg", "01_正面.jpg"),
    ("微信图片_20260910014806_36_40.jpg", "02_接线.jpg"),
    ("微信图片_20260910014806_36_40.jpg", "03_运行_SOFT.jpg"),
    ("微信图片_20260908192143_34_40.jpg", "04_EW_READY对照.jpg"),
]

EXTRA = [
    ("微信图片_20260910020835_37_40.jpg", "05_WiFi页.jpg"),
    ("微信图片_20260910034734_38_40.jpg", "06_Agent页.jpg"),
    ("微信图片_20260910013212_35_40.jpg", "07_蜂鸣器模块规格.jpg"),
    ("微信图片_20260908173802_32_40.jpg", "08_ESP32模块_正面.jpg"),
    ("微信图片_20260908173803_33_40.jpg", "09_ESP32模块_侧面.jpg"),
    ("SF32LB52x_DevKit-40p-define.png", "10_40pin排针定义.png"),
]

VIDEO = (
    "微信视频2026-09-16_174924_340.mp4",
    "边缘行者-Demo-contest2026_313_bianyuanxingzhe.mp4",
)


def main() -> int:
    PHOTOS.mkdir(parents=True, exist_ok=True)
    REPORT_ASSETS.mkdir(parents=True, exist_ok=True)

    for bad in PHOTOS.glob("*.jpg"):
        if "\ufffd" in bad.name or len(bad.stem) < 3:
            bad.unlink(missing_ok=True)
    for bad in REPORT_ASSETS.glob("*"):
        if bad.is_file() and ("\ufffd" in bad.name):
            bad.unlink(missing_ok=True)

    n = 0
    for src_name, rel in PRIMARY:
        src = DESKTOP / src_name
        dst = PHOTOS / rel
        if not src.is_file():
            print(f"MISSING desktop: {src_name}")
            continue
        shutil.copy2(src, dst)
        print(f"OK  {rel}  <=  {src_name}")
        n += 1

    for src_name, rel in EXTRA:
        src = DESKTOP / src_name
        dst = REPORT_ASSETS / rel
        if not src.is_file():
            print(f"MISSING desktop: {src_name}")
            continue
        shutil.copy2(src, dst)
        print(f"OK  archive/report_work/assets/extra/{rel}  <=  {src_name}")
        n += 1

    vsrc, vdst = VIDEO
    vs = DESKTOP / vsrc
    vd = MAT / vdst
    if vs.is_file():
        shutil.copy2(vs, vd)
        print(f"OK  {vdst}  <=  {vsrc}  ({vs.stat().st_size} B)")
        n += 1
    else:
        print(f"MISSING desktop: {vsrc}")

    print(f"done, {n} files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
