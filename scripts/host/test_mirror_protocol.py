"""Host tests for raw/RLE mirror framing, corruption checks, and chunk boundaries."""
import importlib.util
import struct
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("ew_panel", ROOT / "tools/ew_panel.py")
assert SPEC and SPEC.loader
PANEL = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = PANEL
SPEC.loader.exec_module(PANEL)


def frame(magic: bytes, w: int, h: int, payload: bytes) -> bytes:
    return magic + struct.pack("<HHI", w, h, len(payload)) + payload


def main() -> None:
    red = b"\x00\xf8"
    green = b"\xe0\x07"
    blue = b"\x1f\x00"
    raw = red * 4 + green + blue
    # run(4 red), literal(green, blue)
    encoded = bytes((0x83,)) + red + bytes((0x01,)) + green + blue
    assert PANEL.decode_rle565(encoded, len(raw)) == raw

    parser = PANEL.SerialFrameParser()
    stream = b"boot\r\n" + frame(PANEL.RLE_MAGIC, 3, 2, encoded)
    frames = []
    texts = []
    for byte in stream:
        got, text = parser.feed(bytes((byte,)))
        frames.extend(got)
        texts.append(text)
    assert "boot" in "".join(texts)
    assert len(frames) == 1
    assert frames[0].rgb565 == raw and frames[0].codec == "RLE"

    parser = PANEL.SerialFrameParser()
    raw_frame = frame(PANEL.FB_MAGIC, 1, 3, red + green + blue)
    frames, text = parser.feed(raw_frame)
    assert not text and len(frames) == 1 and frames[0].codec == "RAW"

    parser = PANEL.SerialFrameParser()
    bad = frame(PANEL.RLE_MAGIC, 1, 1, bytes((0x82,)) + red)
    frames, text = parser.feed(bad)
    assert not frames and "corrupt" in text
    print("PASS: raw/RLE frames, byte-wise input, magic preservation, corruption rejection")


if __name__ == "__main__":
    main()
