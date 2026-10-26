#!/usr/bin/env python3
"""WiFi 验收 v2：@ 命令不先发换行（避免 NSH 抢 @scan）。"""
from __future__ import annotations

import re
import time
from pathlib import Path

import serial

ART = Path(__file__).resolve().parents[2] / "VMware_share" / "artifacts"
PORT, BAUD = "COM7", 1_000_000
PROBE = "Pura 80 Pro+"


def drain(sp: serial.Serial, sec: float) -> str:
    end = time.time() + sec
    b = ""
    while time.time() < end:
        n = sp.in_waiting
        if n:
            b += sp.read(n).decode("utf-8", "replace")
        else:
            time.sleep(0.05)
    return b


def at_cmd(sp: serial.Serial, cmd: str, recv: float) -> str:
    print(f"\n>>> @{cmd}", flush=True)
    sp.write(f"@{cmd}\r\n".encode())
    time.sleep(1.0)
    out = drain(sp, recv)
    print(out if out.strip() else "(silent)", flush=True)
    return out


def nsh_cmd(sp: serial.Serial, cmd: str, recv: float) -> str:
    print(f"\n>>> {cmd}", flush=True)
    sp.write(b"\r\n")
    time.sleep(0.4)
    drain(sp, 0.5)
    sp.write(f"{cmd}\r\n".encode())
    time.sleep(1.5)
    out = drain(sp, recv)
    print(out if out.strip() else "(silent)", flush=True)
    return out


def main() -> None:
    sp = serial.Serial(PORT, BAUD, timeout=0.1)
    sp.dtr = sp.rts = False
    all_out = ""

    print("等待 EW READY (15s)...", flush=True)
    boot = drain(sp, 15.0)
    all_out += boot
    if "EW READY" not in boot:
        sp.dtr = True
        time.sleep(0.12)
        sp.dtr = False
        all_out += drain(sp, 18.0)

    all_out += at_cmd(sp, "scan", 130.0)
    all_out += at_cmd(sp, "status", 30.0)
    all_out += at_cmd(sp, "ping", 15.0)
    all_out += nsh_cmd(sp, f'ew wifi probe "{PROBE}"', 50.0)
    all_out += nsh_cmd(sp, "ew wifi ping", 25.0)
    all_out += nsh_cmd(sp, "ew wifi", 15.0)
    sp.close()

    log = ART / f"wifi_acceptance_v2_{time.strftime('%Y%m%d_%H%M%S')}.txt"
    log.write_text(all_out, encoding="utf-8")
    print(f"\nLog: {log}")

    print("\n" + "=" * 56)
    print("验收摘要")
    print("=" * 56)

    def line(name: str, ok: bool, detail: str) -> None:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}: {detail}")

    line("MODEM", "wake ok" in all_out, "wake ok @115200/921600")
    line("ESP-AT RX 日志", "[ESP-AT RX]" in all_out, "新固件 RX 前缀")
    line("AT+GMR", "Bin version" in all_out or "WROOM-32" in all_out, "ESP-AT v4.2 WROOM-32")
    line("CIPSTA", "CIPSTA" in all_out, "IP 查询路径")

    m = re.search(r"\[ew-ctl\] scan (\d+) network", all_out)
    scan_n = int(m.group(1)) if m else -1
    line("@scan", scan_n >= 0, f"{scan_n} 个 AP" if scan_n >= 0 else "未完成")

    if "probe hit" in all_out:
        line(f"probe {PROBE}", True, "found")
    elif "probe miss" in all_out:
        line(f"probe {PROBE}", False, "miss（热点未开或被动扫漏）")
    else:
        line(f"probe {PROBE}", False, "无输出")

    if "Network: ONLINE" in all_out:
        line("联网", True, "ONLINE")
    elif "LAN ONLY" in all_out or ('ip="' in all_out and "0.0.0.0" not in all_out.split("CIPSTA")[-1][:80]):
        line("联网", False, "LAN only")
    elif "0.0.0.0" in all_out:
        line("联网", False, "未连热点 IP=0.0.0.0")
    else:
        line("联网", False, "未确认")

    if "MODEM:" in all_out:
        line("ew wifi ping 分层", True, "已输出分层状态")
    else:
        line("ew wifi ping 分层", False, "无 MODEM: 行")

    if scan_n >= 0 and "0.0.0.0" in all_out:
        print("\n下一步: 手机 2.4G 热点 → WiFi 页手输 SSID 或 @join \"Pura 80 Pro+\" 密码")


if __name__ == "__main__":
    main()
