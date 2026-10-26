#!/usr/bin/env python3
"""Join Wi-Fi through the running UI's @ protocol, with redacted logs."""
from __future__ import annotations

import argparse
import time
from serial_common import artifact_path, open_port, receive, write_log


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", default="COM7")
    ap.add_argument("--ssid", required=True)
    ap.add_argument("--password", required=True)
    args = ap.parse_args()
    stamp = time.strftime("%Y%m%d_%H%M%S")
    log_path = artifact_path("wifi_runtime_join")

    with open_port(args.port) as sp:
        receive(sp, 1.0)
        command = f'@join "{args.ssid}" "{args.password}"\r\n'
        print(">>> @join <ssid> <redacted>", flush=True)
        sp.write(command.encode("utf-8"))
        sp.flush()
        join_text = receive(sp, 45.0)
        print(join_text[-5000:] if join_text else "(silent)", flush=True)
        sp.write(b"@status\r\n")
        sp.flush()
        status_text = receive(sp, 35.0)
        print(status_text[-5000:] if status_text else "(silent)", flush=True)

    log_text = (
        f"Wi-Fi runtime join {stamp}\n"
        f"port={args.port} baud=1000000 dtr=0 rts=0\n"
        f"ssid={args.ssid}\n>>> @join <ssid> <redacted>\n"
        f"{join_text}\n>>> @status\n{status_text}"
    )
    write_log(log_path, log_text)
    joined = "join ok:" in join_text
    has_ip = "+CIPSTA:ip:" in status_text and 'ip:"0.0.0.0"' not in status_text
    print(f"LOG={log_path}")
    print(f"VERDICT={'PASS' if joined and has_ip else 'FAIL'}")
    return 0 if joined and has_ip else 1


if __name__ == "__main__":
    raise SystemExit(main())
