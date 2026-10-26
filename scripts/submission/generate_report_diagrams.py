# -*- coding: utf-8 -*-
"""Generate architecture / flow diagrams for technical report PDF."""
from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

ROOT = Path(__file__).resolve().parents[2]


def material_dir() -> Path:
    for d in (ROOT / "docs").iterdir():
        if d.is_dir() and (d / "边缘行者_技术报告_V1.0.md").exists():
            out = d / "archive" / "report_work" / "assets" / "diagrams"
            out.mkdir(parents=True, exist_ok=True)
            return out
    raise SystemExit("docs/提交材料 not found")


def setup_cn() -> None:
    plt.rcParams.update(
        {
            "font.sans-serif": ["Microsoft YaHei", "SimHei", "SimSun", "DejaVu Sans"],
            "axes.unicode_minus": False,
            "figure.dpi": 150,
        }
    )


def box(ax, x, y, w, h, text, fc="#E8F4FD", ec="#2B579A", fs=9):
    patch = FancyBboxPatch(
        (x, y),
        w,
        h,
        boxstyle="round,pad=0.02,rounding_size=0.08",
        linewidth=1.2,
        edgecolor=ec,
        facecolor=fc,
    )
    ax.add_patch(patch)
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=fs, wrap=True)


def arrow(ax, x1, y1, x2, y2, color="#444444"):
    ax.add_patch(
        FancyArrowPatch(
            (x1, y1),
            (x2, y2),
            arrowstyle="-|>",
            mutation_scale=12,
            linewidth=1.2,
            color=color,
            shrinkA=4,
            shrinkB=4,
        )
    )


def save(fig, path: Path) -> None:
    fig.savefig(path, bbox_inches="tight", facecolor="white", pad_inches=0.15)
    plt.close(fig)
    print(f"OK {path.name} ({path.stat().st_size // 1024} KB)")


