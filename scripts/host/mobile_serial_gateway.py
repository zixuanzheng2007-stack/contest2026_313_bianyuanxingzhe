#!/usr/bin/env python3
"""Read-only, loopback-only mobile bridge to an explicitly selected board UART.

CLI usage: python mobile_serial_gateway.py --port COM7
MuMu connects to 10.0.2.2:8766. This is a PC gateway, not independent Wi-Fi.
Only @snapshot is transmitted. No scan, reset, alert, model or config command
is accepted. Importing this module does not import pyserial or open hardware.
"""
from __future__ import annotations

import argparse
from collections import OrderedDict
from concurrent.futures import Future, InvalidStateError
from contextlib import contextmanager
from dataclasses import dataclass
import ipaddress
import json
import math
import queue
import secrets
import socket
import socketserver
import threading
import time
from typing import Any, Iterator

from mobile_device_simulator import (
    MAX_MESSAGE_BYTES, ProtocolError, _Connection, _Handler,
    _decode_request, _error, _result, _unique_object, _reject_constant,
)

CAPABILITIES = ["get_state", "subscribe_state"]
PREFIX = b"[ew-snapshot] "
ALERT_LEVELS = {"none", "soft", "strong", "emergency"}
RADAR_LINKS = {"ok", "waiting", "no_frame", "stale", "error"}


class GatewayError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _integer(value: Any, name: str, maximum: int = 2**32 - 1) -> int:
    if type(value) is not int or not 0 <= value <= maximum:
        raise GatewayError("unsupported_firmware", "Invalid snapshot field: " + name)
    return value


def validate_snapshot(value: Any, request_id: str) -> dict[str, Any]:
    """Validate only board facts; never synthesize a distance, profile or time."""
    if not isinstance(value, dict) or value.get("id") != request_id:
        raise GatewayError("unsupported_firmware", "Snapshot response identity is invalid.")
    if (type(value.get("v")) is not int or value["v"] != 1
            or value.get("origin") != "device" or value.get("connected") is not True
            or value.get("clock") != "device_monotonic"):
        raise GatewayError("unsupported_firmware", "Board does not provide snapshot protocol v1.")
    if (not isinstance(value.get("radar_link"), str) or value["radar_link"] not in RADAR_LINKS
            or not isinstance(value.get("alert_level"), str) or value["alert_level"] not in ALERT_LEVELS):
        raise GatewayError("unsupported_firmware", "Unknown board link or alert state.")
    if value.get("profile", "missing") is not None:
        raise GatewayError("unsupported_firmware", "Read-only firmware must not advertise a profile.")
    state = {"origin": "pc_gateway", "connected": True,
             "radar_link": value["radar_link"], "alert_level": value["alert_level"],
             "profile": None, "clock": "device_monotonic"}
    for name in ("range_m", "speed_kmh"):
        number = value.get(name, "missing")
        if number is not None:
            try:
                valid = type(number) in (int, float) and math.isfinite(number) and number >= 0
            except (OverflowError, ValueError):
                valid = False
            if not valid:
                raise GatewayError("unsupported_firmware", "Invalid snapshot measurement: " + name)
        state[name] = number
    for name in ("event_id", "snapshot_seq", "updated_ms"):
        state[name] = _integer(value.get(name), name)
    if state["snapshot_seq"] == 0:
        raise GatewayError("unsupported_firmware", "Snapshot sequence must be positive.")
    state["radar_error"] = _integer(value.get("radar_error"), "radar_error", 2**31 - 1)
    return state


@dataclass
class _Query:
    future: Future
    deadline: float
    setting: str | None = None


