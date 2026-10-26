#!/usr/bin/env python3
"""Loopback-only Edge Walker TCP JSONL simulator; never talks to the board.

Run ``python scripts/host/mobile_device_simulator.py`` and connect MuMu to
``10.0.2.2:8765``. Every simulated state/reply carries ``origin: simulator``.
The maximum JSON line is 8192 UTF-8 bytes, excluding the trailing newline.
Request IDs are deduplicated across connections within a bounded, expiring
cache; an evicted ID must not be used as a permanent exactly-once guarantee.

Fault examples: ``--delay-ms 3000`` delays queued operations; setting
``--drop-after-requests 2`` closes each connection before its second request
is executed. Public/LAN binding is deliberately refused without an auth
protocol. Use a separately authenticated gateway when remote access is needed.
"""
from __future__ import annotations

import argparse
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import dataclass, field
import ipaddress
import json
import socket
import socketserver
import threading
import time
from typing import Any, Iterator
import weakref


VERSION = 1
MAX_MESSAGE_BYTES = 8192
CAPABILITIES = ["get_state", "subscribe_state", "test_alert", "get_config",
                "set_profile", "ask"]
ALERT_LEVELS = ("none", "soft", "strong", "emergency")
PROFILES = ("walk", "cycle")


class ProtocolError(ValueError):
    def __init__(self, code: str, message: str, request_id: str | None = None):
        super().__init__(message)
        self.code = code
        self.request_id = request_id


def _result(request_id: str, data: dict[str, Any]) -> dict[str, Any]:
    return {"v": VERSION, "id": request_id, "type": "result", "ok": True,
            "stage": "applied", "data": data}


def _error(request_id: str | None, code: str, message: str) -> dict[str, Any]:
    return {"v": VERSION, "id": request_id, "type": "result", "ok": False,
            "error": {"code": code, "message": message}}


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON object key")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ValueError("non-finite JSON number: " + value)


def _valid_id(value: Any) -> bool:
    if not isinstance(value, str) or not value or any(ord(c) < 32 for c in value):
        return False
    try:
        return len(value.encode("utf-8")) <= 128
    except UnicodeError:
        return False


