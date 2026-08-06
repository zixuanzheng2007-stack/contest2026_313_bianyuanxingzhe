"""板到后的 UART 适配层占位：无板阶段用 simulator，有板后读串口字节流。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Iterator, List, Sequence

from .models import RadarTarget
from .protocol import FrameStreamParser, build_detect_frame


class RadarSource(ABC):
    @abstractmethod
    def frames(self) -> Iterator[List[RadarTarget]]:
        raise NotImplementedError


class SimulatedRadarSource(RadarSource):
    def __init__(self, playlist: Sequence[Sequence[RadarTarget]]) -> None:
        self._playlist = playlist

    def frames(self) -> Iterator[List[RadarTarget]]:
        for targets in self._playlist:
            yield list(targets)


class UartRadarSource(RadarSource):
    """
    真机占位。板到后实现：打开 /dev/ttySx 或 COMx，feed 到 FrameStreamParser。
    当前调用会明确报错，避免误当已接好硬件。
    """

    def __init__(self, port: str, baudrate: int = 115200) -> None:
        self.port = port
        self.baudrate = baudrate
        self._parser = FrameStreamParser()

    def frames(self) -> Iterator[List[RadarTarget]]:
        raise NotImplementedError(
            f"UART source not wired yet (port={self.port}). "
            "Use SimulatedRadarSource until DevKit-LCD + LD2451 arrive."
        )


def targets_to_wire(targets: Sequence[RadarTarget]) -> bytes:
    """调试用：把目标列表打成可写入串口环回的字节。"""
    return build_detect_frame(targets)
