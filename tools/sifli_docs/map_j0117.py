#!/usr/bin/env python3
"""Parse SiFli DevKit-LCD PCB ASC for J0117 pin signals (local official zip only)."""
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parent
ASC = ROOT / "DevKit-LCD" / "SF32LB52-DevKit-LCD_PCB_V1.2.0.asc"

if not ASC.is_file():
    print("Missing:", ASC, file=sys.stderr)
    print("Download SF32LB52-DevKit-LCD_V1.2.0.zip from SiFli and extract to", ROOT / "DevKit-LCD", file=sys.stderr)
    sys.exit(1)

asc = ASC.read_text(encoding="latin1", errors="ignore")

pins = sorted({int(x) for x in re.findall(r"J0117\.(\d+)", asc)})
print("J0117 pins seen:", pins)

for n in pins:
    idxs = [m.start() for m in re.finditer(rf"J0117\.{n}\b", asc)]
    sigs = set()
    for i in idxs[:3]:
        chunk = asc[max(0, i - 200) : i + 80]
        sm = re.search(r"\*SIGNAL\*\s+(\S+)", chunk)
        if sm:
            sigs.add(sm.group(1))
        else:
            prev = asc.rfind("*SIGNAL*", 0, i)
            if prev >= 0:
                sm2 = re.search(r"\*SIGNAL\*\s+(\S+)", asc[prev : prev + 80])
                if sm2:
                    sigs.add(sm2.group(1))
    print(f"J0117.{n}: {sorted(sigs)}")

idx = asc.find("J0117")
print("--- context first J0117 ---")
print(asc[idx - 200 : idx + 400])
