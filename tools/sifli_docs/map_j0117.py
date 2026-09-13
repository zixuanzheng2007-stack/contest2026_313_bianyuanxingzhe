from pathlib import Path
import re

asc = Path(r"E:\openvela\contest2026_313_bianyuanxingzhe\tools\sifli_docs\DevKit-LCD\SF32LB52-DevKit-LCD_PCB_V1.2.0.asc").read_text(encoding="latin1", errors="ignore")

# Find J0117 references and nearby signals
for m in re.finditer(r"J0117\.(\d+)", asc):
    pass
pins = sorted({int(x) for x in re.findall(r"J0117\.(\d+)", asc)})
print("J0117 pins seen:", pins)

# For each pin, find SIGNAL blocks mentioning J0117.N
for n in pins:
    pat = rf"\*SIGNAL\*\s+(\S+).*?J0117\.{n}\b"
    ms = re.findall(pat, asc, flags=re.S)
    # simpler: lines around J0117.n
    idxs = [m.start() for m in re.finditer(rf"J0117\.{n}\b", asc)]
    sigs = set()
    for i in idxs[:3]:
        chunk = asc[max(0, i - 200) : i + 80]
        sm = re.search(r"\*SIGNAL\*\s+(\S+)", chunk)
        if sm:
            sigs.add(sm.group(1))
        else:
            # search backwards for last SIGNAL
            prev = asc.rfind("*SIGNAL*", 0, i)
            if prev >= 0:
                sm2 = re.search(r"\*SIGNAL\*\s+(\S+)", asc[prev : prev + 80])
                if sm2:
                    sigs.add(sm2.group(1))
    print(f"J0117.{n}: {sorted(sigs)}")

# component definition for J0117
idx = asc.find("J0117")
print("--- context first J0117 ---")
print(asc[idx - 200 : idx + 400])