class SerialBroker:
    """One UART owner with bounded admission and complete-response deadlines.

    ``serial_port`` is an already-open pyserial-compatible object. Tests inject
    a fake read/write/close object; construction never discovers hardware.
    """

    def __init__(self, serial_port: Any, *, timeout_s: float = 0.8, max_pending: int = 16,
                 enable_sensitivity: bool = False):
        if (isinstance(timeout_s, bool) or not isinstance(timeout_s, (int, float))
                or not 0.05 <= timeout_s <= 5):
            raise ValueError("timeout_s must be between 0.05 and 5 seconds")
        if type(max_pending) is not int or not 1 <= max_pending <= 64:
            raise ValueError("max_pending must be 1-64")
        self.serial_port = serial_port
        self.timeout_s = timeout_s
        self._queue: queue.Queue[_Query] = queue.Queue(maxsize=max_pending)
        self._stopping = threading.Event()
        self._fault: GatewayError | None = None
        self._session_nonce = secrets.token_hex(8)
        self._counter = 0
        self._enable_sensitivity = enable_sensitivity
        self._active_prefix = PREFIX
        self._buffer = bytearray()
        self._prefix_probe = bytearray()
        self._collecting = False
        self._last_seq: int | None = None
        self._last_clock: int | None = None
        # An injected implementation must honor this bounded read interval.
        self.serial_port.timeout = min(0.05, timeout_s)
        self._worker = threading.Thread(target=self._run, name="ew-serial-snapshot", daemon=True)
        self._worker.start()

    @staticmethod
    def _finish(future: Future, *, value=None, error: Exception | None = None) -> None:
        try:
            if error is None:
                future.set_result(value)
            else:
                future.set_exception(error)
        except InvalidStateError:
            pass  # A timed-out caller cancelled a queued query.

    def query(self) -> dict[str, Any]:
        if self._stopping.is_set():
            raise GatewayError("not_connected", "Serial gateway has stopped.")
        if self._fault is not None:
            raise self._fault
        future = Future()
        deadline = time.monotonic() + self.timeout_s
        try:
            self._queue.put_nowait(_Query(future, deadline))
        except queue.Full as exc:
            raise GatewayError("busy", "Snapshot request queue is full.") from exc
        try:
            # The UART read interval is bounded. A small completion-only grace
            # preserves the worker's precise parse/timeout classification.
            return future.result(timeout=max(0.001, deadline - time.monotonic()) + 0.06)
        except TimeoutError as exc:
            future.cancel()
            raise GatewayError("timeout", "No fresh board snapshot before the deadline.") from exc

    def _run(self) -> None:
        while not self._stopping.is_set():
            try:
                job = self._queue.get(timeout=0.05)
            except queue.Empty:
                continue
            try:
                if job.future.cancelled():
                    continue
                if self._fault is not None:
                    raise self._fault
                if time.monotonic() >= job.deadline:
                    raise GatewayError("timeout", "Snapshot expired while queued.")
                value = self._transaction(job.deadline, job.setting) if job.setting is not None else self._transaction(job.deadline)
                self._finish(job.future, value=value)
            except GatewayError as exc:
                self._finish(job.future, error=exc)
            except (OSError, IOError) as exc:
                self._fault = GatewayError("not_connected", "Board serial connection was lost.")
                self._finish(job.future, error=self._fault)
            except Exception:
                self._fault = GatewayError("not_connected", "Serial transport failed.")
                self._finish(job.future, error=self._fault)
            finally:
                self._queue.task_done()
        while True:
            try:
                job = self._queue.get_nowait()
            except queue.Empty:
                break
            self._finish(job.future, error=GatewayError("not_connected", "Serial gateway stopped."))
            self._queue.task_done()

    def _lines(self, chunk: bytes):
        prefix = self._active_prefix
        for byte in chunk:
            if not self._collecting:
                self._prefix_probe.append(byte)
                if len(self._prefix_probe) > len(prefix):
                    del self._prefix_probe[0]
                if self._prefix_probe == prefix:
                    self._buffer = bytearray(prefix)
                    self._prefix_probe.clear()
                    self._collecting = True
                continue
            if byte == 10:
                line = bytes(self._buffer).rstrip(b"\r")
                self._buffer.clear()
                self._collecting = False
                yield line
            else:
                if len(self._buffer) >= MAX_MESSAGE_BYTES:
                    self._buffer.clear()
                    self._collecting = False
                    self._prefix_probe = bytearray([byte])
                    yield None
                else:
                    self._buffer.append(byte)

    def sensitivity(self, setting: str = "get") -> dict[str, Any]:
        if not self._enable_sensitivity or setting not in ("get", "standard", "early"):
            raise GatewayError("unsupported", "Sensitivity control is not enabled or invalid.")
        if self._stopping.is_set():
            raise GatewayError("not_connected", "Serial gateway stopped.")
        future = Future()
        deadline = time.monotonic() + self.timeout_s
        try:
            self._queue.put_nowait(_Query(future, deadline, setting))
        except queue.Full as exc:
            raise GatewayError("busy", "Serial queue is full.") from exc
        try:
            return future.result(timeout=self.timeout_s + 0.06)
        except TimeoutError as exc:
            future.cancel()
            raise GatewayError("timeout", "Sensitivity result unknown; query current setting.") from exc

    def _transaction(self, deadline: float, setting: str | None = None) -> dict[str, Any]:
        self._active_prefix = PREFIX if setting is None else b"[ew-sensitivity] "
        self._counter += 1
        if self._counter > 2**64 - 1:
            self._session_nonce = secrets.token_hex(8)
            self._counter = 1
        # Serial RX can survive closing/reopening the gateway. A per-broker
        # nonce prevents a previous instance's matching counter from looking
        # like a newly received board response. IDs stay ASCII and <= 40 bytes.
        request_id = "gw_" + self._session_nonce + "_" + str(self._counter)
        # Reset only our parser, never flush the UART. An incomplete old reply
        # must not poison the next command after its deadline has expired.
        self._buffer.clear()
        self._prefix_probe.clear()
        self._collecting = False
        wire = (("@snapshot " + request_id) if setting is None else
                ("@sensitivity " + request_id + " " + setting)).encode("ascii") + b"\r\n"
        if self.serial_port.write(wire) != len(wire):
            raise GatewayError("not_connected", "Snapshot command was not completely written.")
        saw_bad_snapshot = False
        while not self._stopping.is_set() and time.monotonic() < deadline:
            chunk = self.serial_port.read(256)
            if not isinstance(chunk, bytes):
                raise GatewayError("not_connected", "Invalid serial read result.")
            if time.monotonic() >= deadline:
                break
            if not chunk:
                self._stopping.wait(min(0.005, max(0, deadline - time.monotonic())))
            for line in self._lines(chunk):
                if line is None:
                    saw_bad_snapshot = True
                    continue
                try:
                    raw = json.loads(line[len(self._active_prefix):].decode("utf-8"),
                                     object_pairs_hook=_unique_object, parse_constant=_reject_constant)
                except (UnicodeError, ValueError, RecursionError):
                    saw_bad_snapshot = True
                    continue
                if not isinstance(raw, dict) or raw.get("id") != request_id:
                    continue
                if setting is not None:
                    profile = raw.get("profile")
                    factor = 1.25 if profile == "early" else 1.0
                    if (type(raw.get("v")) is not int or raw["v"] != 1 or raw.get("ok") is not True
                            or profile not in ("standard", "early")
                            or type(raw.get("factor")) not in (int, float) or raw["factor"] != factor
                            or raw.get("volatile") is not True
                            or (setting != "get" and profile != setting)):
                        raise GatewayError("unsupported_firmware", "Invalid sensitivity acknowledgement.")
                    return raw
                value = validate_snapshot(raw, request_id)
                seq, clock = value["snapshot_seq"], value["updated_ms"]
                if self._last_seq is not None and seq <= self._last_seq:
                    if clock < self._last_clock:
                        self._last_seq = self._last_clock = None
                        raise GatewayError("device_restarted", "Board restarted; reconnect to establish a new session.")
                    raise GatewayError("stale_snapshot", "Board snapshot sequence did not advance.")
                self._last_seq, self._last_clock = seq, clock
                value["received_at_ms"] = int(time.time() * 1000)
                return value
        if self._stopping.is_set():
            raise GatewayError("not_connected", "Serial gateway stopped.")
        if saw_bad_snapshot:
            raise GatewayError("unsupported_firmware", "Board snapshot data was malformed.")
        raise GatewayError("timeout", "No fresh matching board snapshot was received.")

    def close(self) -> None:
        if self._stopping.is_set():
            return
        self._stopping.set()
        try:
            self.serial_port.close()
        except (OSError, IOError):
            pass
        self._worker.join(timeout=self.timeout_s + 0.2)