def _decode_request(line: bytes) -> tuple[str, str, dict[str, Any], str]:
    try:
        decoded = line.decode("utf-8")
    except UnicodeError as exc:
        raise ProtocolError("invalid_utf8", "Messages must use UTF-8.") from exc
    try:
        request = json.loads(decoded, object_pairs_hook=_unique_object,
                             parse_constant=_reject_constant)
    except (ValueError, RecursionError) as exc:
        raise ProtocolError("bad_json", "A line must contain one valid JSON object.") from exc
    if not isinstance(request, dict):
        raise ProtocolError("invalid_request", "Request must be an object.")
    request_id = request.get("id")
    if not _valid_id(request_id):
        raise ProtocolError("invalid_request", "id must be 1-128 UTF-8 bytes without controls.")
    if type(request.get("v")) is not int or request["v"] != VERSION:
        raise ProtocolError("unsupported_version", "Only protocol v=1 is supported.", request_id)
    if set(request) != {"v", "id", "op", "args"}:
        raise ProtocolError("invalid_request", "Expected v, id, op and args fields.", request_id)
    operation, args = request["op"], request["args"]
    try:
        valid_operation = (isinstance(operation, str) and bool(operation)
                           and len(operation.encode("utf-8")) <= 64
                           and all(ord(c) >= 32 for c in operation))
    except UnicodeError:
        valid_operation = False
    if not valid_operation or not isinstance(args, dict):
        raise ProtocolError("invalid_request", "op must be text and args must be an object.", request_id)
    try:
        fingerprint = json.dumps([operation, args], ensure_ascii=True,
                                 sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (ValueError, RecursionError) as exc:
        raise ProtocolError("invalid_request", "Arguments are too complex.", request_id) from exc
    return request_id, operation, args, fingerprint


def _arguments(operation: str, args: dict[str, Any]) -> dict[str, Any]:
    allowed = {"hello": set(), "get_state": set(), "get_config": set(),
               "subscribe_state": {"enabled"}, "set_profile": {"profile"},
               "test_alert": {"level", "duration_ms"}, "ask": {"text"}}
    if operation not in allowed:
        raise ProtocolError("unsupported", "Unsupported operation: " + operation)
    if set(args) - allowed[operation]:
        raise ProtocolError("invalid_args", "Unexpected argument for " + operation + ".")
    if operation == "subscribe_state" and type(args.get("enabled")) is not bool:
        raise ProtocolError("invalid_args", "enabled must be a boolean.")
    if operation == "set_profile" and args.get("profile") not in PROFILES:
        raise ProtocolError("invalid_args", "profile must be walk or cycle.")
    if operation == "test_alert":
        duration = args.get("duration_ms", 1000)
        if args.get("level") not in ALERT_LEVELS:
            raise ProtocolError("invalid_args", "Unknown alert level.")
        if type(duration) is not int or not 50 <= duration <= 5000:
            raise ProtocolError("invalid_args", "duration_ms must be an integer from 50 to 5000.")
        return {"level": args["level"], "duration_ms": duration}
    if operation == "ask":
        text = args.get("text")
        try:
            valid = isinstance(text, str) and bool(text.strip()) and len(text.encode("utf-8")) <= 2048
        except UnicodeError:
            valid = False
        if not valid:
            raise ProtocolError("invalid_args", "text must be nonempty UTF-8 text up to 2048 bytes.")
    return args


@dataclass
class _Record:
    request_id: str
    fingerprint: str
    lock: Any = field(default_factory=threading.RLock)
    listeners: Any = field(default_factory=weakref.WeakSet)
    accepted: dict[str, Any] | None = None
    final: dict[str, Any] | None = None
    completed_at: float | None = None


class _Connection:
    def __init__(self, server: MobileDeviceSimulator, sock: socket.socket):
        self.server = server
        self.socket = sock
        self.lock = threading.RLock()
        self.closed = threading.Event()
        self.subscribed = False
        self.last_activity = time.monotonic()
        self.request_count = 0

    def send(self, value: dict[str, Any], *, subscription: bool = False) -> bool:
        # A single writer keeps event/result JSON lines from interleaving.
        with self.lock:
            if self.closed.is_set() or (subscription and not self.subscribed):
                return False
            try:
                wire = json.dumps(value, ensure_ascii=False, separators=(",", ":"),
                                  allow_nan=False).encode("utf-8")
                if len(wire) > MAX_MESSAGE_BYTES:
                    raise ValueError("outgoing message exceeded protocol bound")
                self.socket.sendall(wire + b"\n")
                self.last_activity = time.monotonic()
                return True
            except (OSError, ValueError, UnicodeError):
                self.closed.set()
                return False

    def subscription_result(self, enabled: bool, value: dict[str, Any]) -> None:
        with self.lock:
            self.subscribed = enabled
            self.send(value)

    def close(self) -> None:
        self.closed.set()
        try:
            self.socket.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        self.socket.close()
        self.server._unregister(self)


class _Handler(socketserver.BaseRequestHandler):
    def handle(self) -> None:
        server: MobileDeviceSimulator = self.server
        self.request.settimeout(0.1)
        connection = _Connection(server, self.request)
        if not server._register(connection):
            connection.send(_error(None, "busy", "Too many clients."))
            connection.close()
            return
        buffer = bytearray()
        frame_started: float | None = None
        try:
            while not server.stopping.is_set() and not connection.closed.is_set():
                now = time.monotonic()
                if frame_started is not None and now - frame_started >= server.frame_timeout_s:
                    connection.send(_error(None, "timeout", "Incomplete JSON line timed out."))
                    break
                if now - connection.last_activity >= server.idle_timeout_s:
                    connection.send(_error(None, "timeout", "Idle connection timed out."))
                    break
                try:
                    chunk = self.request.recv(4096)
                except socket.timeout:
                    continue
                except OSError:
                    break
                if not chunk:
                    break
                connection.last_activity = time.monotonic()
                if not buffer:
                    frame_started = time.monotonic()
                buffer.extend(chunk)
                while b"\n" in buffer:
                    end = buffer.index(10)
                    if end > MAX_MESSAGE_BYTES:
                        connection.send(_error(None, "message_too_large", "JSON line exceeds 8192 bytes."))
                        return
                    line = bytes(buffer[:end])
                    del buffer[:end + 1]
                    server._handle_line(connection, line)
                    if connection.closed.is_set():
                        return
                    frame_started = time.monotonic() if buffer else None
                if len(buffer) > MAX_MESSAGE_BYTES:
                    connection.send(_error(None, "message_too_large", "JSON line exceeds 8192 bytes."))
                    break
        finally:
            connection.close()


class MobileDeviceSimulator(socketserver.ThreadingTCPServer):
    """Concurrent bounded simulator. Construction binds a loopback socket.

    Use :func:`running_simulator` with ``port=0`` in tests. Injecting delays or
    drops is explicit and never changes a board or calls a real model.
    """

    allow_reuse_address = True
    daemon_threads = True
    request_queue_size = 16

    def __init__(self, host: str = "127.0.0.1", port: int = 8765, *,
                 delay_ms: int = 150, drop_after_requests: int = 0,
                 idle_timeout_s: float = 120, frame_timeout_s: float = 5,
                 subscription_interval_s: float = 1, max_clients: int = 16,
                 cache_capacity: int = 256, cache_ttl_s: float = 300,
                 max_pending: int = 16):
        host = "127.0.0.1" if host == "localhost" else host
        try:
            address = ipaddress.ip_address(host)
        except ValueError as exc:
            raise ValueError("Only literal loopback addresses or localhost are allowed.") from exc
        if not address.is_loopback:
            raise ValueError("Non-loopback binding is refused: authentication is not implemented.")
        if type(port) is not int or not 0 <= port <= 65535:
            raise ValueError("port must be an integer from 0 to 65535")
        if type(delay_ms) is not int or not 0 <= delay_ms <= 30000:
            raise ValueError("delay_ms must be an integer from 0 to 30000")
        if type(drop_after_requests) is not int or not 0 <= drop_after_requests <= 100000:
            raise ValueError("drop_after_requests must be an integer from 0 to 100000")
        for name, value, maximum in (("idle_timeout_s", idle_timeout_s, 86400),
                                     ("frame_timeout_s", frame_timeout_s, 300),
                                     ("subscription_interval_s", subscription_interval_s, 60),
                                     ("cache_ttl_s", cache_ttl_s, 86400)):
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 < value <= maximum:
                raise ValueError(name + " is outside its supported range")
        for name, value, maximum in (("max_clients", max_clients, 64),
                                     ("cache_capacity", cache_capacity, 4096),
                                     ("max_pending", max_pending, 64)):
            if type(value) is not int or not 1 <= value <= maximum:
                raise ValueError(name + " is outside its supported range")
        self.address_family = socket.AF_INET6 if address.version == 6 else socket.AF_INET
        self.delay_ms = delay_ms
        self.drop_after_requests = drop_after_requests
        self.idle_timeout_s = idle_timeout_s
        self.frame_timeout_s = frame_timeout_s
        self.subscription_interval_s = subscription_interval_s
        self.max_clients = max_clients
        self.cache_capacity = cache_capacity
        self.cache_ttl_s = cache_ttl_s
        self.stopping = threading.Event()
        self._guard = threading.RLock()
        self._connections: set[_Connection] = set()
        self._records: OrderedDict[str, _Record] = OrderedDict()
        self._pending = threading.BoundedSemaphore(max_pending)
        self._alert_deadline: float | None = None
        self._state = {"origin": "simulator", "connected": True, "radar_link": "ok",
                       "range_m": 12.4, "speed_kmh": 18.0, "alert_level": "none",
                       "profile": "walk", "event_id": 0, "updated_ms": int(time.time() * 1000)}
        super().__init__((host, port), _Handler)
        self._executor = ThreadPoolExecutor(max_workers=min(4, max_pending),
                                            thread_name_prefix="ew-sim-action")
        self._publisher = threading.Thread(target=self._publish_loop,
                                           name="ew-sim-events", daemon=True)
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
            return sum(c.subscribed and not c.closed.is_set() for c in self._connections)

    def _register(self, connection: _Connection) -> bool:
        with self._guard:
            if self.stopping.is_set() or len(self._connections) >= self.max_clients:
                return False
            self._connections.add(connection)
            return True

    def _unregister(self, connection: _Connection) -> None:
        with self._guard:
            self._connections.discard(connection)

    def _snapshot(self) -> dict[str, Any]:
        with self._guard:
            return dict(self._state)

    def _changed(self) -> dict[str, Any]:
        # Caller owns _guard. State and periodic event sequence share one clock.
        self._state["event_id"] += 1
        self._state["updated_ms"] = int(time.time() * 1000)
        return dict(self._state)

    def _record(self, request_id: str, fingerprint: str) -> tuple[_Record, bool]:
        with self._guard:
            now = time.monotonic()
            expired = [key for key, value in self._records.items()
                       if value.completed_at is not None and now - value.completed_at >= self.cache_ttl_s]
            for key in expired:
                del self._records[key]
            record = self._records.get(request_id)
            if record is not None:
                if record.fingerprint != fingerprint:
                    raise ProtocolError("id_conflict", "Request id was used with different content.", request_id)
                self._records.move_to_end(request_id)
                return record, False
            while len(self._records) >= self.cache_capacity:
                removable = next((key for key, value in self._records.items()
                                  if value.completed_at is not None), None)
                if removable is None:
                    raise ProtocolError("busy", "Request cache is full of pending work.", request_id)
                del self._records[removable]
            record = _Record(request_id, fingerprint)
            self._records[request_id] = record
            return record, True

    def _complete(self, record: _Record, result: dict[str, Any]) -> None:
        with record.lock:
            record.final = result
            record.completed_at = time.monotonic()
            for connection in list(record.listeners):
                connection.send(result)
            record.listeners.clear()

    def _handle_line(self, connection: _Connection, line: bytes) -> None:
        try:
            request_id, operation, raw_args, fingerprint = _decode_request(line)
        except ProtocolError as exc:
            connection.send(_error(exc.request_id, exc.code, str(exc)))
            return
        connection.request_count += 1
        if self.drop_after_requests and connection.request_count >= self.drop_after_requests:
            connection.close()
            return
        try:
            record, is_new = self._record(request_id, fingerprint)
        except ProtocolError as exc:
            connection.send(_error(request_id, exc.code, str(exc)))
            return
        with record.lock:
            if not is_new:
                if record.final is not None:
                    if operation == "subscribe_state" and record.final["ok"]:
                        # Subscriptions belong to a connection, so a retry on a
                        # replacement connection must restore that connection.
                        connection.subscription_result(raw_args["enabled"], record.final)
                    else:
                        connection.send(record.final)
                else:
                    record.listeners.add(connection)
                    if record.accepted is not None:
                        connection.send(record.accepted)
                return
            record.listeners.add(connection)
            try:
                args = _arguments(operation, raw_args)
            except ProtocolError as exc:
                self._complete(record, _error(request_id, exc.code, str(exc)))
                return
            if operation in ("test_alert", "ask"):
                if not self._pending.acquire(blocking=False):
                    self._complete(record, _error(request_id, "busy", "Action queue is full."))
                    return
                record.accepted = {"v": VERSION, "id": request_id, "type": "accepted",
                                   "ok": True, "stage": "queued"}
                for listener in list(record.listeners):
                    listener.send(record.accepted)
                try:
                    self._executor.submit(self._deferred, record, operation, args)
                except RuntimeError:
                    self._pending.release()
                    self._complete(record, _error(request_id, "server_closing", "Simulator is stopping."))
                return
            if operation == "hello":
                data = {"origin": "simulator", "device_id": "ew-sim-001",
                        "capabilities": list(CAPABILITIES), "max_message_bytes": MAX_MESSAGE_BYTES}
            elif operation == "get_state":
                data = self._snapshot()
            elif operation == "get_config":
                data = {"origin": "simulator", "profile": self._snapshot()["profile"]}
            elif operation == "set_profile":
                with self._guard:
                    self._state["profile"] = args["profile"]
                    self._changed()
                data = {"origin": "simulator", "profile": args["profile"]}
            else:  # subscribe_state: acknowledgment follows the subscription fence.
                data = {"origin": "simulator", "enabled": args["enabled"]}
                value = _result(request_id, data)
                connection.subscription_result(args["enabled"], value)
                record.listeners.discard(connection)
                self._complete(record, value)
                return
            self._complete(record, _result(request_id, data))

    def _deferred(self, record: _Record, operation: str, args: dict[str, Any]) -> None:
        try:
            if self.stopping.wait(self.delay_ms / 1000):
                self._complete(record, _error(record.request_id, "server_closing", "Simulator is stopping."))
                return
            if operation == "ask":
                data = {"origin": "simulator",
                        "reply": "【模拟器】这是模拟回复，未调用真实模型。你的问题：" + args["text"][:256]}
            else:
                with self._guard:
                    self._state["alert_level"] = args["level"]
                    self._alert_deadline = (time.monotonic() + args["duration_ms"] / 1000
                                            if args["level"] != "none" else None)
                    state = self._changed()
                data = {"origin": "simulator", "event_id": state["event_id"], "state": state}
            self._complete(record, _result(record.request_id, data))
        finally:
            self._pending.release()

    def _publish_loop(self) -> None:
        next_event = time.monotonic() + self.subscription_interval_s
        while not self.stopping.wait(min(0.05, self.subscription_interval_s)):
            with self._guard:
                now = time.monotonic()
                if self._alert_deadline is not None and now >= self._alert_deadline:
                    self._state["alert_level"] = "none"
                    self._alert_deadline = None
                    self._changed()
                if now < next_event:
                    continue
                next_event = now + self.subscription_interval_s
                subscribers = [c for c in self._connections if c.subscribed and not c.closed.is_set()]
                if not subscribers:
                    continue
                state = self._changed()
            value = {"v": VERSION, "type": "event", "event": "state",
                     "event_id": state["event_id"], "source": "simulator", "data": state}
            for connection in subscribers:
                connection.send(value, subscription=True)

    def server_close(self) -> None:
        self.stopping.set()
        with self._guard:
            connections = list(self._connections)
        for connection in connections:
            connection.close()
        if hasattr(self, "_publisher"):
            self._publisher.join(timeout=2)
        if hasattr(self, "_executor"):
            self._executor.shutdown(wait=True)
        super().server_close()


@contextmanager
def running_simulator(**options: Any) -> Iterator[MobileDeviceSimulator]:
    """Start a real socket server; defaults to an OS-assigned temporary port."""
    options.setdefault("port", 0)
    server = MobileDeviceSimulator(**options)
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05},
                              name="ew-sim-server", daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1", help="Loopback address only.")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--delay-ms", type=int, default=150, help="Delay queued result by 0-30000 ms.")
    parser.add_argument("--drop-after-requests", type=int, default=0,
                        help="Drop before the Nth request on each connection; 0 disables.")
    parser.add_argument("--idle-timeout", type=float, default=120)
    parser.add_argument("--frame-timeout", type=float, default=5)
    args = parser.parse_args()
    try:
        server = MobileDeviceSimulator(args.host, args.port, delay_ms=args.delay_ms,
                                       drop_after_requests=args.drop_after_requests,
                                       idle_timeout_s=args.idle_timeout,
                                       frame_timeout_s=args.frame_timeout)
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    print(json.dumps({"origin": "simulator", "listening": list(server.address),
                      "mumu_host": "10.0.2.2", "max_message_bytes": MAX_MESSAGE_BYTES}), flush=True)
    try:
        server.serve_forever(poll_interval=0.1)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
