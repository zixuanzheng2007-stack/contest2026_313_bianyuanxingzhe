# -*- coding: utf-8 -*-
"""Trim long idle waits from demo source videos (scene-gap based + mpdecimate).

Usage:
  python scripts/submission/trim_demo_wait.py
  python scripts/submission/trim_demo_wait.py --concat   # also build rough dual-track draft

Outputs under docs/提交材料/archive/demo_work/demo_clips/trimmed/
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

SOURCES = [
    {
        "id": "desktop_1",
        "path": Path(r"D:\Nvidia Screenshots\Desktop\Desktop 2026.09.19 - 00.03.55.01.mp4"),
        "pair": "phone_1",
        "sync_phone_offset": 222.0,  # phone start 00:07:37 - desktop 00:03:55
    },
    {
        "id": "desktop_2",
        "path": Path(r"D:\Nvidia Screenshots\Desktop\Desktop 2026.09.19 - 00.10.18.02.mp4"),
        "pair": "phone_2",
        "sync_phone_offset": 157.0,  # 00:12:55 - 00:10:18
    },
    {
        "id": "phone_1",
        "path": Path(r"C:\Users\15568\Desktop\VID_20260919_000737.mp4"),
        "pair": "desktop_1",
    },
    {
        "id": "phone_2",
        "path": Path(r"C:\Users\15568\Desktop\VID_20260919_001255.mp4"),
        "pair": "desktop_2",
    },
]

SCENE_RE = re.compile(r"pts_time:([0-9.]+)")


def mat_dir() -> Path:
    for d in (ROOT / "docs").iterdir():
        if d.is_dir() and (d / "边缘行者_技术报告_V1.0.md").exists():
            cand = d / "archive" / "demo_work" / "demo_clips"
            cand.mkdir(parents=True, exist_ok=True)
            return cand
    raise SystemExit("docs/提交材料/archive/demo_work/demo_clips not found")


def run(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")


def probe_duration(path: Path) -> float:
    cp = run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ]
    )
    return float(cp.stdout.strip())


def detect_scenes(path: Path, threshold: float = 0.018) -> list[float]:
    cp = run(
        [
            "ffmpeg",
            "-hide_banner",
            "-i",
            str(path),
            "-filter:v",
            f"select='gt(scene,{threshold})',showinfo",
            "-f",
            "null",
            "-",
        ]
    )
    times = [0.0]
    for line in cp.stderr.splitlines():
        m = SCENE_RE.search(line)
        if m:
            times.append(float(m.group(1)))
    dur = probe_duration(path)
    if dur - times[-1] > 0.05:
        times.append(dur)
    return sorted(set(times))


def build_keep_segments(
    scene_times: list[float],
    gap_cut: float = 2.5,
    pad: float = 0.35,
    min_seg: float = 0.4,
) -> list[tuple[float, float]]:
    """Drop gaps longer than gap_cut between scene changes; keep short pauses."""
    if len(scene_times) < 2:
        dur = scene_times[-1] if scene_times else 0.0
        return [(0.0, dur)]

    segments: list[tuple[float, float]] = []
    seg_start = max(0.0, scene_times[0] - pad)
    prev = scene_times[0]

    for t in scene_times[1:]:
        gap = t - prev
        if gap >= gap_cut:
            seg_end = prev + pad
            if seg_end - seg_start >= min_seg:
                segments.append((seg_start, seg_end))
            seg_start = max(0.0, t - pad)
        prev = t

    seg_end = scene_times[-1] + pad
    if seg_end - seg_start >= min_seg:
        segments.append((seg_start, seg_end))

    return merge_nearby(segments, 0.25)


def merge_nearby(segs: list[tuple[float, float]], gap: float) -> list[tuple[float, float]]:
    if not segs:
        return segs
    out = [segs[0]]
    for s, e in segs[1:]:
        ps, pe = out[-1]
        if s - pe <= gap:
            out[-1] = (ps, max(pe, e))
        else:
            out.append((s, e))
    return out


def trim_video(
    src: Path,
    dst: Path,
    gap_cut: float,
    scene_threshold: float,
    max_rate: float | None = None,
) -> dict:
    scenes = detect_scenes(src, scene_threshold)
    segments = build_keep_segments(scenes, gap_cut=gap_cut)
    if not segments:
        segments = [(0.0, probe_duration(src))]

    dst.parent.mkdir(parents=True, exist_ok=True)
    concat_list = dst.with_suffix(".concat.txt")
    part_paths: list[Path] = []

    for i, (start, end) in enumerate(segments):
        part = dst.with_name(f"{dst.stem}_part{i:03d}.mp4")
        dur = end - start
        vf = "setpts=PTS-STARTPTS"
        if max_rate and dur > max_rate:
            # compress ultra-long single segments (e.g. stuck scan)
            speed = min(dur / max_rate, 8.0)
            vf = f"setpts=PTS/{speed:.3f}"

        cmd = [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-ss",
            f"{start:.3f}",
            "-to",
            f"{end:.3f}",
            "-i",
            str(src),
            "-vf",
            vf,
            "-af",
            "aresample=async=1",
            "-c:v",
            "libx264",
            "-preset",
            "fast",
            "-crf",
            "22",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            str(part),
        ]
        subprocess.run(cmd, check=True)
        part_paths.append(part)

    with concat_list.open("w", encoding="utf-8") as f:
        for p in part_paths:
            f.write(f"file '{p.as_posix()}'\n")

    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_list),
            "-c",
            "copy",
            str(dst),
        ],
        check=True,
    )

    for p in part_paths:
        p.unlink(missing_ok=True)
    concat_list.unlink(missing_ok=True)

    orig = probe_duration(src)
    new = probe_duration(dst)
    return {
        "src": str(src),
        "dst": str(dst),
        "orig_s": orig,
        "new_s": new,
        "segments": len(segments),
        "saved_s": orig - new,
    }


def extract_sync_pair(
    desktop_src: Path,
    phone_src: Path,
    work: Path,
    phone_offset: float,
) -> tuple[Path, Path, float]:
    """Cut overlapping window from raw sources before wait-trim (keeps sync)."""
    work.mkdir(parents=True, exist_ok=True)
    d_dur = probe_duration(desktop_src)
    p_dur = probe_duration(phone_src)
    overlap = min(max(0.0, d_dur - phone_offset), p_dur)
    if overlap <= 1.0:
        raise ValueError(f"overlap too short: {overlap:.1f}s")

    d_part = work / f"{desktop_src.stem}_sync.mp4"
    p_part = work / f"{phone_src.stem}_sync.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-ss",
            f"{phone_offset:.3f}",
            "-t",
            f"{overlap:.3f}",
            "-i",
            str(desktop_src),
            "-c",
            "copy",
            str(d_part),
        ],
        check=True,
    )
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-t",
            f"{overlap:.3f}",
            "-i",
            str(phone_src),
            "-c",
            "copy",
            str(p_part),
        ],
        check=True,
    )
    return d_part, p_part, overlap


def side_by_side(desktop: Path, phone: Path, out: Path) -> None:
    """Stack two already-synced trimmed clips."""
    out.parent.mkdir(parents=True, exist_ok=True)
    dur = min(probe_duration(desktop), probe_duration(phone))
    # Same width + fixed height so PC (landscape) and phone (portrait) can hstack.
    box = "960:540"
    fit = (
        f"scale={box}:force_original_aspect_ratio=decrease,"
        f"pad={box}:(ow-iw)/2:(oh-ih)/2:black"
    )
    filter_complex = (
        f"[0:v]trim=duration={dur:.3f},setpts=PTS-STARTPTS,{fit}[left];"
        f"[1:v]trim=duration={dur:.3f},setpts=PTS-STARTPTS,{fit}[right];"
        f"[left][right]hstack=inputs=2[v]"
    )
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(desktop),
            "-i",
            str(phone),
            "-filter_complex",
            filter_complex,
            "-map",
            "[v]",
            "-map",
            "0:a?",
            "-c:v",
            "libx264",
            "-preset",
            "fast",
            "-crf",
            "22",
            "-c:a",
            "aac",
            "-shortest",
            str(out),
        ],
        check=True,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Trim idle waits from demo sources")
    parser.add_argument("--gap-cut", type=float, default=3.5, help="Drop gaps longer than this (s)")
    parser.add_argument("--scene", type=float, default=0.022, help="Scene detect threshold")
    parser.add_argument("--max-seg", type=float, default=15.0, help="Max seconds per kept chunk")
    parser.add_argument("--concat", action="store_true", help="Build side-by-side trimmed pairs")
    args = parser.parse_args()

    out_dir = mat_dir() / "trimmed"
    out_dir.mkdir(parents=True, exist_ok=True)

    trimmed: dict[str, Path] = {}
    print("== trim_demo_wait ==")
    for item in SOURCES:
        src = item["path"]
        if not src.is_file():
            print(f"SKIP missing {src}")
            continue
        dst = out_dir / f"{item['id']}_trimmed.mp4"
        meta = trim_video(src, dst, args.gap_cut, args.scene, args.max_seg)
        trimmed[item["id"]] = dst
        print(
            f"OK {item['id']}: {meta['orig_s']:.1f}s -> {meta['new_s']:.1f}s "
            f"(-{meta['saved_s']:.1f}s, {meta['segments']} segs)"
        )

    if args.concat:
        src_map = {s["id"]: s for s in SOURCES}
        pairs = [
            ("desktop_1", "phone_1", 222.0, "pair1_agent_or_mix.mp4"),
            ("desktop_2", "phone_2", 157.0, "pair2_wifi.mp4"),
        ]
        sync_dir = out_dir / "sync_raw"
        for d_id, p_id, off, name in pairs:
            ds, ps = src_map.get(d_id), src_map.get(p_id)
            if not ds or not ps or not ds["path"].is_file() or not ps["path"].is_file():
                continue
            try:
                d_sync, p_sync, ov = extract_sync_pair(
                    ds["path"], ps["path"], sync_dir, off
                )
                d_trim = out_dir / f"{d_id}_sync_trimmed.mp4"
                p_trim = out_dir / f"{p_id}_sync_trimmed.mp4"
                trim_video(d_sync, d_trim, args.gap_cut, args.scene, args.max_seg)
                trim_video(p_sync, p_trim, args.gap_cut, args.scene, args.max_seg)
                side_by_side(d_trim, p_trim, out_dir / name)
                print(
                    f"OK pair {name}: raw overlap {ov:.1f}s -> "
                    f"d {probe_duration(d_trim):.1f}s p {probe_duration(p_trim):.1f}s"
                )
            except (ValueError, subprocess.CalledProcessError) as exc:
                print(f"WARN pair {name}: {exc}")

    readme = out_dir / "README.md"
    readme.write_text(
        f"""# Demo 素材 · 已剪等待

由 `python scripts/submission/trim_demo_wait.py` 生成。

- **gap_cut** = {args.gap_cut}s：场景静止超过该时长则整段跳过
- **max_seg** = {args.max_seg}s：单段仍过长则加速压缩

## 文件

| 文件 | 说明 |
|------|------|
| `desktop_1_trimmed.mp4` | PC 录屏 #1（去等待） |
| `desktop_2_trimmed.mp4` | PC 录屏 #2 |
| `phone_1_trimmed.mp4` | 手机 #1 |
| `phone_2_trimmed.mp4` | 手机 #2 |
| `pair1_agent_or_mix.mp4` | 左右对照（需 --concat） |
| `pair2_wifi.mp4` | WiFi 段对照 |

## 下一步

用 trimmed 文件在剪映里微调，合成 ≤5min 成片：
`docs/提交材料/边缘行者-Demo-contest2026_313_bianyuanxingzhe.mp4`
""",
        encoding="utf-8",
    )
    print(f"Wrote {readme}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