class MobileSerialGateway(socketserver.ThreadingTCPServer):
    """Read-only JSONL service. Every read retries UART, never an old cache.

    Repeating an ID with different content is rejected; repeating a read-only
    request obtains a fresh snapshot. IDs fence request content, not freshness.
    Subscription retries always act on the requesting connection.
    """

    allow_reuse_address = True
    daemon_threads = True
    request_queue_size = 16

    def __init__(self, broker: SerialBroker, host: str = "127.0.0.1", port: int = 8766, *,
                 subscription_interval_s: float = 1, idle_timeout_s: float = 120,
                 frame_timeout_s: float = 5, max_clients: int = 16,
                 cache_capacity: int = 256, cache_ttl_s: float = 300):
        host = "127.0.0.1" if host == "localhost" else host
        try:
            address = ipaddress.ip_address(host)
        except ValueError as exc:
            raise ValueError("Only literal loopback addresses or localhost are allowed.") from exc
        if not address.is_loopback:
            raise ValueError("Non-loopback access requires an authenticated transport.")
        if type(port) is not int or not 0 <= port <= 65535:
            raise ValueError("port must be 0-65535")
        for name, value, maximum in (("subscription_interval_s", subscription_interval_s, 60),
                                     ("idle_timeout_s", idle_timeout_s, 86400),
                                     ("frame_timeout_s", frame_timeout_s, 300),
                                     ("cache_ttl_s", cache_ttl_s, 86400)):
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 < value <= maximum:
                raise ValueError(name + " is outside the supported range")
        for name, value, maximum in (("max_clients", max_clients, 64), ("cache_capacity", cache_capacity, 4096)):
            if type(value) is not int or not 1 <= value <= maximum:
                raise ValueError(name + " is outside the supported range")
        self.address_family = socket.AF_INET6 if address.version == 6 else socket.AF_INET
        self.broker = broker
        self.subscription_interval_s = subscription_interval_s
        self.idle_timeout_s = idle_timeout_s
        self.frame_timeout_s = frame_timeout_s
        self.max_clients = max_clients
        self.cache_capacity = cache_capacity
        self.cache_ttl_s = cache_ttl_s
        self.stopping = threading.Event()
        self._guard = threading.RLock()
        self._connections: set[_Connection] = set()
        self._records: OrderedDict[str, tuple[str, float]] = OrderedDict()
        super().__init__((host, port), _Handler)
        self._publisher = threading.Thread(target=self._publish_loop, name="ew-gateway-events", daemon=True)
        self._publisher.start()

    @property
    def address(self) -> tuple[str, int]:
        return self.server_address[0], self.server_address[1]

    @property
    def active_connections(self) -> int:
        with self._guard:
            return len(self._connections)

    @property
    def subscriber_count(self) -> int:
        with self._guard:
            return sum(connection.subscribed and not connection.closed.is_set() for connection in self._connections)

    def _register(self, connection: _Connection) -> bool:
        with self._guard:
            if self.stopping.is_set() or len(self._connections) >= self.max_clients:
                return False
            self._connections.add(connection)
            connection.subscription_id = None
            return True

    def _unregister(self, connection: _Connection) -> None:
        with self._guard:
            self._connections.discard(connection)

    def _invalidate_sessions(self, error: GatewayError, *,
                             requester: _Connection | None = None,
                             request_id: str | None = None) -> None:
        # A reboot resets the board's snapshot sequence for every observer.
        # Close all old network sessions, even clients that are not currently
        # subscribed, so the next handshake resets their ordering boundary.
        with self._guard:
            connections = list(self._connections)
        for connection in connections:
            result_id = request_id if connection is requester else connection.subscription_id
            connection.send(_error(result_id, error.code, str(error)))
            connection.close()

    def _record(self, request_id: str, fingerprint: str) -> None:
        with self._guard:
            now = time.monotonic()
            expired = [key for key, (_, touched) in self._records.items() if now - touched >= self.cache_ttl_s]
            for key in expired:
                del self._records[key]
            if request_id in self._records and self._records[request_id][0] != fingerprint:
                raise ProtocolError("id_conflict", "Request id was used with different content.", request_id)
            self._records[request_id] = (fingerprint, now)
            self._records.move_to_end(request_id)
            while len(self._records) > self.cache_capacity:
                self._records.popitem(last=False)

    def _handle_line(self, connection: _Connection, line: bytes) -> None:
        try:
            request_id, operation, args, fingerprint = _decode_request(line)
        except ProtocolError as exc:
            connection.send(_error(exc.request_id, exc.code, str(exc)))
            return
        try:
            self._record(request_id, fingerprint)
            if operation not in {"hello", *CAPABILITIES}:
                raise GatewayError("unsupported", "Gateway only provides read-only board state.")
            expected = {"enabled"} if operation == "subscribe_state" else set()
            if set(args) != expected or (operation == "subscribe_state" and type(args["enabled"]) is not bool):
                raise GatewayError("invalid_args", "Invalid arguments for read-only operation.")
            if operation == "subscribe_state" and not args["enabled"]:
                connection.subscription_id = request_id
                connection.subscription_result(False, _result(request_id, {"origin": "pc_gateway", "enabled": False}))
                return
            state = self.broker.query()
            if operation == "hello":
                data = {"origin": "pc_gateway", "device_id": "ew-serial-board",
                        "capabilities": list(CAPABILITIES), "max_message_bytes": MAX_MESSAGE_BYTES,
                        "read_only": True}
            elif operation == "get_state":
                data = state
            else:
                connection.subscription_id = request_id
                connection.subscription_result(True, _result(request_id, {"origin": "pc_gateway", "enabled": True}))
                return
            connection.send(_result(request_id, data))
        except (GatewayError, ProtocolError) as exc:
            if isinstance(exc, GatewayError) and exc.code == "device_restarted":
                self._invalidate_sessions(exc, requester=connection, request_id=request_id)
            else:
                connection.send(_error(request_id, exc.code, str(exc)))

    def _publish_loop(self) -> None:
        while not self.stopping.wait(self.subscription_interval_s):
            with self._guard:
                subscribers = [connection for connection in self._connections
                               if connection.subscribed and not connection.closed.is_set()]
            if not subscribers:
                continue
            try:
                state = self.broker.query()
            except GatewayError as exc:
                if exc.code == "device_restarted":
                    self._invalidate_sessions(exc)
                    continue
                for connection in subscribers:
                    connection.send(_error(connection.subscription_id, exc.code, str(exc)))
                    connection.close()
                continue
            event = {"v": 1, "type": "event", "event": "state", "source": "pc_gateway",
                     "event_id": state["snapshot_seq"], "data": state}
            for connection in subscribers:
                connection.send(event, subscription=True)

    def server_close(self) -> None:
        self.stopping.set()
        with self._guard:
            connections = list(self._connections)
        for connection in connections:
            connection.close()
        self.broker.close()
        if hasattr(self, "_publisher"):
            self._publisher.join(timeout=self.broker.timeout_s + 0.3)
        super().server_close()


