from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Optional


class AlertLevel(str, Enum):
    NONE = "NONE"
    SOFT = "SOFT"
    STRONG = "STRONG"
    EMERGENCY = "EMERGENCY"


@dataclass(frozen=True)
class RadarTarget:
    """端侧策略使用的统一目标结构（与板级解析输出对齐）。"""

    range_m: float
    speed_kmh: float
    approaching: bool
    azimuth_deg: float = 0.0
    snr: int = 0
    alarm: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ApproachEvent:
    """部分二 → 部分三 的事件接口。"""

    event: str
    alert_level: AlertLevel
    range_m: float
    speed_kmh: float
    azimuth_deg: float
    ttc_s: Optional[float]
    timestamp: float
    payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["alert_level"] = self.alert_level.value
        return data
