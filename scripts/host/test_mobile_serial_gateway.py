#!/usr/bin/env python3
"""Real TCP plus fake UART tests; no board, model, pyserial or GUI is needed."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
import json
import re
import socket
import threading
import time
import unittest

from mobile_serial_gateway import (
    CAPABILITIES, MAX_MESSAGE_BYTES, PREFIX, GatewayError, MobileSerialGateway,
    SerialBroker, running_gateway, validate_snapshot,
)


def board_snapshot(request_id: str, sequence: int = 1) -> dict:
    return {"v": 1, "id": request_id, "origin": "device", "connected": True,
            "radar_link": "ok", "range_m": 12.4, "speed_kmh": 18.0,
            "alert_level": "soft", "profile": None, "event_id": 41,
            "updated_ms": 1000 + sequence * 10, "clock": "device_monotonic",
            "snapshot_seq": sequence, "radar_error": 0}


def frame(value: dict) -> bytes:
    return PREFIX + json.dumps(value, separators=(",", ":")).encode() + b"\n"


class FakeSerial:
    """Fragmenting transport with explicit firmware-response injection."""
    def __init__(self, factory=None, chunk_size: int = 17):
        self.timeout = 0.01
        self.factory = factory
        self.chunk_size = chunk_size
        self.writes: list[bytes] = []
        self.buffer = bytearray()
        self.condition = threading.Condition()
        self.closed = False
        self.fail = False
        self.short_write = False

    def write(self, wire: bytes) -> int:
        with self.condition:
            if self.closed or self.fail:
                raise OSError("fake disconnected")
            self.writes.append(wire)
            if self.short_write:
                return len(wire) - 1
            match = re.fullmatch(rb"@snapshot ([A-Za-z0-9_-]{1,48})\r\n", wire)
            if not match:
                raise AssertionError("Gateway transmitted a command other than bounded @snapshot")
            request_id = match.group(1).decode()
            sequence = len(self.writes)
            value = self.factory(request_id, sequence) if self.factory else frame(board_snapshot(request_id, sequence))
            if value is not None:
                self.buffer.extend(value)
            self.condition.notify_all()
            return len(wire)

    def read(self, size: int) -> bytes:
        with self.condition:
            if not self.buffer and not self.closed:
                self.condition.wait(self.timeout)
            if self.closed or self.fail:
                raise OSError("fake disconnected")
            count = min(size, self.chunk_size, len(self.buffer))
            result = bytes(self.buffer[:count])
            del self.buffer[:count]
            return result

    def close(self) -> None:
        with self.condition:
            self.closed = True
            self.condition.notify_all()


class Client:
    def __init__(self, address):
        self.socket = socket.create_connection(address, timeout=2)
        self.buffer = bytearray()

    def close(self):
        self.socket.close()

    def send(self, request_id: str, operation: str, args=None):
        self.socket.sendall(json.dumps({"v": 1, "id": request_id, "op": operation,
                                        "args": args or {}}).encode() + b"\n")

    def read(self, timeout=2):
        self.socket.settimeout(timeout)
        while b"\n" not in self.buffer:
            data = self.socket.recv(4096)
            if not data:
                return None
            self.buffer.extend(data)
        index = self.buffer.index(10)
        line = bytes(self.buffer[:index])
        del self.buffer[:index + 1]
        assert len(line) <= MAX_MESSAGE_BYTES
        return json.loads(line)

    def result(self, request_id: str, timeout=2):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            value = self.read(max(0.01, deadline - time.monotonic()))
            if value is None:
                raise AssertionError("EOF waiting for result")
            if value.get("id") == request_id:
                return value
        raise AssertionError("No result")


class GatewayTests(unittest.TestCase):
    def test_no_frame_is_a_device_fault_state_not_a_transport_failure(self):
        raw = board_snapshot("q", 1)
        raw.update(radar_link="no_frame", range_m=None, speed_kmh=None)
        parsed = validate_snapshot(raw, "q")
        self.assertEqual(parsed["radar_link"], "no_frame")
        self.assertIsNone(parsed["range_m"])
        self.assertIsNone(parsed["speed_kmh"])
        self.assertTrue(parsed["connected"])

    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)

    def broker(self, transport=None, **options):
        broker = SerialBroker(transport or FakeSerial(), **options)
        self.stack.callback(broker.close)
        return broker

    def server(self, transport=None, **options):
        options.setdefault("subscription_interval_s", 0.04)
        options.setdefault("broker_options", {"timeout_s": 0.2})
        return self.stack.enter_context(running_gateway(transport or FakeSerial(), **options))

    def client(self, server):
        client = Client(server.address)
        self.stack.callback(client.close)
        return client

    def assert_error(self, value, code):
        self.assertIsNotNone(value)
        self.assertFalse(value["ok"])
        self.assertEqual(value["error"]["code"], code)

    def test_broker_has_one_serial_owner_and_fetches_fresh_snapshots(self):
        transport = FakeSerial()
        broker = self.broker(transport)
        first, second = broker.query(), broker.query()
        self.assertEqual(first["origin"], "pc_gateway")
        self.assertEqual(first["event_id"], second["event_id"])
        self.assertGreater(second["snapshot_seq"], first["snapshot_seq"])
        self.assertEqual(second["updated_ms"], 1020)
        self.assertGreater(first["received_at_ms"], 1_700_000_000_000)
        ids = [re.fullmatch(rb"@snapshot (gw_[0-9a-f]{16}_[0-9]+)\r\n", wire).group(1)
               for wire in transport.writes]
        self.assertEqual(ids[0].rsplit(b"_", 1)[1], b"1")
        self.assertEqual(ids[1].rsplit(b"_", 1)[1], b"2")
        self.assertEqual(ids[0].rsplit(b"_", 1)[0], ids[1].rsplit(b"_", 1)[0])
        self.assertTrue(all(len(request_id) <= 48 for request_id in ids))

    def test_old_broker_response_cannot_be_marked_fresh_after_reopening(self):
        previous_transport = FakeSerial()
        previous = self.broker(previous_transport)
        previous.query()
        previous_id = re.fullmatch(rb"@snapshot (.+)\r\n", previous_transport.writes[0]).group(1).decode()
        previous.close()
        # Driver RX may retain data from the previous process/Serial object.
        old_wire = frame(board_snapshot(previous_id, 9999))
        transport = FakeSerial()
        transport.buffer.extend(old_wire)
        current = self.broker(transport)
        self.assertEqual(current.query()["snapshot_seq"], 1)
        current_id = re.fullmatch(rb"@snapshot (.+)\r\n", transport.writes[0]).group(1).decode()
        self.assertNotEqual(current_id, previous_id)
        stale_only = FakeSerial(lambda *_: None)
        stale_only.buffer.extend(old_wire)
        current = self.broker(stale_only, timeout_s=0.07)
        with self.assertRaises(GatewayError) as caught:
            current.query()
        self.assertEqual(caught.exception.code, "timeout")

    def test_prefix_recovers_from_binary_noise_wrong_ids_and_fragmentation(self):
        def response(request_id, sequence):
            return (b"secret ordinary log\xff\x00" * 3000 + frame(board_snapshot("old", 99))
                    + b"nsh> " + frame(board_snapshot(request_id, sequence)))
        value = self.broker(FakeSerial(response, chunk_size=256), timeout_s=1).query()
        self.assertEqual(value["snapshot_seq"], 1)
        self.assertNotIn("secret", json.dumps(value))

    def test_oversized_snapshot_does_not_prevent_next_valid_prefix(self):
        def response(request_id, sequence):
            return PREFIX + b"x" * (MAX_MESSAGE_BYTES + 100) + frame(board_snapshot(request_id, sequence))
        value = self.broker(FakeSerial(response, chunk_size=256)).query()
        self.assertEqual(value["snapshot_seq"], 1)

    def test_wrong_id_cannot_be_used_as_fresh_state(self):
        broker = self.broker(FakeSerial(lambda *_: frame(board_snapshot("wrong"))), timeout_s=0.07)
        with self.assertRaises(GatewayError) as caught:
            broker.query()
        self.assertEqual(caught.exception.code, "timeout")

    def test_malformed_snapshot_never_becomes_online(self):
        server = self.server(FakeSerial(lambda *_: PREFIX + b"{bad JSON}\n"))
        client = self.client(server)
        client.send("h", "hello")
        self.assert_error(client.result("h"), "unsupported_firmware")

    def test_snapshot_types_null_measurements_and_device_clock(self):
        raw = board_snapshot("q")
        raw.update(range_m=None, speed_kmh=None, radar_link="waiting")
        parsed = validate_snapshot(raw, "q")
        self.assertIsNone(parsed["range_m"])
        self.assertIsNone(parsed["speed_kmh"])
        self.assertEqual(parsed["clock"], "device_monotonic")
        self.assertEqual(parsed["updated_ms"], 1010)
        for field, invalid in (("range_m", True), ("speed_kmh", -1), ("speed_kmh", float("nan")),
                               ("range_m", 10**1000), ("connected", 1), ("v", True),
                               ("event_id", True), ("snapshot_seq", 0), ("updated_ms", 2**32),
                               ("event_id", 2**32), ("radar_error", -1), ("profile", "walk"),
                               ("radar_link", []), ("alert_level", {})):
            with self.subTest(field=field, invalid=repr(invalid)[:30]):
                wrong = dict(raw)
                wrong[field] = invalid
                with self.assertRaises(GatewayError):
                    validate_snapshot(wrong, "q")

    def test_partial_old_frame_does_not_poison_next_query(self):
        def response(request_id, sequence):
            return PREFIX + b'{"v":' if sequence == 1 else frame(board_snapshot(request_id, sequence))
        broker = self.broker(FakeSerial(response), timeout_s=0.07)
        with self.assertRaises(GatewayError) as caught:
            broker.query()
        self.assertEqual(caught.exception.code, "timeout")
        self.assertEqual(broker.query()["snapshot_seq"], 2)

    def test_duplicate_json_keys_and_nan_are_rejected(self):
        for payload in (b'{"id":"gw_1","id":"gw_1"}', b'{"id":"gw_1","range_m":NaN}'):
            broker = self.broker(FakeSerial(lambda *_: PREFIX + payload + b"\n"), timeout_s=0.07)
            with self.assertRaises(GatewayError) as caught:
                broker.query()
            self.assertIn(caught.exception.code, ("timeout", "unsupported_firmware"))

    def test_stale_sequence_rejected_and_restart_requires_new_session(self):
        def response(request_id, sequence):
            value = board_snapshot(request_id, sequence)
            if sequence == 2:
                value["snapshot_seq"] = 1
            return frame(value)
        broker = self.broker(FakeSerial(response))
        broker.query()
        with self.assertRaises(GatewayError) as caught:
            broker.query()
        self.assertEqual(caught.exception.code, "stale_snapshot")
        self.assertEqual(broker.query()["snapshot_seq"], 3)
        def reboot_response(request_id, sequence):
            value = board_snapshot(request_id, sequence)
            if sequence >= 2:
                value.update(snapshot_seq=sequence - 1, updated_ms=sequence)
            return frame(value)
        broker = self.broker(FakeSerial(reboot_response))
        broker.query()
        with self.assertRaises(GatewayError) as caught:
            broker.query()
        self.assertEqual(caught.exception.code, "device_restarted")
        self.assertEqual(broker.query()["snapshot_seq"], 2)

    def test_serial_disconnect_and_short_write_are_explicit_failures(self):
        for short in (False, True):
            transport = FakeSerial()
            transport.short_write = short
            transport.fail = not short
            broker = self.broker(transport)
            with self.assertRaises(GatewayError) as caught:
                broker.query()
            self.assertEqual(caught.exception.code, "not_connected")

    def test_pending_queries_have_bounded_admission_and_timeout(self):
        transport = FakeSerial(lambda *_: None)
        broker = self.broker(transport, timeout_s=0.12, max_pending=1)
        with ThreadPoolExecutor(max_workers=3) as executor:
            first = executor.submit(broker.query)
            deadline = time.monotonic() + 1
            while not transport.writes and time.monotonic() < deadline:
                time.sleep(0.001)
            second = executor.submit(broker.query)
            time.sleep(0.01)
            with self.assertRaises(GatewayError) as caught:
                broker.query()
            self.assertEqual(caught.exception.code, "busy")
            for future in (first, second):
                with self.assertRaises(GatewayError):
                    future.result()
        self.assertLessEqual(len(transport.writes), 2)

    def test_hello_advertises_read_only_after_fresh_board_response(self):
        transport = FakeSerial()
        client = self.client(self.server(transport))
        client.send("h", "hello")
        hello = client.result("h")
        self.assertEqual(hello["data"]["origin"], "pc_gateway")
        self.assertTrue(hello["data"]["read_only"])
        self.assertEqual(hello["data"]["capabilities"], CAPABILITIES)
        self.assertEqual(len(transport.writes), 1)
        client.send("s", "get_state")
        state = client.result("s")["data"]
        self.assertEqual(state["snapshot_seq"], 2)
        self.assertEqual(state["event_id"], 41)
        self.assertEqual(state["origin"], "pc_gateway")

    def test_silent_board_never_gets_successful_hello(self):
        client = self.client(self.server(FakeSerial(lambda *_: None)))
        client.send("h", "hello")
        self.assert_error(client.result("h"), "timeout")

    def test_mutating_operations_and_unknown_args_never_reach_uart(self):
        transport = FakeSerial()
        client = self.client(self.server(transport))
        for operation in ("test_alert", "set_profile", "ask", "get_config", "raw", "get_events"):
            client.send(operation, operation)
            self.assert_error(client.result(operation), "unsupported")
        for operation, args in (("get_state", {"raw": "@alert none"}),
                                ("subscribe_state", {"enabled": 1}),
                                ("hello", {"extra": True})):
            client.send("bad" + operation, operation, args)
            self.assert_error(client.result("bad" + operation), "invalid_args")
        self.assertEqual(transport.writes, [])

    def test_repeat_read_is_fresh_while_id_conflict_is_rejected(self):
        client = self.client(self.server())
        client.send("same", "get_state")
        first = client.result("same")["data"]
        client.send("same", "get_state")
        second = client.result("same")["data"]
        self.assertGreater(second["snapshot_seq"], first["snapshot_seq"])
        client.send("same", "hello")
        self.assert_error(client.result("same"), "id_conflict")

    def test_subscribe_cancel_fence_and_replacement_connection(self):
        server = self.server()
        client = self.client(server)
        client.send("sub", "subscribe_state", {"enabled": True})
        self.assertTrue(client.result("sub")["data"]["enabled"])
        event = client.read()
        self.assertEqual(event["source"], "pc_gateway")
        self.assertEqual(event["event_id"], event["data"]["snapshot_seq"])
        self.assertEqual(event["data"]["event_id"], 41)
        client.close()
        replacement = self.client(server)
        replacement.send("sub", "subscribe_state", {"enabled": True})
        self.assertTrue(replacement.result("sub")["data"]["enabled"])
        self.assertEqual(replacement.read()["type"], "event")
        replacement.send("off", "subscribe_state", {"enabled": False})
        self.assertFalse(replacement.result("off")["data"]["enabled"])
        with self.assertRaises(socket.timeout):
            replacement.read(0.12)

    def test_subscription_failure_closes_socket_without_replaying_old_state(self):
        transport = FakeSerial()
        client = self.client(self.server(transport))
        client.send("sub", "subscribe_state", {"enabled": True})
        client.result("sub")
        client.read()
        transport.fail = True
        value = client.read()
        self.assert_error(value, "not_connected")
        self.assertIsNone(client.read())

    def test_read_detected_restart_closes_every_old_client_and_allows_fresh_session(self):
        def response(request_id, sequence):
            value = board_snapshot(request_id, sequence)
            value.update(snapshot_seq=100 if sequence == 1 else sequence - 1,
                         updated_ms=10_000 if sequence == 1 else sequence)
            return frame(value)
        server = self.server(FakeSerial(response))
        first, second = self.client(server), self.client(server)
        deadline = time.monotonic() + 1
        while server.active_connections != 2 and time.monotonic() < deadline:
            time.sleep(0.001)
        self.assertEqual(server.active_connections, 2)
        first.send("before", "get_state")
        self.assertEqual(first.result("before")["data"]["snapshot_seq"], 100)
        first.send("restart", "get_state")
        self.assert_error(first.result("restart"), "device_restarted")
        self.assertIsNone(first.read())
        self.assert_error(second.read(), "device_restarted")
        self.assertIsNone(second.read())
        replacement = self.client(server)
        replacement.send("after", "get_state")
        self.assertEqual(replacement.result("after")["data"]["snapshot_seq"], 2)
        self.assertIsNone(server.broker._fault)

    def test_publisher_detected_restart_also_closes_non_subscribed_clients(self):
        def response(request_id, sequence):
            value = board_snapshot(request_id, sequence)
            value.update(snapshot_seq=99 + sequence if sequence <= 2 else sequence - 2,
                         updated_ms=10_000 + sequence if sequence <= 2 else sequence)
            return frame(value)
        server = self.server(FakeSerial(response))
        observer, subscriber = self.client(server), self.client(server)
        observer.send("old", "get_state")
        self.assertEqual(observer.result("old")["data"]["snapshot_seq"], 100)
        subscriber.send("sub", "subscribe_state", {"enabled": True})
        self.assertTrue(subscriber.result("sub")["ok"])
        self.assert_error(subscriber.read(), "device_restarted")
        self.assertIsNone(subscriber.read())
        self.assert_error(observer.read(), "device_restarted")
        self.assertIsNone(observer.read())
        replacement = self.client(server)
        replacement.send("new", "get_state")
        self.assertEqual(replacement.result("new")["data"]["snapshot_seq"], 2)
        self.assertIsNone(server.broker._fault)

    def test_network_bad_json_and_oversize_have_bounded_failures(self):
        client = self.client(self.server())
        client.socket.sendall(b"{bad}\n")
        self.assert_error(client.read(), "bad_json")
        client.send("ok", "get_state")
        self.assertTrue(client.result("ok")["ok"])
        client.socket.sendall(b"x" * (MAX_MESSAGE_BYTES + 1))
        self.assert_error(client.read(), "message_too_large")
        self.assertIsNone(client.read())

    def test_concurrent_clients_keep_uart_responses_correlated(self):
        server = self.server()
        def read_state(index):
            with socket.create_connection(server.address, timeout=2) as sock:
                sock.sendall(json.dumps({"v": 1, "id": str(index), "op": "get_state", "args": {}}).encode() + b"\n")
                value = json.loads(sock.makefile("rb").readline())
                self.assertEqual(value["id"], str(index))
                return value["data"]["snapshot_seq"]
        with ThreadPoolExecutor(max_workers=5) as pool:
            sequences = list(pool.map(read_state, range(5)))
        self.assertEqual(len(set(sequences)), 5)

    def test_public_bind_invalid_parameters_and_close_cleanup(self):
        broker = self.broker()
        with self.assertRaises(ValueError):
            MobileSerialGateway(broker, host="0.0.0.0", port=0)
        for options in ({"port": True}, {"subscription_interval_s": 0}, {"max_clients": 0}):
            with self.assertRaises(ValueError):
                MobileSerialGateway(broker, **options)
        transport = FakeSerial()
        with running_gateway(transport) as server:
            client = Client(server.address)
            self.stack.callback(client.close)
            client.send("s", "get_state")
            self.assertTrue(client.result("s")["ok"])
        self.assertTrue(transport.closed)
        self.assertFalse(server._publisher.is_alive())
        self.assertFalse(server.broker._worker.is_alive())


if __name__ == "__main__":
    unittest.main(verbosity=2)
