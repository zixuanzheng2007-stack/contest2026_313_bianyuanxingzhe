"""端侧接近策略：过滤 + 粗 TTC + 告警等级。禁止调用 LLM。"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional, Sequence, Tuple

from .models import AlertLevel, ApproachEvent, RadarTarget


@dataclass
class PolicyConfig:
    max_range_m: float = 40.0
    min_speed_kmh: float = 5.0
    min_snr: int = 4
    soft_range_m: float = 25.0
    strong_range_m: float = 15.0
    emergency_range_m: float = 8.0
    soft_ttc_s: float = 5.0
    strong_ttc_s: float = 3.0
    emergency_ttc_s: float = 1.5
    approaching_only: bool = True


def compute_ttc_s(target: RadarTarget) -> Optional[float]:
    if not target.approaching or target.speed_kmh <= 0:
        return None
    speed_mps = target.speed_kmh / 3.6
    if speed_mps <= 0:
        return None
    return target.range_m / speed_mps


def passes_filter(target: RadarTarget, cfg: PolicyConfig) -> bool:
    if cfg.approaching_only and not target.approaching:
        return False
    if target.range_m > cfg.max_range_m:
        return False
    if target.speed_kmh < cfg.min_speed_kmh:
        return False
    if target.snr and target.snr < cfg.min_snr:
        return False
    return True


def level_from_range_and_ttc(
    range_m: float, ttc_s: Optional[float], cfg: PolicyConfig
) -> AlertLevel:
    by_range = AlertLevel.NONE
    if range_m <= cfg.emergency_range_m:
        by_range = AlertLevel.EMERGENCY
    elif range_m <= cfg.strong_range_m:
        by_range = AlertLevel.STRONG
    elif range_m <= cfg.soft_range_m:
        by_range = AlertLevel.SOFT

    by_ttc = AlertLevel.NONE
    if ttc_s is not None:
        if ttc_s <= cfg.emergency_ttc_s:
            by_ttc = AlertLevel.EMERGENCY
        elif ttc_s <= cfg.strong_ttc_s:
            by_ttc = AlertLevel.STRONG
        elif ttc_s <= cfg.soft_ttc_s:
            by_ttc = AlertLevel.SOFT

    order = {
        AlertLevel.NONE: 0,
        AlertLevel.SOFT: 1,
        AlertLevel.STRONG: 2,
        AlertLevel.EMERGENCY: 3,
    }
    return by_range if order[by_range] >= order[by_ttc] else by_ttc


class ApproachPolicy:
    def __init__(self, config: Optional[PolicyConfig] = None) -> None:
        self.config = config or PolicyConfig()
        self._last_level = AlertLevel.NONE

    def evaluate(
        self, targets: Sequence[RadarTarget], timestamp: Optional[float] = None
    ) -> Tuple[AlertLevel, Optional[ApproachEvent]]:
        ts = time.time() if timestamp is None else timestamp
        cfg = self.config
        candidates = [t for t in targets if passes_filter(t, cfg)]
        if not candidates:
            self._last_level = AlertLevel.NONE
            return AlertLevel.NONE, None

        primary = min(candidates, key=lambda t: t.range_m)
        ttc = compute_ttc_s(primary)
        level = level_from_range_and_ttc(primary.range_m, ttc, cfg)
        self._last_level = level

        if level == AlertLevel.NONE:
            return level, None

        event = ApproachEvent(
            event="approach_threshold_exceeded",
            alert_level=level,
            range_m=primary.range_m,
            speed_kmh=primary.speed_kmh,
            azimuth_deg=primary.azimuth_deg,
            ttc_s=ttc,
            timestamp=ts,
            payload={"snr": primary.snr},
        )
        return level, event

    @property
    def last_level(self) -> AlertLevel:
        return self._last_level
