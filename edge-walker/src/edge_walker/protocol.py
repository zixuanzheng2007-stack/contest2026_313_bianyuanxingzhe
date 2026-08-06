"""LD2451 检测上报帧编解码（按项目文档字段；完整细节以厂商 V1.03 PDF 为准）。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Optional, Sequence, Tuple

from .models import RadarTarget

FRAME_HEAD = bytes([0xF4, 0xF3, 0xF2, 0xF1])
FRAME_TAIL = bytes([0xF8, 0xF7, 0xF6, 0xF5])
TARGET_SIZE = 6
MAX_TARGETS = 5


@dataclass
class DetectFrame:
    targets: List[RadarTarget]

    @property
    def primary(self) -> Optional[RadarTarget]:
        if not self.targets:
            return None
        approaching = [t for t in self.targets if t.approaching]
        pool = approaching or self.targets
        return min(pool, key=lambda t: t.range_m)


def encode_target(target: RadarTarget) -> bytes:
    alarm = 0x01 if (target.alarm or target.approaching) else 0x00
    angle = int(round(target.azimuth_deg)) + 0x80
    angle = max(0, min(255, angle))
    distance = max(0, min(100, int(round(target.range_m))))
    direction = 0x01 if target.approaching else 0x00
    speed = max(0, min(120, int(round(target.speed_kmh))))
    snr = max(0, min(255, int(target.snr)))
    return bytes([alarm, angle, distance, direction, speed, snr])


def decode_target(raw: bytes) -> RadarTarget:
    if len(raw) < TARGET_SIZE:
        raise ValueError("target payload too short")
    alarm = raw[0] == 0x01
    azimuth = raw[1] - 0x80
    distance = float(raw[2])
    approaching = raw[3] == 0x01
    speed = float(raw[4])
    snr = int(raw[5])
    return RadarTarget(
        range_m=distance,
        speed_kmh=speed,
        approaching=approaching,
        azimuth_deg=float(azimuth),
        snr=snr,
        alarm=alarm,
    )


def build_detect_frame(targets: Sequence[RadarTarget]) -> bytes:
    if len(targets) > MAX_TARGETS:
        raise ValueError(f"at most {MAX_TARGETS} targets")
    body = bytearray()
    body.append(len(targets))
    for t in targets:
        body.extend(encode_target(t))
    length = len(body)
    return FRAME_HEAD + bytes([length & 0xFF, (length >> 8) & 0xFF]) + bytes(body) + FRAME_TAIL


def parse_detect_frame(data: bytes) -> DetectFrame:
    if len(data) < 8:
        raise ValueError("frame too short")
    if data[:4] != FRAME_HEAD:
        raise ValueError("bad frame head")
    if data[-4:] != FRAME_TAIL:
        raise ValueError("bad frame tail")
    length = data[4] | (data[5] << 8)
    body = data[6 : 6 + length]
    if len(body) != length:
        raise ValueError("length mismatch")
    if not body:
        return DetectFrame(targets=[])
    count = body[0]
    rest = body[1:]
    if count * TARGET_SIZE != len(rest):
        raise ValueError("target count does not match payload")
    targets = [
        decode_target(rest[i : i + TARGET_SIZE])
        for i in range(0, len(rest), TARGET_SIZE)
    ]
    return DetectFrame(targets=targets)


class FrameStreamParser:
    """从字节流中切出完整检测帧。"""

    def __init__(self) -> None:
        self._buf = bytearray()

    def feed(self, chunk: bytes) -> List[DetectFrame]:
        self._buf.extend(chunk)
        frames: List[DetectFrame] = []
        while True:
            start = self._buf.find(FRAME_HEAD)
            if start < 0:
                # 保留可能构成帧头的后缀，避免分包把 F4 F3 F2 清掉
                if len(self._buf) > 3:
                    self._buf[:] = self._buf[-3:]
                break
            if start > 0:
                del self._buf[:start]
            if len(self._buf) < 6:
                break
            length = self._buf[4] | (self._buf[5] << 8)
            total = 6 + length + 4
            if len(self._buf) < total:
                break
            raw = bytes(self._buf[:total])
            del self._buf[:total]
            if raw[-4:] != FRAME_TAIL:
                del self._buf[:1]
                continue
            frames.append(parse_detect_frame(raw))
        return frames


def encode_many(frames: Iterable[Sequence[RadarTarget]]) -> bytes:
    out = bytearray()
    for targets in frames:
        out.extend(build_detect_frame(targets))
    return bytes(out)


def split_hex(frame: bytes) -> str:
    return " ".join(f"{b:02X}" for b in frame)
