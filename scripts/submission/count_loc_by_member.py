# -*- coding: utf-8 -*-
"""Rough LOC by module ownership (app/edge_walker)."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "app" / "edge_walker"
WJH = {"ew_ld2451.c", "ew_ld2451.h", "host_smoke.c", "host_smoke.h"}
WZY = {
    "ew_chat.c", "ew_chat.h", "ew_llm.c", "ew_llm.h",
    "ew_pinyin.c", "ew_pinyin.h", "ew_agent.c", "ew_agent.h",
    "ew_agent_tool.c", "ew_agent_tool.h",
}


def line_count(path: Path) -> int:
    return sum(1 for _ in path.open(encoding="utf-8", errors="ignore"))


def main() -> None:
    counts = {"zzx": 0, "wjh": 0, "wzy": 0, "font": 0}
    for p in sorted(ROOT.glob("*")):
        if p.suffix not in {".c", ".h"}:
            continue
        n = line_count(p)
        if p.name == "ew_font_cjk_18.c":
            counts["font"] = n
            continue
        if p.name in WJH:
            counts["wjh"] += n
        elif p.name in WZY:
            counts["wzy"] += n
        else:
            counts["zzx"] += n
    core = counts["zzx"] + counts["wjh"] + counts["wzy"]
    print(f"Core LOC (excl font): {core}")
    for key, name in [("zzx", "郑"), ("wjh", "王"), ("wzy", "韦")]:
        print(f"  {name}: {counts[key]} ({counts[key] / core * 100:.1f}%)")
    print(f"Font blob excluded: {counts['font']}")


if __name__ == "__main__":
    main()
