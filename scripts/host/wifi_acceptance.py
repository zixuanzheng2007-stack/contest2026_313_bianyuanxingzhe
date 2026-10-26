#!/usr/bin/env python3
"""新固件 WiFi 分层验收（@ 遥控 + 关键 ew 命令）。"""
from __future__ import annotations

import re
import sys
import time
from pathlib import Path

import serial

REPO = Path(__file__).resolve().parents[2]
ART = REPO / "VMware_share" / "artifacts"
PORT, BAUD = "COM7", 1_000_000
PROBE_SSID = "Pura 80 Pro+"


def drain(sp: serial.Serial, sec: float) -> str:
    end = time.time() + sec
    buf = ""
    while time.time() < end:
        n = sp.in_waiting
        if n:
            buf += sp.read(n).decode("utf-8", "replace")
        else:
            time.sleep(0.05)
    return buf


def run(sp: serial.Serial, cmd: str, recv: float, log: list[str]) -> str:
    line = f">>> {cmd}"
    log.append("")
    log.append(line)
    print(line, flush=True)
    sp.write(b"\r\n")
    time.sleep(0.25)
    while sp.in_waiting:
        sp.read(sp.in_waiting)
    sp.write(f"{cmd}\r\n".encode())
    time.sleep(1.0)
    out = drain(sp, recv)
    text = out if out.strip() else "(silent)"
    log.append(text)
    print(text, flush=True)
    return out


def main() -> int:
    ts = time.strftime("%Y%m%d_%H%M%S")
    log_path = ART / f"wifi_acceptance_{ts}.txt"
    log: list[str] = [f"=== WiFi acceptance {ts} ==="]

    try:
        sp = serial.Serial(PORT, BAUD, timeout=0.1)
    except serial.SerialException as e:
        print(f"FAIL: cannot open {PORT}: {e}")
        return 1
    sp.dtr = sp.rts = False
    drain(sp, 1.0)

    all_out = ""
    steps = [
        ("@ping", 20.0),
        ("@status", 25.0),
        ("@scan", 130.0),
        (f'ew wifi probe "{PROBE_SSID}"', 45.0),
        ("ew wifi ping", 25.0),
        ("ew wifi", 15.0),
    ]
    for cmd, recv in steps:
        all_out += run(sp, cmd, recv, log)
    sp.close()

    log_path.write_text("\n".join(log), encoding="utf-8")
    print(f"\nLog: {log_path}")

    # --- verdict ---
    checks: list[tuple[str, bool, str]] = []

    modem_ok = (
        "wake ok" in all_out
        or "[ESP-AT RX]" in all_out and "OK" in all_out
        or "MODEM: OK" in all_out
    )
    checks.append(("A MODEM/AT 握手", modem_ok, "wake ok / ESP-AT RX OK"))

    has_cipsta = "CIPSTA" in all_out or "AT+CIPSTA" in all_out
    checks.append(("B 新固件 CIPSTA 路径", has_cipsta, "status/bringup 含 CIPSTA"))

    has_esp_rx = "[ESP-AT RX]" in all_out
    checks.append(("C [ESP-AT RX] 调试日志", has_esp_rx, "新 RX 前缀"))

    markers = all_out.count("+CWLAP:")
    m_scan = re.search(r"(\d+) network\(s\)", all_out)
    scan_n = int(m_scan.group(1)) if m_scan else -1
    scan_ok = scan_n >= 0
    checks.append(("D @scan 完成", scan_ok, f"parsed={scan_n}, raw_markers={markers}"))

    if markers > 0 and scan_n == 0:
        checks.append(("D2 CWLAP 解析", False, "有原始 CWLAP 但列表空 → parser 问题"))
    elif scan_n > 0:
        checks.append(("D2 CWLAP 解析", True, f"{scan_n} 条 AP"))

    probe_hit = "probe hit" in all_out
    probe_miss = "probe miss" in all_out
    if probe_hit:
        checks.append(("E 定向 probe 热点", True, PROBE_SSID))
    elif probe_miss:
        checks.append(("E 定向 probe 热点", False, f"未扫到 {PROBE_SSID}（被动扫漏/热点未开）"))
    else:
        checks.append(("E 定向 probe 热点", False, "无 probe 回显（检查 ew wifi probe）"))

    if "Network: ONLINE" in all_out or "WIFI ON" in all_out or "ONLINE" in all_out:
        checks.append(("F 联网状态", True, "ONLINE"))
    elif "LAN ONLY" in all_out or "WIFI LAN" in all_out or "LAN: ip=" in all_out:
        checks.append(("F 联网状态", False, "LAN ONLY（已连热点无公网）"))
    elif "0.0.0.0" in all_out or "not connected" in all_out.lower():
        checks.append(("F 联网状态", False, "未连热点 / IP=0.0.0.0"))
    else:
        checks.append(("F 联网状态", False, "未确认"))

    layered = "MODEM:" in all_out
    checks.append(("G ew wifi ping 分层", layered, "MODEM/WiFi/LAN/ONLINE 输出"))

    print("\n" + "=" * 60)
    print("验收结果")
    print("=" * 60)
    pass_n = 0
    for name, ok, detail in checks:
        mark = "PASS" if ok else "FAIL"
        if ok:
            pass_n += 1
        print(f"  [{mark}] {name}: {detail}")
    print("=" * 60)
    print(f"通过 {pass_n}/{len(checks)}")

    if not probe_hit and scan_n >= 0:
        print("\n建议: 手机 2.4G 热点开启后，WiFi 页手动输入 SSID 连接，或:")
        print(f'  @join "{PROBE_SSID}" <密码>')

    # exit 0 if core modem+scan work; full online needs user hotspot
    core = modem_ok and scan_ok
    return 0 if core else 1


if __name__ == "__main__":
    raise SystemExit(main())