@contextmanager
def running_gateway(serial_port: Any, *, broker_options: dict | None = None, **options: Any) -> Iterator[MobileSerialGateway]:
    """Real TCP plus explicitly injected UART, for software acceptance tests."""
    broker = SerialBroker(serial_port, **(broker_options or {}))
    options.setdefault("port", 0)
    try:
        server = MobileSerialGateway(broker, **options)
    except Exception:
        broker.close()
        raise
    worker = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
    worker.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=2)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", required=True, help="Explicit board serial port; never auto-discovered")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--listen-port", type=int, default=8766)
    parser.add_argument("--timeout", type=float, default=0.8)
    args = parser.parse_args()
    # Reject non-loopback destinations before any hardware is opened.
    try:
        if not ipaddress.ip_address("127.0.0.1" if args.host == "localhost" else args.host).is_loopback:
            raise ValueError("Only loopback binding is supported")
        if not 0 <= args.listen_port <= 65535 or not 0.05 <= args.timeout <= 5:
            raise ValueError("Invalid listen port or serial timeout")
        import serial
    except (ValueError, ImportError) as exc:
        parser.error(str(exc))
    port = serial.Serial(port=None, baudrate=1_000_000, timeout=0.05, write_timeout=0.2)
    port.dtr = False
    port.rts = False
    port.port = args.port
    try:
        port.open()
        with running_gateway(port, broker_options={"timeout_s": args.timeout},
                             host=args.host, port=args.listen_port) as server:
            print(json.dumps({"origin": "pc_gateway", "read_only": True,
                              "listening": list(server.address), "board_verified": False}), flush=True)
            while not server.stopping.wait(1):
                pass
    except KeyboardInterrupt:
        pass
    except (OSError, ValueError) as exc:
        # Do not print arbitrary exception text potentially containing local secrets.
        print(json.dumps({"error": "gateway_start_failed", "detail": type(exc).__name__}), flush=True)
        return 1
    finally:
        port.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
