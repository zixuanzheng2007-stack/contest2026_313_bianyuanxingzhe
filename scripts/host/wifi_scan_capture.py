"""Capture one board command without resetting the board or changing credentials."""
import argparse
import time
from pathlib import Path

import serial


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", nargs="?", default="@help")
    parser.add_argument("--port", default="COM7")
    parser.add_argument("--seconds", type=float, default=10)
    parser.add_argument("--reset", action="store_true")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()
    out_dir = Path(__file__).resolve().parents[2] / "VMware_share/artifacts"
    out_dir.mkdir(parents=True, exist_ok=True)
    log = out_dir / ("wifi_scan_capture_" + time.strftime("%Y%m%d_%H%M%S") + ".txt")
    sp = serial.Serial(port=None, baudrate=1_000_000, timeout=0.2)
    sp.dtr = sp.rts = False
    sp.port = args.port
    with sp, log.open("w", encoding="utf-8") as fp, log.with_suffix(".bin").open("wb") as raw:
        if args.reset:
            sp.dtr = True
            time.sleep(0.15)
            sp.dtr = False
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                data = sp.read(4096)
                if data:
                    raw.write(data)
                    text = data.decode("utf-8", "replace")
                    fp.write(text)
                    if not args.quiet:
                        print(text, end="", flush=True)
        fp.write("COMMAND: " + args.command + "\n")
        sp.write((args.command + "\r\n").encode())
        deadline = time.monotonic() + args.seconds
        received = 0
        while time.monotonic() < deadline:
            data = sp.read(4096)
            if data:
                raw.write(data)
                received += len(data)
                text = data.decode("utf-8", "replace")
                fp.write(text)
                fp.flush()
                if not args.quiet:
                    print(text, end="", flush=True)
        print(f"\nReceived {received} bytes. Log: {log}")


if __name__ == "__main__":
    main()
