#!/usr/bin/env python3
"""Verify quick prompts are hidden until the Agent input is clicked."""

from __future__ import annotations

import importlib.util
import sys
import time
from pathlib import Path

from serial_common import ARTIFACTS, open_port, write_log


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("ew_panel", ROOT / "tools/ew_panel.py")
assert SPEC and SPEC.loader
PANEL = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = PANEL
SPEC.loader.exec_module(PANEL)


def receive(port: object, parser: object, seconds: float) -> tuple[str, list]:
    deadline = time.monotonic() + seconds
    text_parts: list[str] = []
    frames: list = []
    while time.monotonic() < deadline:
        if port.in_waiting:
            parsed, text = parser.feed(port.read(port.in_waiting))
            frames.extend(parsed)
            if text:
                text_parts.append(text)
        else:
            time.sleep(0.01)
    return "".join(text_parts), frames


def command(port: object, parser: object, value: str,
            wait: float) -> tuple[str, list]:
    port.write((value + "\r\n").encode("utf-8"))
    port.flush()
    return receive(port, parser, wait)


def save_frame(frame: object, path: Path) -> None:
    from PIL import Image

    image = Image.frombytes(
        "RGB", (frame.width, frame.height), frame.rgb565, "raw", "BGR;16")
    image.save(path)


def main() -> int:
    stamp = time.strftime("%Y%m%d_%H%M%S")
    log_path = ARTIFACTS / f"chat_quick_prompts_{stamp}.txt"
    parser = PANEL.SerialFrameParser()
    transcript = ["Chat quick-prompts acceptance",
                  "port=COM7 baud=1000000 dtr=0 rts=0"]
    shots: list[tuple[str, object]] = []
    phase_text: dict[str, str] = {}

    with open_port() as port:
        transcript.append(receive(port, parser, 16.0)[0])
        for label, value, wait in (
            ("reset", "@goto warn", 2.0),
            ("goto", "@goto chat", 3.0),
            ("default", "@mirror snap", 9.0),
            ("focus", "@tap 185 416", 3.0),
            ("shown", "@mirror snap", 9.0),
            ("dismiss", "@tap 250 40", 3.0),
            ("hidden", "@mirror snap", 9.0),
        ):
            text, frames = command(port, parser, value, wait)
            phase_text[label] = text
            transcript.extend((f">>> {value}", text))
            hd = [frame for frame in frames
                  if frame.width == 390 and frame.height == 450]
            if hd and label in ("default", "shown", "hidden"):
                shots.append((label, hd[-1]))

    text = "\n".join(transcript)
    write_log(log_path, text)
    for label, frame in shots:
        save_frame(frame, ARTIFACTS / f"chat_quick_prompts_{stamp}_{label}.png")

    labels = {label for label, _ in shots}
    checks = {
        "default has no show event": (
            "quick prompts shown" not in phase_text.get("goto", "")
            and "quick prompts shown" not in phase_text.get("default", "")
        ),
        "input click shows prompts": text.count("quick prompts shown") == 1,
        "title click hides prompts": text.count("quick prompts hidden") == 1,
        "three HD frames": labels == {"default", "shown", "hidden"},
    }
    print(f"LOG={log_path}")
    print(f"FRAMES={','.join(sorted(labels))}")
    for name, passed in checks.items():
        print(f"{name}={'PASS' if passed else 'FAIL'}")
    passed = all(checks.values())
    print(f"VERDICT={'PASS' if passed else 'FAIL'}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
