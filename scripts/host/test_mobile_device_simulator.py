#!/usr/bin/env python3
"""Real-socket protocol, concurrency and fault regressions; standard library only."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
import json
import socket
import time
import unittest

from mobile_device_simulator import MAX_MESSAGE_BYTES, MobileDeviceSimulator, running_simulator


class Client:
    def __init__(self, address: tuple[str, int]):
        self.socket = socket.create_connection(address, timeout=1)
        self.buffer = bytearray()

    def close(self) -> None:
        self.socket.close()

    def send(self, request_id: str, operation: str, args: dict | None = None, **extra) -> None:
        value = {"v": 1, "id": request_id, "op": operation, "args": args or {}}
        value.update(extra)
        self.raw(json.dumps(value, ensure_ascii=False).encode("utf-8") + b"\n")

    def raw(self, value: bytes) -> None:
        self.socket.sendall(value)

    def read(self, timeout: float = 1) -> dict | None:
        self.socket.settimeout(timeout)
        while b"\n" not in self.buffer:
            chunk = self.socket.recv(4096)
            if not chunk:
                return None
            self.buffer.extend(chunk)
        end = self.buffer.index(10)
        line = bytes(self.buffer[:end])
        del self.buffer[:end + 1]
        if len(line) > MAX_MESSAGE_BYTES:
            raise AssertionError("server sent an oversized message")
        return json.loads(line)

    def result(self, request_id: str, timeout: float = 1) -> dict:
        deadline = time.monotonic() + timeout
        while True:
            value = self.read(max(0.01, deadline - time.monotonic()))
            if value is None:
                raise AssertionError("unexpected EOF waiting for result")
            if value.get("id") == request_id and value["type"] == "result":
                return value
            if time.monotonic() >= deadline:
                raise AssertionError("no matching result")


def wait_until(predicate, timeout: float = 1) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError("condition did not become true before timeout")


class SimulatorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)

    def server(self, **options):
        defaults = {"delay_ms": 20, "subscription_interval_s": 0.05,
                    "idle_timeout_s": 3, "frame_timeout_s": 0.5}
        defaults.update(options)
        return self.stack.enter_context(running_simulator(**defaults))

    def client(self, server):
        client = Client(server.address)
        self.stack.callback(client.close)
        return client

    def assert_error(self, value, code: str):
        self.assertIsNotNone(value)
        self.assertEqual(value["type"], "result")
        self.assertFalse(value["ok"])
        self.assertEqual(value["error"]["code"], code)

    def test_hello_state_and_config_are_final_simulator_results(self):
        client = self.client(self.server())
        client.send("hello", "hello")
        hello = client.read()
        self.assertEqual((hello["type"], hello["stage"]), ("result", "applied"))
        self.assertEqual(hello["data"]["origin"], "simulator")
        self.assertEqual(hello["data"]["device_id"], "ew-sim-001")
        self.assertEqual(hello["data"]["max_message_bytes"], MAX_MESSAGE_BYTES)
        self.assertEqual(set(hello["data"]["capabilities"]),
                         {"get_state", "subscribe_state", "test_alert", "get_config", "set_profile", "ask"})
        client.send("state", "get_state")
        state = client.read()["data"]
        self.assertEqual(state["origin"], "simulator")
        self.assertEqual((state["connected"], state["radar_link"]), (True, "ok"))
        self.assertEqual((state["range_m"], state["speed_kmh"]), (12.4, 18.0))
        self.assertEqual((state["alert_level"], state["profile"]), ("none", "walk"))
        self.assertIs(type(state["updated_ms"]), int)
        client.send("config", "get_config")
        self.assertEqual(client.read()["data"]["profile"], "walk")

    def test_profile_applies_and_is_visible_after_reconnection(self):
        server = self.server()
        first = self.client(server)
        first.send("profile", "set_profile", {"profile": "cycle"})
        self.assertEqual(first.read()["data"]["profile"], "cycle")
        first.close()
        wait_until(lambda: server.active_connections == 0)
        second = self.client(server)
        second.send("config", "get_config")
        self.assertEqual(second.read()["data"]["profile"], "cycle")

    def test_queued_alert_result_is_delayed_and_alert_automatically_expires(self):
        client = self.client(self.server(delay_ms=100))
        client.send("alert", "test_alert", {"level": "strong", "duration_ms": 80})
        accepted = client.read()
        self.assertEqual(accepted, {"v": 1, "id": "alert", "type": "accepted",
                                    "ok": True, "stage": "queued"})
        with self.assertRaises(socket.timeout):
            client.read(0.025)
        client.send("still-queued", "get_state")
        self.assertEqual(client.result("still-queued")["data"]["alert_level"], "none")
        applied = client.result("alert")
        self.assertEqual(applied["stage"], "applied")
        self.assertEqual(applied["data"]["state"]["alert_level"], "strong")
        self.assertEqual(applied["data"]["event_id"], applied["data"]["state"]["event_id"])
        time.sleep(0.15)
        client.send("restored", "get_state")
        self.assertEqual(client.read()["data"]["alert_level"], "none")

    def test_ask_always_discloses_simulation_and_reply_stays_bounded(self):
        client = self.client(self.server())
        for index, text in enumerate(("现在有没有车", "a" + "\x01" * 1100)):
            request_id = "ask-" + str(index)
            client.send(request_id, "ask", {"text": text})
            self.assertEqual(client.read()["type"], "accepted")
            result = client.result(request_id)
            self.assertEqual(result["data"]["origin"], "simulator")
            self.assertIn("模拟回复", result["data"]["reply"])
            self.assertIn("未调用真实模型", result["data"]["reply"])

    def test_bad_json_utf8_duplicate_keys_and_nan_do_not_break_next_request(self):
        client = self.client(self.server())
        cases = [(b'{bad json}\n', "bad_json"), (b'\xff\n', "invalid_utf8"),
                 (b'{"v":1,"v":1}\n', "bad_json"),
                 (b'{"v":NaN}\n', "bad_json"), (b'[]\n', "invalid_request")]
        for wire, code in cases:
            client.raw(wire)
            self.assert_error(client.read(), code)
        client.send("recovery", "hello")
        self.assertTrue(client.read()["ok"])

    def test_wrong_version_and_boolean_version_are_rejected(self):
        client = self.client(self.server())
        for version in (2, True, "1"):
            client.send("version", "hello", v=version)
            self.assert_error(client.read(), "unsupported_version")

    def test_exact_line_size_is_accepted_then_oversize_line_is_closed(self):
        client = self.client(self.server())
        line = json.dumps({"v": 1, "id": "boundary", "op": "hello", "args": {}}).encode()
        client.raw(line + b" " * (MAX_MESSAGE_BYTES - len(line)) + b"\n")
        self.assertTrue(client.read()["ok"])
        client.raw(b" " * (MAX_MESSAGE_BYTES + 1) + b"\n")
        self.assert_error(client.read(), "message_too_large")
        self.assertIsNone(client.read())

    def test_oversize_frame_without_newline_cannot_grow_buffer_unbounded(self):
        client = self.client(self.server())
        client.raw(b"x" * (MAX_MESSAGE_BYTES + 1))
        self.assert_error(client.read(), "message_too_large")
        self.assertIsNone(client.read())

    def test_arguments_and_unsupported_operation_are_explicit_errors(self):
        client = self.client(self.server())
        cases = [("set_profile", {"profile": "drive"}),
                 ("subscribe_state", {"enabled": 1}),
                 ("test_alert", {"level": "emergency", "duration_ms": True}),
                 ("test_alert", {"level": "soft", "duration_ms": 5001}),
                 ("test_alert", {"level": "loud", "duration_ms": 100}),
                 ("ask", {"text": " "}), ("ask", {"text": "a" * 2049}),
                 ("ask", {"text": "\ud800"}),
                 ("hello", {"extra": 1})]
        for index, (operation, args) in enumerate(cases):
            # ensure_ascii keeps the deliberately invalid surrogate on the wire.
            value = {"v": 1, "id": "bad-" + str(index), "op": operation, "args": args}
            client.raw(json.dumps(value).encode() + b"\n")
            self.assert_error(client.read(), "invalid_args")
        client.send("events", "get_events")
        self.assert_error(client.read(), "unsupported")
        client.raw(b'{"v":1,"id":"args-list","op":"hello","args":[]}\n')
        self.assert_error(client.read(), "invalid_request")
        client.raw(b'{"v":1,"id":"","op":"hello","args":{}}\n')
        self.assert_error(client.read(), "invalid_request")
        client.raw(b'{"v":1,"id":"bad-op","op":"\\ud800","args":{}}\n')
        self.assert_error(client.read(), "invalid_request")

    def test_incomplete_frame_timeout_closes_and_cleans_up_connection(self):
        server = self.server(frame_timeout_s=0.1)
        client = self.client(server)
        client.raw(b'{"v":1')
        self.assert_error(client.read(), "timeout")
        self.assertIsNone(client.read())
        wait_until(lambda: server.active_connections == 0)

    def test_idle_timeout_is_bounded(self):
        client = self.client(self.server(idle_timeout_s=0.12))
        self.assert_error(client.read(), "timeout")
        self.assertIsNone(client.read())

    def test_duplicate_final_request_does_not_repeat_profile_side_effect(self):
        client = self.client(self.server())
        client.send("same", "set_profile", {"profile": "cycle"})
        first = client.read()
        client.send("before", "get_state")
        event_id = client.read()["data"]["event_id"]
        client.send("same", "set_profile", {"profile": "cycle"})
        self.assertEqual(client.read(), first)
        client.send("after", "get_state")
        self.assertEqual(client.read()["data"]["event_id"], event_id)

    def test_pending_duplicate_and_reconnect_replay_have_one_side_effect(self):
        server = self.server(delay_ms=100)
        first, second = self.client(server), self.client(server)
        args = {"level": "soft", "duration_ms": 500}
        first.send("shared", "test_alert", args)
        self.assertEqual(first.read()["type"], "accepted")
        second.send("shared", "test_alert", args)
        self.assertEqual(second.read()["type"], "accepted")
        result = first.result("shared")
        self.assertEqual(second.result("shared"), result)
        first.close()
        second.close()
        wait_until(lambda: server.active_connections == 0)
        third = self.client(server)
        third.send("shared", "test_alert", args)
        self.assertEqual(third.read(), result)
        third.send("state", "get_state")
        self.assertEqual(third.read()["data"]["event_id"], result["data"]["event_id"])

    def test_same_id_different_arguments_cannot_replace_pending_action(self):
        client = self.client(self.server(delay_ms=100))
        client.send("conflict", "test_alert", {"level": "soft", "duration_ms": 500})
        self.assertEqual(client.read()["type"], "accepted")
        client.send("conflict", "test_alert", {"level": "emergency", "duration_ms": 500})
        self.assert_error(client.read(), "id_conflict")
        self.assertEqual(client.result("conflict")["data"]["state"]["alert_level"], "soft")
        client.send("conflict", "get_state")
        self.assert_error(client.read(), "id_conflict")

    def test_subscription_events_are_ordered_disable_fenced_and_disconnect_cleaned(self):
        server = self.server(idle_timeout_s=0.14)
        client = self.client(server)
        client.send("on", "subscribe_state", {"enabled": True})
        self.assertTrue(client.result("on")["data"]["enabled"])
        first, second = client.read(), client.read()
        for event in (first, second):
            self.assertEqual((event["type"], event["event"], event["source"]),
                             ("event", "state", "simulator"))
            self.assertEqual(event["data"]["origin"], "simulator")
        self.assertGreater(second["event_id"], first["event_id"])
        client.send("off", "subscribe_state", {"enabled": False})
        self.assertFalse(client.result("off")["data"]["enabled"])
        self.assertEqual(server.subscriber_count, 0)
        with self.assertRaises(socket.timeout):
            client.read(0.08)
        client.send("again", "subscribe_state", {"enabled": True})
        client.result("again")
        client.close()
        wait_until(lambda: server.subscriber_count == 0 and server.active_connections == 0)

    def test_subscription_retry_on_replacement_connection_resubscribes(self):
        server = self.server()
        first = self.client(server)
        first.send("subscription", "subscribe_state", {"enabled": True})
        first.result("subscription")
        first.close()
        second = self.client(server)
        second.send("subscription", "subscribe_state", {"enabled": True})
        self.assertTrue(second.result("subscription")["ok"])
        self.assertEqual(second.read()["type"], "event")

    def test_cached_cancel_on_replacement_connection_stops_events_before_ack(self):
        server = self.server()
        first = self.client(server)
        first.send("cancel", "subscribe_state", {"enabled": False})
        canceled = first.result("cancel")
        first.close()
        wait_until(lambda: server.active_connections == 0)
        second = self.client(server)
        second.send("new-subscription", "subscribe_state", {"enabled": True})
        second.result("new-subscription")
        self.assertEqual(second.read()["type"], "event")
        second.send("cancel", "subscribe_state", {"enabled": False})
        self.assertEqual(second.result("cancel"), canceled)
        self.assertEqual(server.subscriber_count, 0)
        with self.assertRaises(socket.timeout):
            second.read(0.12)

    def test_disconnect_during_queued_work_preserves_one_result_for_retry(self):
        server = self.server(delay_ms=150)
        first = self.client(server)
        args = {"level": "soft", "duration_ms": 500}
        first.send("retry", "test_alert", args)
        self.assertEqual(first.read()["type"], "accepted")
        first.close()
        wait_until(lambda: server.active_connections == 0)
        second = self.client(server)
        second.send("retry", "test_alert", args)
        self.assertEqual(second.read()["type"], "accepted")
        result = second.result("retry")
        self.assertTrue(result["ok"])
        self.assertEqual(result["data"]["event_id"], 1)

    def test_drop_fault_and_reconnect_are_repeatable(self):
        server = self.server(drop_after_requests=2)
        first = self.client(server)
        first.send("first", "hello")
        self.assertTrue(first.read()["ok"])
        first.send("drop", "get_state")
        self.assertIsNone(first.read())
        second = self.client(server)
        second.send("reconnected", "hello")
        self.assertTrue(second.read()["ok"])

    def test_pending_work_and_cache_have_bounded_admission(self):
        client = self.client(self.server(delay_ms=100, max_pending=1))
        client.send("one", "ask", {"text": "test"})
        self.assertEqual(client.read()["type"], "accepted")
        client.send("two", "test_alert", {"level": "soft", "duration_ms": 50})
        self.assert_error(client.read(), "busy")
        self.assertTrue(client.result("one")["ok"])
        client2 = self.client(self.server(delay_ms=100, cache_capacity=1))
        client2.send("pending", "ask", {"text": "test"})
        self.assertEqual(client2.read()["type"], "accepted")
        client2.send("too-many", "get_state")
        self.assert_error(client2.read(), "busy")
        self.assertTrue(client2.result("pending")["ok"])

    def test_completed_cache_is_bounded_and_expiration_allows_id_reuse(self):
        server = self.server(cache_capacity=2, cache_ttl_s=0.08)
        client = self.client(server)
        for index in range(5):
            client.send("id-" + str(index), "get_state")
            self.assertTrue(client.read()["ok"])
        self.assertLessEqual(len(server._records), 2)
        client.send("expires", "set_profile", {"profile": "cycle"})
        client.read()
        time.sleep(0.11)
        client.send("expires", "set_profile", {"profile": "walk"})
        self.assertEqual(client.read()["data"]["profile"], "walk")

    def test_concurrent_connections_share_state_without_corrupting_json(self):
        server = self.server()

        def worker(index):
            client = Client(server.address)
            try:
                profile = "walk" if index % 2 else "cycle"
                client.send("worker-" + str(index), "set_profile", {"profile": profile})
                return client.read()
            finally:
                client.close()

        with ThreadPoolExecutor(max_workers=6) as pool:
            results = list(pool.map(worker, range(6)))
        self.assertTrue(all(value["ok"] for value in results))
        client = self.client(server)
        client.send("count", "get_state")
        self.assertEqual(client.read()["data"]["event_id"], 6)

    def test_shutdown_interrupts_long_delay_without_lingering_workers(self):
        started = time.monotonic()
        with running_simulator(delay_ms=30000) as server:
            client = Client(server.address)
            try:
                client.send("long", "ask", {"text": "test"})
                self.assertEqual(client.read()["type"], "accepted")
            finally:
                client.close()
        self.assertLess(time.monotonic() - started, 2)
        self.assertEqual(server.active_connections, 0)

    def test_public_binding_and_invalid_server_parameters_are_refused(self):
        for host in ("0.0.0.0", "192.0.2.1", "::", "example.com"):
            with self.assertRaises(ValueError):
                MobileDeviceSimulator(host, 0)
        for options in ({"delay_ms": -1}, {"delay_ms": 30001}, {"cache_capacity": 0},
                        {"frame_timeout_s": float("nan")}, {"max_clients": True}):
            with self.assertRaises(ValueError):
                MobileDeviceSimulator(port=0, **options)


if __name__ == "__main__":
    unittest.main(verbosity=2)
