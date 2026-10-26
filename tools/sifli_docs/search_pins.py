#!/usr/bin/env python3
"""Search SiFli DevKit-LCD design files for UART/GPIO strings (local zip only)."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent / "DevKit-LCD"
needles = [b"PA20", b"PA27", b"PA_20", b"PA_27", b"UART_TXD", b"UART_RXD", b"UART2", b"40P", b"HDR"]

if not ROOT.is_dir():
    print("Missing:", ROOT, file=sys.stderr)
    print("See tools/sifli_docs/README.md", file=sys.stderr)
    sys.exit(1)

for p in ROOT.rglob("*"):
    if not p.is_file():
        continue
    if p.suffix.lower() not in {".txt", ".sch", ".asc", ".pdf", ".docx", ".xls", ".xlsx"}:
        continue
    if p.stat().st_size > 80_000_000:
        continue
    data = p.read_bytes()
    hits = [n.decode() for n in needles if n.lower() in data.lower()]
    if hits:
        print(f"{p.name} -> {hits}")

for name in [
    "SF32LB52-DevKit-LCD-1-SCH_V1.2.0.txt",
    "SF32LB52-DevKit-LCD-1-SCH_V1.2.0.sch",
    "SF32LB52-DevKit-LCD_PCB_V1.2.0.asc",
]:
    p = ROOT / name
    if not p.is_file():
        print(name, "not found")
        continue
    data = p.read_bytes()
    for key in [b"PA27", b"PA_27", b"PA20", b"PA_20", b"UART_TXD", b"UART_RXD"]:
        idx = data.lower().find(key.lower())
        print(name, key.decode(), "idx", idx)
        if idx >= 0:
            chunk = data[max(0, idx - 100) : idx + 140]
            print(repr(chunk))
