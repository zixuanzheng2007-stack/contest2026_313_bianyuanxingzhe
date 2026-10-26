#!/usr/bin/env python3
"""Install and exercise only the Edge Walker app on an explicitly chosen ADB device.

Supports a local simulated device, a C fixture, or explicit physical-board UART.
None of these modes verifies independent phone BLE or device Wi-Fi transport.
This is intentionally not named test_*.py: the host regression runner is hardware-free.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager, ExitStack
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import queue
import subprocess
import tempfile
import threading
import time
import xml.etree.ElementTree as ET

from mobile_device_simulator import running_simulator

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = "com.edgewalker.companion"


@contextmanager
def physical_board_gateway(port: int, board_port: str):
    """Only open the selected UART; never reset, flash or send actuator commands."""
    import serial
    from mobile_serial_gateway import running_gateway

    transport = serial.Serial(port=None, baudrate=1_000_000, timeout=0.05,
                              write_timeout=0.2)
    transport.dtr = transport.rts = False
    transport.port = board_port
    try:
        transport.open()
        with running_gateway(transport, port=port, subscription_interval_s=3,
                             broker_options={"timeout_s": 1.5}) as server:
            yield server
    finally:
        transport.close()


@contextmanager
def snapshot_gateway_fixture(port: int, output: Path, *, waiting: bool = False):
    """Run real C serialization through the real gateway with OS pipes, not UART.

    Its state is deliberately fixture data. This never opens a COM port.
    """
    from test_snapshot import build_snapshot_fixture
    from mobile_serial_gateway import running_gateway

    class ProcessSerial:
        timeout = 0.02

        def __init__(self, executable, stderr):
            mode = "--stdio-waiting" if waiting else "--stdio"
            self.process = subprocess.Popen([str(executable), mode], stdin=subprocess.PIPE,
                                            stdout=subprocess.PIPE, stderr=stderr)
            self.messages = queue.Queue(maxsize=16)
            self.buffer = bytearray()
            self.closed = False
            self.reader = threading.Thread(target=self.collect, daemon=True)
            self.reader.start()

        def collect(self):
            while not self.closed:
                line = self.process.stdout.readline(8193)
                if not line:
                    return
                try:
                    self.messages.put(line, timeout=0.2)
                except queue.Full:
                    return

        def write(self, data):
            if self.closed or self.process.poll() is not None:
                raise OSError("C snapshot fixture is closed")
            self.process.stdin.write(data)
            self.process.stdin.flush()
            return len(data)

        def read(self, size):
            if self.closed:
                raise OSError("C snapshot fixture is closed")
            if not self.buffer:
                try:
                    self.buffer.extend(self.messages.get(timeout=self.timeout))
                except queue.Empty:
                    return b""
            result = bytes(self.buffer[:size])
            del self.buffer[:size]
            return result

        def close(self):
            if self.closed:
                return
            self.closed = True
            self.process.stdin.close()
            try:
                self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.process.terminate()
                self.process.wait(timeout=2)
            self.reader.join(timeout=2)
            self.process.stdout.close()

    with tempfile.TemporaryDirectory(prefix="ew_gateway_ui_") as directory:
        executable = build_snapshot_fixture(Path(directory))
        with (output / ("fixture_waiting.log" if waiting else "fixture_valid.log")).open("wb") as log:
            transport = ProcessSerial(executable, log)
            try:
                with running_gateway(transport, port=port, subscription_interval_s=3,
                                     broker_options={"timeout_s": 1.0}) as server:
                    yield server
            finally:
                transport.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--adb", type=Path, default=Path("C:/Program Files (x86)/Android/android-sdk/platform-tools/adb.exe"))
    parser.add_argument("--serial", required=True, help="Exact device from adb devices; never use an implicit target")
    parser.add_argument("--apk", type=Path, default=ROOT / "output/mobile_android/edge-walker-companion-debug.apk")
    parser.add_argument("--port", type=int, default=8765)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--gateway-fixture", action="store_true",
                        help="Test read-only gateway using real C serializer and fixture state, no COM port")
    mode.add_argument("--board-port", help="Read-only physical board UART, e.g. COM7; no reset or flash")
    mode.add_argument("--prototype-existing", action="store_true",
                      help="Use an already running physical PC prototype service; never opens COM")
    mode.add_argument("--prototype-fixture", action="store_true",
                      help="Run prototype sensitivity/model fixtures locally; no COM or cloud access")
    parser.add_argument("--output", type=Path, default=ROOT / "output/mobile_android/acceptance")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    base = [str(args.adb), "-s", args.serial]
    report = {"started_at_utc": datetime.now(timezone.utc).isoformat(),
              "device": args.serial, "origin": "pc_gateway" if args.gateway_fixture or args.board_port else "simulator",
              "fixture_state": not bool(args.board_port), "board_tested": False,
              "board_port": args.board_port, "independent_wireless_tested": False,
              "apk_sha256": hashlib.sha256(args.apk.read_bytes()).hexdigest(), "checks": []}
    latest_tree = None
    resources = ExitStack()
    if args.prototype_existing:
        report.update(origin="pc_prototype", fixture_state=None, existing_service_only=True)
    if args.prototype_fixture:
        report.update(origin="pc_prototype", fixture_state=True, model_simulated=True,
                      physical_phone_tested=False)

    def adb(*parts: str, timeout: float = 20) -> bytes:
        result = subprocess.run(base + list(parts), capture_output=True, timeout=timeout)
        if result.returncode and "swipe" in parts and b"INJECT_EVENTS" in result.stderr:
            # MuMu may reject input during a window transition. Retry once only
            # after verifying that this app still owns the focused window.
            focus = subprocess.run(base + ["shell", "dumpsys", "window"],
                                   capture_output=True, timeout=timeout)
            focused = next((line for line in focus.stdout.splitlines()
                            if b"mCurrentFocus=" in line), b"")
            if PACKAGE.encode() in focused:
                time.sleep(0.3)
                result = subprocess.run(base + list(parts), capture_output=True, timeout=timeout)
                report.setdefault("automation_notes", []).append("Retried one MuMu swipe after focused-window confirmation")
        if result.returncode:
            raise RuntimeError("ADB operation failed: " + result.stderr.decode("utf-8", "replace"))
        return result.stdout

    def dump() -> ET.Element:
        nonlocal latest_tree
        for attempt in range(3):
            try:
                status = adb("shell", "uiautomator", "dump", "--compressed", "/sdcard/ew-companion-ui.xml").decode("utf-8", "replace")
            except subprocess.TimeoutExpired:
                focus = adb("shell", "dumpsys", "window")
                focused = next((line for line in focus.splitlines() if b"mCurrentFocus=" in line), b"")
                if PACKAGE.encode() not in focused or attempt == 2:
                    raise
                report.setdefault("automation_notes", []).append(
                    "Retried UI snapshot timeout after confirming target app focus")
                continue
            if "dumped" in status:
                data = adb("exec-out", "cat", "/sdcard/ew-companion-ui.xml")
                tree = ET.fromstring(data)
                if not any(node.get("package") == PACKAGE for node in tree.iter("node")):
                    raise RuntimeError("Target app is not the observed Android UI")
                latest_tree = tree
                return tree
            time.sleep(0.3)
        raise RuntimeError("UI hierarchy could not be captured: " + status)

    def bounds(node: ET.Element) -> tuple[int, int, int, int]:
        values = [int(value) for value in re.findall(r"\d+", node.get("bounds", ""))]
        if len(values) != 4:
            raise RuntimeError("Missing UI bounds")
        return tuple(values)

    def find(description: str, *, direction: str = "down") -> ET.Element:
        for attempt in range(9):
            tree = dump()
            for node in tree.iter("node"):
                if node.get("content-desc") == description:
                    left, top, right, bottom = bounds(node)
                    if right > left and bottom > top:
                        return node
            scroll = next((node for node in tree.iter("node") if node.get("scrollable") == "true"), None)
            if scroll is None:
                break
            left, top, right, bottom = bounds(scroll)
            x = (left + right) // 2
            low, high = top + (bottom - top) * 3 // 4, top + (bottom - top) // 4
            start, end = (low, high) if direction == "down" else (high, low)
            adb("shell", "input", "touchscreen", "swipe", str(x), str(start), str(x), str(end), "280")
        raise AssertionError(f"Visible control not found: {description}")

    def click(description: str, *, direction: str = "down") -> None:
        node = find(description, direction=direction)
        if node.get("enabled") != "true":
            raise AssertionError(f"Control disabled: {description}")
        left, top, right, bottom = bounds(node)
        adb("shell", "input", "tap", str((left + right) // 2), str((top + bottom) // 2))

    def replace(description: str, text: str) -> None:
        node = find(description)
        left, top, right, bottom = bounds(node)
        adb("shell", "input", "tap", str((left + right) // 2), str((top + bottom) // 2))
        adb("shell", "input", "keyevent", "KEYCODE_MOVE_END")
        count = min(254, len(node.get("text", "")) + 2)
        adb("shell", "input", "keyevent", *(["KEYCODE_DEL"] * count))
        adb("shell", "input", "text", text.replace(" ", "%s"))

    def wait_text(description: str, fragment: str, *, direction: str = "down", timeout: float = 14) -> str:
        deadline = time.monotonic() + timeout
        last = ""
        while time.monotonic() < deadline:
            last = find(description, direction=direction).get("text", "")
            if fragment in last:
                return last
            time.sleep(0.15)
        raise AssertionError(f"Expected {fragment!r} in {description}; observed {last!r}")

    def check(name: str) -> None:
        report["checks"].append({"name": name, "passed": True})
        print("PASS " + name, flush=True)

    def capture(name: str) -> None:
        tree = dump()
        (args.output / (name + ".xml")).write_bytes(ET.tostring(tree, encoding="utf-8"))
        (args.output / (name + ".png")).write_bytes(adb("exec-out", "screencap", "-p"))

    try:
        if args.prototype_fixture:
            from test_mobile_prototype import SensitivitySerial
            from mobile_prototype_gateway import PrototypeBoard, PrototypeGateway
            from mobile_serial_gateway import SerialBroker
            transport = SensitivitySerial()
            server = PrototypeGateway(
                PrototypeBoard(SerialBroker(transport, timeout_s=.8, enable_sensitivity=True)),
                lambda text, state: "EXPLICIT MODEL FIXTURE; no real model", port=args.port,
                fixture_state=True)
            worker = threading.Thread(target=server.serve_forever,
                                      kwargs={"poll_interval": .05}, daemon=True)
            worker.start()
            def close_fixture():
                server.shutdown()
                server.server_close()
                worker.join(2)
            resources.callback(close_fixture)
        if adb("get-state").strip() != b"device":
            raise RuntimeError("Selected ADB target is not ready")
        adb("install", "-r", str(args.apk), timeout=60)
        adb("shell", "am", "force-stop", PACKAGE)
        adb("shell", "am", "start", "-W", "-n", PACKAGE + "/.MainActivity")
        wait_text("ew_connection", "未连接", direction="up")
        capture("01_initial")
        check("APK installation and cold start")
        if args.prototype_existing or args.prototype_fixture:
            from test_mobile_serial_gateway import Client
            probe = Client(("127.0.0.1", args.port))
            try:
                probe.send("ui-probe-hello", "hello")
                meta = probe.result("ui-probe-hello")["data"]
                if meta["origin"] != "pc_prototype" or meta["fixture_state"] != args.prototype_fixture:
                    raise AssertionError("Prototype source does not match selected test mode")
                report["fixture_state"] = args.prototype_fixture
                report["server_reported_physical_source"] = not args.prototype_fixture
            finally:
                probe.close()
            replace("ew_host", "10.0.2.2")
            replace("ew_port", str(args.port))
            click("ew_connect", direction="up")
            wait_text("ew_connection", "电脑转发原型", direction="up")
            wait_text("ew_origin", "模拟设备" if args.prototype_fixture else "真实开发板", direction="up")
            wait_text("ew_profile", "标准敏感度")
            check("Prototype provenance, state and standard sensitivity displayed")
            for description in ("ew_alert_soft", "ew_alert_strong"):
                if find(description).get("enabled") != "false":
                    raise AssertionError("Prototype must not enable actuator tests")
            click("ew_profile_cycle")
            wait_text("ew_action", "已应用")
            wait_text("ew_profile", "提前预警")
            check("Early sensitivity waits for serial acknowledgement and readback")
            click("ew_profile_walk")
            wait_text("ew_profile", "标准敏感度")
            check("Standard sensitivity restored through device readback")
            replace("ew_ask_text", "Reply only OK")
            click("ew_ask_send")
            wait_text("ew_reply", "模拟回复" if args.prototype_fixture else "MiMo", timeout=55)
            if args.prototype_fixture:
                wait_text("ew_reply", "EXPLICIT MODEL FIXTURE")
            check("Model reply displayed with accurate simulated/real source")
            capture("02_prototype_complete")
            adb("shell", "input", "keyevent", "KEYCODE_HOME")
            time.sleep(1)
            adb("shell", "am", "start", "-W", "-n", PACKAGE + "/.MainActivity")
            wait_text("ew_connection", "未连接", direction="up")
            check("Prototype background lifecycle closes app connection")
            click("ew_connect", direction="up")
            wait_text("ew_connection", "电脑转发原型", direction="up")
            check("Prototype manual reconnect succeeds")
            click("ew_disconnect", direction="up")
            report["passed"] = True
            return 0
        if args.board_port:
            with physical_board_gateway(args.port, args.board_port) as server:
                observations = [server.broker.query() for _ in range(10)]
                sequences = [value["snapshot_seq"] for value in observations]
                if not all(b > a for a, b in zip(sequences, sequences[1:])):
                    raise AssertionError("Physical snapshots do not advance")
                report["board_tested"] = True
                report["physical_snapshots"] = observations
                check("Ten fresh physical board snapshots with advancing sequences")
                replace("ew_host", "10.0.2.2")
                replace("ew_port", str(args.port))
                click("ew_connect", direction="up")
                wait_text("ew_connection", "已连接", direction="up")
                wait_text("ew_origin", "PC 串口网关", direction="up")
                wait_text("ew_updated", "网关接收")
                wait_text("ew_profile", "未提供")
                check("Android receives real board state with explicit gateway provenance")
                # Empty measurements must remain empty; moving measurements may
                # legitimately change while the accessibility tree is captured.
                if all(value["range_m"] is None for value in observations):
                    wait_text("ew_range", "—")
                if all(value["speed_kmh"] is None for value in observations):
                    wait_text("ew_speed", "—")
                capture("02_physical_board_state")
                check("Absent board measurements and profile are not fabricated")
                for description in ("ew_alert_soft", "ew_alert_strong", "ew_profile_walk",
                                    "ew_profile_cycle", "ew_ask_text", "ew_ask_send"):
                    if find(description).get("enabled") != "false":
                        raise AssertionError("Read-only control unexpectedly enabled: " + description)
                check("Unavailable actuator, configuration and model actions remain disabled")
                click("ew_refresh", direction="up")
                wait_text("ew_connection", "已连接", direction="up")
                check("Explicit refresh remains connected to physical board")
                adb("shell", "input", "keyevent", "KEYCODE_HOME")
                # Let the Home transition finish and Android dispatch onStop;
                # immediately reopening can legitimately cancel backgrounding.
                time.sleep(1.0)
                adb("shell", "am", "start", "-W", "-n", PACKAGE + "/.MainActivity")
                wait_text("ew_connection", "未连接", direction="up")
                check("Background closes the real gateway session")
                click("ew_connect", direction="up")
                wait_text("ew_connection", "已连接", direction="up")
                wait_text("ew_origin", "PC 串口网关", direction="up")
                capture("03_physical_reconnected")
                check("Foreground manual reconnect to physical board")
            wait_text("ew_connection", "连接异常", direction="up")
            capture("04_physical_gateway_stopped")
            check("Gateway shutdown is visible without resetting board")
            report["passed"] = True
            return 0
        if args.gateway_fixture:
            with snapshot_gateway_fixture(args.port, args.output):
                replace("ew_host", "10.0.2.2")
                replace("ew_port", str(args.port))
                click("ew_connect", direction="up")
                wait_text("ew_connection", "已连接", direction="up")
                wait_text("ew_origin", "PC 串口网关", direction="up")
                wait_text("ew_range", "8.8")
                wait_text("ew_speed", "22.0")
                check("Gateway handshake and production C fixture serialization across real TCP")
                wait_text("ew_updated", "网关接收")
                wait_text("ew_radar", "正常")
                capture("02_gateway_state")
                check("Device monotonic time is distinct from gateway reception time")
                for description in ("ew_alert_soft", "ew_alert_strong", "ew_profile_walk",
                                    "ew_profile_cycle", "ew_ask_text", "ew_ask_send"):
                    if find(description).get("enabled") != "false":
                        raise AssertionError("Read-only control unexpectedly enabled: " + description)
                check("All unsupported gateway mutations and model controls remain disabled")
                click("ew_refresh", direction="up")
                wait_text("ew_range", "8.8")
                check("Gateway state refresh reads a fresh C snapshot")
            wait_text("ew_connection", "连接异常", direction="up")
            check("Gateway transport shutdown is visible")
            with snapshot_gateway_fixture(args.port, args.output, waiting=True):
                click("ew_connect", direction="up")
                wait_text("ew_connection", "已连接", direction="up")
                wait_text("ew_range", "—")
                wait_text("ew_speed", "—")
                wait_text("ew_radar", "等待")
                wait_text("ew_profile", "未提供")
                capture("03_gateway_waiting")
                check("Missing radar samples and absent profile never become fabricated numbers")
            report["passed"] = True
            return 0
        # The legacy ADB dumper needs an idle accessibility window. A 3-second
        # subscription cadence permits that window without disabling updates.
        with running_simulator(port=args.port, delay_ms=6000, subscription_interval_s=3):
            replace("ew_host", "10.0.2.2")
            replace("ew_port", str(args.port))
            click("ew_connect", direction="up")
            wait_text("ew_connection", "已连接", direction="up")
            wait_text("ew_origin", "本地模拟器", direction="up")
            wait_text("ew_range", "12.4")
            check("Simulator handshake, source label and real socket state")
            click("ew_refresh")
            wait_text("ew_range", "12.4")
            capture("02_connected_state")
            check("Explicit state refresh")
            click("ew_alert_strong")
            wait_text("ew_action", "尚未执行完成", timeout=8)
            capture("03_queued")
            wait_text("ew_action", "已应用", timeout=10)
            capture("04_applied")
            check("Queued and applied are distinct UI states")
            click("ew_profile_cycle", direction="up")
            wait_text("ew_action", "骑行")
            check("Profile change confirmed by simulated device")
            replace("ew_ask_text", "How does warning work?")
            click("ew_ask_send")
            wait_text("ew_reply", "未调用真实模型", timeout=16)
            capture("05_simulated_reply")
            check("Question and explicitly simulated reply")
            # Press Home rather than changing or closing any other Android app.
            adb("shell", "input", "keyevent", "KEYCODE_HOME")
            time.sleep(0.3)
            adb("shell", "am", "start", "-W", "-n", PACKAGE + "/.MainActivity")
            wait_text("ew_connection", "未连接", direction="up")
            check("Background lifecycle closes connection; foreground requires manual connect")
            click("ew_connect", direction="up")
            wait_text("ew_connection", "已连接", direction="up")
            check("Manual reconnect after background")
        wait_text("ew_connection", "连接异常", direction="up")
        capture("06_server_disconnect")
        check("Server loss becomes a visible connection error")
        click("ew_connect", direction="up")
        wait_text("ew_connection", "连接异常", direction="up", timeout=12)
        check("Unavailable server fails without hanging UI")
        with running_simulator(port=args.port, delay_ms=150, subscription_interval_s=3):
            click("ew_connect", direction="up")
            wait_text("ew_connection", "已连接", direction="up")
            wait_text("ew_range", "12.4")
            capture("07_reconnected")
            check("Reconnect after service restart")
        report["passed"] = True
        return 0
    except (OSError, RuntimeError, AssertionError, subprocess.SubprocessError, ET.ParseError) as exc:
        report["passed"] = False
        report["error"] = str(exc)
        print("FAIL " + str(exc), flush=True)
        try:
            capture("failure")
        except Exception:
            pass
        return 1
    finally:
        resources.close()
        report["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
        (args.output / "acceptance.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
