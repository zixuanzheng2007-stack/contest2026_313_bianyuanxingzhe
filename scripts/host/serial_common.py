"""Shared serial policy for Edge Walker Host tools."""

from __future__ import annotations

import re
import time
from pathlib import Path

import serial

ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS = ROOT / "VMware_share" / "artifacts"
DEFAULT_PORT = "COM7"
DEFAULT_BAUD = 1_000_000


def open_port(port: str = DEFAULT_PORT, timeout: float = 0.02) -> serial.Serial:
    device = serial.Serial(port, DEFAULT_BAUD, timeout=timeout)
    device.dtr = False
    device.rts = False
    return device


def receive(device: serial.Serial, seconds: float) -> str:
    deadline = time.monotonic() + seconds
    chunks: list[str] = []
    while time.monotonic() < deadline:
        if device.in_waiting:
            chunks.append(device.read(device.in_waiting).decode("utf-8", "replace"))
        else:
            time.sleep(0.02)
    return "".join(chunks)


def send_line(device: serial.Serial, command: str, wait: float) -> str:
    device.write((command.rstrip("\r\n") + "\r\n").encode("utf-8"))
    device.flush()
    return receive(device, wait)


def artifact_path(prefix: str, suffix: str = ".txt") -> Path:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    return ARTIFACTS / f"{prefix}_{time.strftime('%Y%m%d_%H%M%S')}{suffix}"


def redact(text: str) -> str:
    text = re.sub(r"(@join\s+)(?:\"[^\"]*\"|\S+)(?:\s+)(?:\"[^\"]*\"|\S+)",
                  r"\1<ssid> <redacted>", text)
    text = re.sub(r"(@mimo-set\s+)\S+", r"\1<redacted>", text)
    text = re.sub(r"(AT\+CWJAP=).*", r"\1***", text)
    return text


def write_log(path: Path, text: str) -> None:
    path.write_text(redact(text), encoding="utf-8")