def draw_system_arch(out: Path) -> None:
    fig, ax = plt.subplots(figsize=(10.5, 7.6))
    ax.set_xlim(0, 10.5)
    ax.set_ylim(0, 7.6)
    ax.axis("off")
    ax.set_title("图 3-11  系统总体架构流程图", fontsize=13, fontweight="bold", pad=12)

    # Left: radar / alert path
    ax.text(2.5, 7.15, "本地安全环（断网可用）", ha="center", fontsize=10, color="#C0392B", fontweight="bold")
    box(ax, 1.6, 6.3, 1.8, 0.55, "LD2451\nUART2 / ttyS1", fc="#FDEBD0", ec="#D35400")
    arrow(ax, 2.5, 6.3, 2.5, 6.02)
    box(ax, 1.5, 5.35, 2.0, 0.55, "ew_ld2451 解析", fc="#FDEBD0", ec="#D35400")
    arrow(ax, 2.5, 5.35, 2.5, 5.07)
    box(ax, 1.4, 4.4, 2.2, 0.55, "ew_decide 门限", fc="#FDEBD0", ec="#D35400")
    arrow(ax, 2.5, 4.4, 2.5, 4.12)
    box(ax, 0.9, 3.25, 3.2, 0.72, "NONE / SOFT / STRONG / EMERGENCY", fc="#FADBD8", ec="#C0392B", fs=8)
    arrow(ax, 2.5, 3.25, 2.5, 2.87)
    box(ax, 1.2, 2.05, 2.6, 0.62, "alert_output()", fc="#F5B7B1", ec="#C0392B")
    box(ax, 0.45, 0.6, 1.9, 0.9, "PA28 蜂鸣器\n2300/2500/2700 Hz", fc="#FADBD8", ec="#C0392B", fs=8)
    box(ax, 2.75, 0.6, 1.9, 0.9, "LVGL 预警页\n分档变色", fc="#FADBD8", ec="#C0392B", fs=8)
    arrow(ax, 2.5, 2.05, 1.4, 1.5)
    arrow(ax, 2.5, 2.05, 3.7, 1.5)

    # Skill branch: keep a separate vertical lane and merge into alert_output.
    box(ax, 4.55, 3.25, 2.25, 0.55, "Skill: approach-warn", fc="#E8DAEF", ec="#7D3C98", fs=8)
    box(ax, 4.55, 2.35, 2.25, 0.55, "ew_agent_proactive_alert", fc="#E8DAEF", ec="#7D3C98", fs=8)
    box(ax, 4.7, 1.45, 1.95, 0.55, "Tool: approach_alert", fc="#E8DAEF", ec="#7D3C98", fs=8)
    arrow(ax, 4.1, 3.61, 4.55, 3.52)
    arrow(ax, 5.68, 3.25, 5.68, 2.9)
    arrow(ax, 5.68, 2.35, 5.68, 2.0)
    arrow(ax, 4.7, 1.72, 3.8, 2.36)

    # Right: network / agent path
    ax.text(8.2, 7.15, "联网交互（可选）", ha="center", fontsize=10, color="#1F618D", fontweight="bold")
    box(ax, 7.0, 6.3, 2.4, 0.55, "ESP32 AT 模组\nUART3 PA24/PA25", fc="#D6EAF8", ec="#1F618D", fs=8)
    arrow(ax, 8.2, 6.3, 8.2, 6.02)
    box(ax, 7.2, 5.35, 2.0, 0.55, "ew_wifi_at", fc="#D6EAF8", ec="#1F618D")
    arrow(ax, 8.2, 5.35, 8.2, 5.07)
    box(ax, 7.3, 4.4, 1.8, 0.55, "ew_llm", fc="#D6EAF8", ec="#1F618D")
    arrow(ax, 8.2, 4.4, 8.2, 4.12)
    box(ax, 7.1, 3.45, 2.2, 0.55, "MiMo HTTPS", fc="#D6EAF8", ec="#1F618D")
    arrow(ax, 8.2, 3.45, 8.2, 3.17)
    box(ax, 7.2, 2.3, 2.0, 0.55, "Agent 对话页", fc="#D4EFDF", ec="#196F3D")

    ax.text(
        5.2,
        0.16,
        "安全判决与 LLM 解耦：雷达门限与 alert_output 不依赖网络",
        ha="center",
        fontsize=9,
        color="#555555",
        style="italic",
    )
    save(fig, out / "fig_3_11_system_arch.png")


def draw_software_layers(out: Path) -> None:
    fig, ax = plt.subplots(figsize=(10.5, 8.0))
    ax.set_xlim(0, 10.5)
    ax.set_ylim(0, 8.0)
    ax.axis("off")
    ax.set_title("图 3-12  软件模块分层结构（app/edge_walker/）", fontsize=13, fontweight="bold", pad=12)

    layers = [
        ("入口", "#ECEFF1", "#455A64", ["ew_main.c  NSH 命令 ew boot / fake / wifi"]),
        (
            "感知 / 策略",
            "#FDEBD0",
            "#D35400",
            ["ew_ld2451.c  雷达解析 + ew_decide", "（不访问 WiFi / LVGL）"],
        ),
        (
            "呈现",
            "#FADBD8",
            "#C0392B",
            [
                "alert_output / alert_buzzer / alert_lcd",
                "ew_wifi_ui.c  WiFi 页",
                "ew_chat.c + ew_pinyin.c  Agent 页",
            ],
        ),
        (
            "传输",
            "#D6EAF8",
            "#1F618D",
            ["ew_wifi_at.c  AT 串口", "ew_net_state.c  链路快照", "ew_llm.c  MiMo HTTPS"],
        ),
        (
            "AI",
            "#E8DAEF",
            "#7D3C98",
            ["ew_agent.c + ew_agent_tool.c", "Skill approach-warn → Tool approach_alert"],
        ),
        (
            "调试",
            "#E8F8F5",
            "#117A65",
            ["ew_serial_ctl.c  @ 遥控", "ew_mirror.c + ew_panel.py  屏镜像"],
        ),
    ]
    y = 7.2
    for name, fc, ec, items in layers:
        box(ax, 0.4, y - 0.55, 1.3, 0.55, name, fc=fc, ec=ec, fs=10)
        text = "\n".join(items)
        box(ax, 1.9, y - 0.95, 8.1, 0.95, text, fc=fc, ec=ec, fs=9)
        y -= 1.05

    ax.text(
        5.2,
        0.4,
        "并发：LVGL 仅 UI 线程；/dev/ttyS2 由 ew_wifi_at 串行化；Scan/Join/HTTPS 互斥",
        ha="center",
        fontsize=9,
        color="#555555",
    )
    save(fig, out / "fig_3_12_software_layers.png")


