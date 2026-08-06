"""接近场景假数据发生器（无板）。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator, List, Sequence

from .models import RadarTarget
from .protocol import build_detect_frame


@dataclass
class ApproachScenario:
    """电自从远处靠近的直线场景。"""

    start_range_m: float = 40.0
    end_range_m: float = 5.0
    speed_kmh: float = 25.0
    step_m: float = 2.0
    azimuth_deg: float = 0.0
    snr: int = 20

    def targets_over_time(self) -> List[RadarTarget]:
        frames: List[RadarTarget] = []
        r = self.start_range_m
        while r >= self.end_range_m - 1e-6:
            frames.append(
                RadarTarget(
                    range_m=round(r, 1),
                    speed_kmh=self.speed_kmh,
                    approaching=True,
                    azimuth_deg=self.azimuth_deg,
                    snr=self.snr,
                    alarm=True,
                )
            )
            r -= self.step_m
        return frames


def receding_noise(range_m: float = 20.0, speed_kmh: float = 15.0) -> RadarTarget:
    """远离目标：策略应过滤。"""
    return RadarTarget(
        range_m=range_m,
        speed_kmh=speed_kmh,
        approaching=False,
        azimuth_deg=5.0,
        snr=18,
        alarm=False,
    )


def slow_target(range_m: float = 12.0, speed_kmh: float = 3.0) -> RadarTarget:
    """低于最小速度：策略应过滤。"""
    return RadarTarget(
        range_m=range_m,
        speed_kmh=speed_kmh,
        approaching=True,
        azimuth_deg=-3.0,
        snr=16,
        alarm=True,
    )


def iter_binary_stream(targets: Sequence[RadarTarget]) -> Iterator[bytes]:
    for t in targets:
        yield build_detect_frame([t])


def demo_playlist() -> List[Sequence[RadarTarget]]:
    """演示用混合序列：噪声 → 接近升级。"""
    playlist: List[Sequence[RadarTarget]] = [
        [receding_noise()],
        [slow_target()],
        [],
    ]
    for t in ApproachScenario().targets_over_time():
        playlist.append([t])
    return playlist
