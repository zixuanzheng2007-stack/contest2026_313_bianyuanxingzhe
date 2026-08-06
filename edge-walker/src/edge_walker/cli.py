"""命令行演示：假雷达 → 策略 → Agent Tool。"""

from __future__ import annotations

import argparse
import time

from edge_walker.agent_bridge import AgentBridge
from edge_walker.policy import ApproachPolicy
from edge_walker.protocol import FrameStreamParser, build_detect_frame, split_hex
from edge_walker.simulator import demo_playlist


def run_demo(delay_s: float = 0.15, show_hex: bool = False) -> int:
    policy = ApproachPolicy()
    agent = AgentBridge(proactive=True)
    parser = FrameStreamParser()

    print("=== 边缘行者 · 无板演示 ===")
    print("链路: 假雷达帧 → policy → approach_threshold_exceeded → haptic_alert(mock)\n")

    for targets in demo_playlist():
        raw = build_detect_frame(targets)
        if show_hex:
            print(f"TX {split_hex(raw)}")
        for frame in parser.feed(raw):
            level, event = policy.evaluate(frame.targets)
            if event is None:
                desc = "无有效靠近目标" if not frame.targets else f"过滤后无告警 level={level.value}"
                print(f"[POLICY] {desc}")
            else:
                print(
                    f"[POLICY] {level.value:10} range={event.range_m:5.1f}m "
                    f"speed={event.speed_kmh:5.1f}km/h ttc="
                    f"{'n/a' if event.ttc_s is None else f'{event.ttc_s:.2f}s'}"
                )
                agent.ingest(event)
        time.sleep(delay_s)

    print("\n--- Agent 日志 ---")
    print(agent.dump_jsonl() or "(empty)")
    print(f"\nTool 调用次数: {len(agent.tool_calls)}")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="边缘行者无板演示")
    parser.add_argument("--delay", type=float, default=0.15, help="帧间隔秒")
    parser.add_argument("--hex", action="store_true", help="打印原始帧十六进制")
    args = parser.parse_args()
    raise SystemExit(run_demo(delay_s=args.delay, show_hex=args.hex))


if __name__ == "__main__":
    main()
