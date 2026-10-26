"""Host regression tests for mirror pointer mapping and UTF-8 input commands."""

import importlib.util
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("ew_panel", ROOT / "tools/ew_panel.py")
assert SPEC and SPEC.loader
PANEL = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = PANEL
SPEC.loader.exec_module(PANEL)


def main() -> None:
    assert PANEL.map_canvas_to_lcd(10, 20, 10, 20, 780, 900, 390, 450) == (0, 0)
    assert PANEL.map_canvas_to_lcd(789, 919, 10, 20, 780, 900, 390, 450) == (389, 449)
    assert PANEL.map_canvas_to_lcd(9, 20, 10, 20, 780, 900, 390, 450) is None
    assert PANEL.map_canvas_to_lcd(389, 449, 0, 0, 390, 450, 195, 225) == (389, 449)
    assert PANEL.fit_mirror_size(390, 450, 824, 720) == (577, 666)
    fitted = PANEL.fit_mirror_size(390, 450, 640, 480)
    assert fitted[0] <= 640 - PANEL.BEZEL_SIDE * 2 - 8
    assert fitted[1] <= 480 - PANEL.BEZEL_TOP - PANEL.BEZEL_BOT - 8
    rgb = bytes((10, 20, 30, 40, 50, 60))
    scaled, width, height = PANEL.scale_rgb_nearest(rgb, 2, 1, 3, 2)
    assert (width, height) == (3, 2)
    assert len(scaled) == 18

    chinese = "你好，边缘行者"
    command = PANEL.remote_text_command(chinese)
    submit = PANEL.remote_text_command(chinese, submit=True)
    assert command == "@input " + chinese
    assert submit == "@submit " + chinese
    assert command.encode("utf-8").decode("utf-8") == command
    assert "\r" not in PANEL.remote_text_command("a\r\nb")
    assert len(PANEL.normalize_remote_text("中" * 300).encode("utf-8")) == 600
    assert PANEL.wheel_drag_end((195, 225), 120) == (195, 273)
    assert PANEL.wheel_drag_end((195, 225), -120) == (195, 177)
    assert PANEL.wheel_drag_end((195, 440), 120) == (195, 449)
    os.environ["EW_TEST_SECRET"] = "tp-test"
    assert PANEL.read_host_secret("EW_TEST_SECRET") == "tp-test"
    del os.environ["EW_TEST_SECRET"]
    print("PASS: pointer mapping and UTF-8 input/submit commands")


if __name__ == "__main__":
    main()
