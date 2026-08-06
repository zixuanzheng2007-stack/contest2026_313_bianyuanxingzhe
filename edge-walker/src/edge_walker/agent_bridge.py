"""Agent 事件桥接（主机侧 mock）。板上将替换为 openvela ai_agent Tool。"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Callable, List, Optional

from .models import AlertLevel, ApproachEvent


HapticFn = Callable[[AlertLevel, ApproachEvent], None]


@dataclass
class ToolResult:
    name: str
    ok: bool
    detail: str


@dataclass
class AgentBridge:
    """
    消费部分二事件：主动触发 → Tool(haptic_alert)。
    无板阶段：Tool 只写日志，不驱动马达。
    """

    proactive: bool = True
    log: List[str] = field(default_factory=list)
    tool_calls: List[ToolResult] = field(default_factory=list)
    on_haptic: Optional[HapticFn] = None

    def ingest(self, event: Optional[ApproachEvent]) -> Optional[ToolResult]:
        if event is None:
            return None
        if event.alert_level == AlertLevel.NONE:
            return None

        line = (
            f"[PROACTIVE] {event.event} level={event.alert_level.value} "
            f"range={event.range_m}m speed={event.speed_kmh}km/h "
            f"ttc={event.ttc_s}"
        )
        self.log.append(line)

        if not self.proactive:
            return None

        return self.call_haptic_alert(event)

    def call_haptic_alert(self, event: ApproachEvent) -> ToolResult:
        detail = (
            f"haptic_alert({event.alert_level.value}) "
            f"range={event.range_m}m"
        )
        if self.on_haptic:
            self.on_haptic(event.alert_level, event)
        else:
            self.log.append(f"[TOOL] {detail} (mock, no motor)")

        result = ToolResult(name="haptic_alert", ok=True, detail=detail)
        self.tool_calls.append(result)
        return result

    def dump_jsonl(self) -> str:
        return "\n".join(self.log)


def format_event_for_skill(event: ApproachEvent) -> str:
    return json.dumps(event.to_dict(), ensure_ascii=False, indent=2)