def draw_skill_flow(out: Path) -> None:
    fig, ax = plt.subplots(figsize=(8.5, 7.5))
    ax.set_xlim(0, 8.5)
    ax.set_ylim(0, 7.5)
    ax.axis("off")
    ax.set_title("图 3-13  Skill 主动告警链路", fontsize=13, fontweight="bold", pad=12)

    nodes = [
        (3.0, 6.5, "LD2451 / ew fake 注入"),
        (3.0, 5.55, "ew_ld2451"),
        (3.0, 4.6, "ew_decide"),
        (3.0, 3.55, "SOFT / STRONG / EMERGENCY"),
        (3.0, 2.5, "ew_agent_proactive_alert"),
        (3.0, 1.55, "Tool: approach_alert"),
        (3.0, 0.55, "alert_output()\n蜂鸣 + LCD"),
    ]
    colors = ["#FDEBD0", "#FDEBD0", "#FDEBD0", "#FADBD8", "#E8DAEF", "#E8DAEF", "#F5B7B1"]
    ecs = ["#D35400"] * 3 + ["#C0392B"] + ["#7D3C98"] * 2 + ["#C0392B"]
    for (x, y, t), fc, ec in zip(nodes, colors, ecs):
        box(ax, x - 1.55, y - 0.32, 3.1, 0.64, t, fc=fc, ec=ec, fs=9)
    for i in range(len(nodes) - 1):
        arrow(ax, 3.0, nodes[i][1] - 0.32, 3.0, nodes[i + 1][1] + 0.32)

    ax.text(
        6.2,
        3.2,
        "MiMo / LLM\n不参与\n门限判决",
        ha="center",
        va="center",
        fontsize=10,
        color="#7D3C98",
        bbox=dict(boxstyle="round", facecolor="#F4ECF7", edgecolor="#7D3C98"),
    )
    save(fig, out / "fig_3_13_skill_flow.png")


def draw_ui_state(out: Path) -> None:
    fig, ax = plt.subplots(figsize=(10.0, 3.2))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 3.2)
    ax.axis("off")
    ax.set_title("图 3-14  预警 UI 状态机（alert_lcd）", fontsize=13, fontweight="bold", pad=10)

    states = [
        ("EW READY\n蓝底", "#AED6F1", "#1F618D"),
        ("SOFT\n黄底", "#F9E79F", "#B7950B"),
        ("STRONG/WARN\n橙底", "#F5CBA7", "#CA6F1E"),
        ("CRIT/EMERGENCY\n红底", "#F5B7B1", "#C0392B"),
        ("恢复 READY\n~1 s", "#AED6F1", "#1F618D"),
    ]
    x = 0.35
    w = 1.65
    for i, (label, fc, ec) in enumerate(states):
        box(ax, x, 1.0, w, 1.0, label, fc=fc, ec=ec, fs=8)
        if i < len(states) - 1:
            arrow(ax, x + w, 1.5, x + w + 0.35, 1.5)
        x += w + 0.35

    ax.text(5.0, 0.35, "目标离开或 @alert none → 约 1 s 内回 READY，蜂鸣停止", ha="center", fontsize=9, color="#555555")
    save(fig, out / "fig_3_14_ui_state.png")


def main() -> int:
    setup_cn()
    out = material_dir()
    draw_system_arch(out)
    draw_software_layers(out)
    draw_skill_flow(out)
    draw_ui_state(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
