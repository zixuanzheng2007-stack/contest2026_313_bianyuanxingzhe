#!/usr/bin/env python3
"""Real-board acceptance for PC pointer, UTF-8 keyboard, and HD mirror."""
from __future__ import annotations

import importlib.util
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
            parsed_frames, text = parser.feed(sp.read(waiting))
            frames.extend(parsed_frames)
            if text:
                text_parts.append(text)
        else:
            time.sleep(0.01)
    return "".join(text_parts), frames


def send(sp: serial.Serial, parser: object, command: str,
         wait: float) -> tuple[str, list]:
    shown = command.split(" ", 1)[0] + " <redacted>" \
        if command.startswith(("@input ", "@submit ")) else command
    print(f">>> {shown}", flush=True)
    sp.write((command + "\r\n").encode("utf-8"))
    sp.flush()
    text, frames = receive(sp, parser, wait)
    print(text[-3000:] if text else "(silent)", flush=True)
    return text, frames


def save_frame(frame: object, path: Path) -> None:
    try:
        from PIL import Image
    except ImportError:
        path = path.with_suffix(".ppm")
        rgb = PANEL.rgb565_to_rgb(frame.rgb565)
        path.write_bytes(f"P6\n{frame.width} {frame.height}\n255\n".encode() + rgb)
        return
    image = Image.frombytes(
        "RGB", (frame.width, frame.height), frame.rgb565, "raw", "BGR;16")
    image.save(path)


def main() -> int:
    stamp = time.strftime("%Y%m%d_%H%M%S")
    log_path = ARTIFACTS / f"pc_control_acceptance_{stamp}.txt"
    frame_path = ARTIFACTS / f"pc_control_hd_{stamp}.png"
    parser = PANEL.SerialFrameParser()
    transcript: list[str] = [
        f"PC control acceptance {stamp}",
        f"port={PORT} baud={BAUD} dtr=0 rts=0",
    ]
    frames: list = []

    try:
        sp = serial.Serial(PORT, BAUD, timeout=0.02)
        sp.dtr = False
        sp.rts = False
        boot_text, boot_frames = receive(sp, parser, 2.0)
        transcript.append(boot_text)
        frames.extend(boot_frames)

        steps = (
            ("@help", 2.0),
            ("@goto chat", 2.0),
            ("@input Hello", 2.0),
            ("@input 你好，边缘行者", 2.0),
            ("@mirror snap", 8.0),
            ("@mirror fast", 1.0),
            ("@submit 你好", 4.0),
            ("@key backspace", 2.0),
        )
        for command, wait in steps:
            text, new_frames = send(sp, parser, command, wait)
            transcript.extend((f">>> {command.split(' ', 1)[0]}", text))
            frames.extend(new_frames)

        touch_commands = ["@touch down 130 330"]
        touch_commands.extend(
            f"@touch move {130 + index * 10} {330 + index * 3}"
            for index in range(1, 9)
        )
        touch_commands.append("@touch up 210 354")
        sp.write(b"@mirror fast\r\n")
        sp.flush()
        time.sleep(0.20)
        for command in touch_commands:
            sp.write((command + "\r\n").encode("utf-8"))
            sp.flush()
            time.sleep(0.10)
        text, new_frames = receive(sp, parser, 4.0)
        transcript.extend((">>> @touch burst", text))
        frames.extend(new_frames)
        text, new_frames = send(sp, parser, "@mirror off", 1.0)
        transcript.extend((">>> @mirror", text))
        frames.extend(new_frames)
        sp.close()
    except Exception as exc:
        transcript.append(f"ERROR: {type(exc).__name__}: {exc}")

    all_text = "\n".join(transcript)
    log_path.write_text(all_text, encoding="utf-8")
    hd_frames = [f for f in frames if f.width == 390 and f.height == 450]
    if hd_frames:
        save_frame(hd_frames[-1], frame_path)

    checks = {
        "help exposes UTF-8 input": "@input/@submit <UTF-8 text>" in all_text,
        "ASCII input accepted": "input ok bytes=5" in all_text,
        "Chinese input accepted": "input ok bytes=21" in all_text,
        "Chinese submit accepted": "submit ok bytes=6" in all_text,
        "pointer commands accepted": (
            "cmd: touch down 130 330" in all_text
            and "cmd: touch up 210 354" in all_text
            and all_text.count("cmd: touch move") >= 8
        ),
        "CJK font has no compression warning": (
            "LV_USE_FONT_COMPRESSED" not in all_text
        ),
        "HD frame 390x450": bool(hd_frames),
    }
    print(f"LOG={log_path}")
    print(f"FRAME={frame_path if hd_frames else 'NONE'}")
    for name, passed in checks.items():
        print(f"{'PASS' if passed else 'FAIL'}: {name}")
    passed = all(checks.values())
    print(f"VERDICT={'PASS' if passed else 'FAIL'}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
