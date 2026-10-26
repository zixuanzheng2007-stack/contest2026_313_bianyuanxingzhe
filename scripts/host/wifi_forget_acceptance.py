#!/usr/bin/env python3
"""Reproduce and verify the Wi-Fi "forget saved network" UI action."""
from __future__ import annotations

import importlib.util
import argparse
import sys
import time
from pathlib import Path

import serial


ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS = ROOT / "VMware_share" / "artifacts"
PORT = "COM7"
BAUD = 1_000_000

SPEC = importlib.util.spec_from_file_location("ew_panel", ROOT / "tools/ew_panel.py")
assert SPEC and SPEC.loader
PANEL = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = PANEL
SPEC.loader.exec_module(PANEL)


def receive(sp: serial.Serial, parser: object, seconds: float) -> tuple[str, list]:
    deadline = time.monotonic() + seconds
    text_parts: list[str] = []
    frames: list = []
    while time.monotonic() < deadline:
        waiting = sp.in_waiting
        if waiting:
            parsed, text = parser.feed(sp.read(waiting))
            frames.extend(parsed)
            if text:
                text_parts.append(text)
        else:
            time.sleep(0.02)
    return "".join(text_parts), frames


def send(sp: serial.Serial, parser: object, command: str,
         wait: float) -> tuple[str, list]:
    print(f">>> {command}", flush=True)
    sp.write((command + "\r\n").encode("utf-8"))
    sp.flush()
    text, frames = receive(sp, parser, wait)
    print(text[-5000:] if text else "(silent)", flush=True)
    return text, frames


def save_frame(frame: object, path: Path) -> None:
    from PIL import Image

    image = Image.frombytes(
        "RGB", (frame.width, frame.height), frame.rgb565, "raw", "BGR;16")
    image.save(path)


def main() -> int:
    parser_args = argparse.ArgumentParser()
    parser_args.add_argument(
        "--quick", action="store_true",
        help="reuse the currently open, idle Wi-Fi page")
    parser_args.add_argument(
        "--direct", action="store_true",
        help="test the AT forget path through @forget without UI injection")
    args = parser_args.parse_args()
    stamp = time.strftime("%Y%m%d_%H%M%S")
    log_path = ARTIFACTS / f"wifi_forget_acceptance_{stamp}.txt"
    before_path = ARTIFACTS / f"wifi_forget_before_{stamp}.png"
    after_path = ARTIFACTS / f"wifi_forget_after_{stamp}.png"
    parser = PANEL.SerialFrameParser()
    transcript = [
        f"Wi-Fi forget acceptance {stamp}",
        f"port={PORT} baud={BAUD} dtr=0 rts=0",
    ]

    with serial.Serial(PORT, BAUD, timeout=0.02) as sp:
        sp.dtr = False
        sp.rts = False
        receive(sp, parser, 1.0)

        if args.direct:
            text, _ = send(sp, parser, "@forget", 12.0)
            transcript.extend((">>> @forget", text))
        elif not args.quick:
            text, _ = send(sp, parser, "@goto wifi", 135.0)
            transcript.extend((">>> @goto wifi", text))
        if not args.direct:
            text, frames = send(sp, parser, "@mirror snap", 10.0)
            transcript.extend((">>> @mirror snap (before)", text))
            hd = [f for f in frames if f.width == 390 and f.height == 450]
            if hd:
                save_frame(hd[-1], before_path)

            text, _ = send(sp, parser, "@tap 195 420", 8.0)
            transcript.extend((">>> @tap 195 420", text))
            text, frames = send(sp, parser, "@mirror snap", 10.0)
            transcript.extend((">>> @mirror snap (after)", text))
            hd = [f for f in frames if f.width == 390 and f.height == 450]
            if hd:
                save_frame(hd[-1], after_path)

        text, _ = receive(sp, parser, 5.0)
        transcript.extend((">>> wait for disconnect completion", text))
        text, _ = send(sp, parser, "@status", 35.0)
        transcript.extend((">>> @status", text))

    all_text = "\n".join(transcript)
    log_path.write_text(all_text, encoding="utf-8")
    jumped = "[ew-ui] page=1" in all_text
    forget_sent = "tx=AT+CWQAP" in all_text
    still_joined = "+CWJAP:" in all_text and "No AP" not in all_text
    print(f"LOG={log_path}")
    print(f"BEFORE={before_path if before_path.exists() else 'NONE'}")
    print(f"AFTER={after_path if after_path.exists() else 'NONE'}")
    print(f"PAGE={'FAIL agent' if jumped else 'PASS stayed off agent'}")
    print(f"CWQAP={'SEEN' if forget_sent else 'MISSING'}")
    print(f"ASSOCIATION={'FAIL still joined' if still_joined else 'cleared/unconfirmed'}")
    return 1 if jumped or still_joined or not forget_sent else 0


if __name__ == "__main__":
    raise SystemExit(main())
