#!/usr/bin/env python3
"""Exercise the real bounded ESP-AT stream parser, without UART or devices."""
from __future__ import annotations

import ctypes
import os
from pathlib import Path
import random
import subprocess
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parents[2] / "app/edge_walker"
CALLBACK = ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_int,
                          ctypes.c_int, ctypes.c_void_p, ctypes.c_size_t)
LINE, PROMPT, DATA = 1, 2, 3


class Session:
    def __init__(self, library, multiple=1):
        self.library = library
        size = library.ew_test_parser_size()
        self.storage = ctypes.create_string_buffer(b"x" * (size + 32), size + 32)
        self.pointer = ctypes.cast(ctypes.byref(self.storage, 16), ctypes.c_void_p)
        self.events = []
        self.callback = CALLBACK(lambda _ctx, event, link, data, length:
                                 self.events.append((event, link, ctypes.string_at(data, length))))
        self.reset(multiple)

    def reset(self, multiple=1):
        result = self.library.ew_esp_stream_init(self.pointer, multiple, self.callback, None)
        assert result == 0, result

    def feed(self, data):
        buffer = ctypes.create_string_buffer(data)
        result = self.library.ew_esp_stream_feed(self.pointer, buffer, len(data))
        assert self.storage.raw[:16] == b"x" * 16
        assert self.storage.raw[-16:] == b"x" * 16
        return result

    def expire(self):
        return self.library.ew_esp_stream_expire(self.pointer)


class EspStreamTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="ew_esp_stream_")
        directory = Path(cls.temp.name)
        shim = directory / "size.c"
        shim.write_text('#include "ew_esp_stream.h"\n'
                        'size_t ew_test_parser_size(void) { return sizeof(ew_esp_stream_t); }\n',
                        encoding="utf-8")
        library = directory / ("stream.dll" if os.name == "nt" else "stream.so")
        subprocess.run(["gcc", "-std=c99", "-O2", "-Wall", "-Wextra", "-Werror",
                        "-shared", *([] if os.name == "nt" else ["-fPIC"]),
                        "-I", str(SOURCE), str(shim), str(SOURCE / "ew_esp_stream.c"),
                        "-o", str(library)], check=True)
        cls.lib = ctypes.CDLL(str(library))
        cls.lib.ew_test_parser_size.restype = ctypes.c_size_t
        cls.lib.ew_esp_stream_init.argtypes = [ctypes.c_void_p, ctypes.c_int, CALLBACK, ctypes.c_void_p]
        cls.lib.ew_esp_stream_feed.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t]
        cls.lib.ew_esp_stream_expire.argtypes = [ctypes.c_void_p]
        # Windows cannot remove a loaded DLL; explicitly unload after tests.
        cls.handle = cls.lib._handle

    @classmethod
    def tearDownClass(cls):
        if os.name == "nt":
            import _ctypes
            _ctypes.FreeLibrary(cls.handle)
        cls.temp.cleanup()

    def session(self, multiple=1):
        return Session(self.lib, multiple)

    def test_lines_prompt_and_empty_lines_one_byte_at_a_time(self):
        session = self.session()
        for byte in b"\r\nOK\r\n> \r\nSEND OK\r\n":
            self.assertEqual(session.feed(bytes([byte])), 0)
        self.assertEqual(session.events, [(LINE, -1, b"OK"), (PROMPT, -1, b""),
                                          (LINE, -1, b"SEND OK")])
        self.assertEqual(session.expire(), 0)

    def test_payload_cannot_spoof_at_replies_or_link_events(self):
        session = self.session(0)
        payload = b"\x00\r\nOK\r\nERROR\r\n> +IPD,1,4:fake\r\n0,CLOSED\xff"
        self.assertEqual(session.feed(b"+IPD," + str(len(payload)).encode() + b":" + payload), 0)
        self.assertEqual(session.events, [(DATA, -1, payload)])

    def test_multiple_links_and_adjacent_frames_do_not_mix(self):
        session = self.session()
        transcript = b"0,CONNECT\r\n+IPD,0,3:one+IPD,4,3:two\r\n4,CLOSED\r\n"
        self.assertEqual(session.feed(transcript), 0)
        self.assertEqual(session.events, [(LINE, -1, b"0,CONNECT"), (DATA, 0, b"one"),
                                          (DATA, 4, b"two"), (LINE, -1, b"4,CLOSED")])

    def test_every_possible_two_chunk_split(self):
        transcript = b"\r\n+IPD,2,11:hello\x00world\r\nOK\r\n"
        for split in range(len(transcript) + 1):
            with self.subTest(split=split):
                session = self.session()
                self.assertEqual(session.feed(transcript[:split]), 0)
                self.assertEqual(session.feed(transcript[split:]), 0)
                self.assertEqual(session.events, [(DATA, 2, b"hello\x00world"), (LINE, -1, b"OK")])

    def test_random_chunking_and_binary_payloads(self):
        rng = random.Random(251025)
        transcript = bytearray()
        expected = []
        for index in range(80):
            payload = bytes(rng.randrange(256) for _ in range(rng.randrange(1, 150)))
            link = index % 5
            transcript.extend(f"+IPD,{link},{len(payload)}:".encode() + payload + b"\r\nOK\r\n")
            expected.extend([(DATA, link, payload), (LINE, -1, b"OK")])
        session = self.session()
        offset = 0
        while offset < len(transcript):
            count = rng.randrange(1, 65)
            self.assertEqual(session.feed(bytes(transcript[offset:offset + count])), 0)
            offset += count
        self.assertEqual(session.events, expected)

    def test_maximum_payload_is_atomic_and_bounded(self):
        session = self.session()
        payload = bytes(range(256)) * 32
        self.assertEqual(session.feed(b"+IPD,1,8192:" + payload[:-1]), 0)
        self.assertEqual(session.events, [])
        self.assertEqual(session.feed(payload[-1:]), 0)
        self.assertEqual(session.events, [(DATA, 1, payload)])

    def test_oversized_signed_and_malformed_headers_poison_session(self):
        for header in (b"+IPD,0,8193:", b"+IPD,0,99999999999999999999999:",
                       b"+IPD,0,-1:", b"+IPD,0,+1:", b"+IPD,0,:",
                       b"+IPD,5,1:", b"+IPD,,1:", b"+IPD,0,1,2:",
                       b'+IPD,0,1,"192.168.1.1",80:', b"+IPD,0,1.0:"):
            with self.subTest(header=header):
                session = self.session()
                error = session.feed(header + b"OK\r\n")
                self.assertLess(error, 0)
                self.assertEqual(session.feed(b"\r\nOK\r\n+IPD,0,1:a"), error)
                self.assertEqual(session.events, [])

    def test_connection_mode_mismatch_is_rejected(self):
        self.assertLess(self.session(0).feed(b"+IPD,0,1:a"), 0)
        self.assertLess(self.session(1).feed(b"+IPD,1:a"), 0)

    def test_passive_mode_is_not_misread_as_active_data(self):
        session = self.session()
        self.assertLess(session.feed(b"+IPD,0,40\r\nOK\r\n"), 0)
        self.assertEqual(session.events, [])

    def test_zero_length_frames_and_max_line(self):
        session = self.session()
        self.assertEqual(session.feed(b"+IPD,3,0:" + b"a" * 512 + b"\n"), 0)
        self.assertEqual(session.events, [(DATA, 3, b""), (LINE, -1, b"a" * 512)])

    def test_text_overflow_and_nul_fail_without_truncated_success(self):
        for data in (b"a" * 513 + b"\nOK\r\n", b"bad\x00OK\r\n"):
            session = self.session()
            error = session.feed(data)
            self.assertLess(error, 0)
            self.assertEqual(session.events, [])
            self.assertEqual(session.feed(b"OK\r\n"), error)

    def test_partial_frame_deadline_never_emits_or_resynchronizes_payload(self):
        for prefix in (b"+IP", b"+IPD,0,4:", b"+IPD,0,20:abc", b"partial AT reply"):
            session = self.session()
            self.assertEqual(session.feed(prefix), 0)
            error = session.expire()
            self.assertLess(error, 0)
            self.assertEqual(session.feed(b"\r\nOK\r\n"), error)
            self.assertEqual(session.events, [])

    def test_new_session_clears_partial_state_and_connection_mode(self):
        session = self.session()
        self.assertEqual(session.feed(b"+IPD,0,20:abc"), 0)
        self.assertLess(session.expire(), 0)
        session.reset(0)
        self.assertEqual(session.feed(b"+IPD,1:z\r\nOK\r\n"), 0)
        self.assertEqual(session.events, [(DATA, -1, b"z"), (LINE, -1, b"OK")])

    def test_null_arguments_and_idle_expiry(self):
        session = self.session()
        self.assertEqual(session.expire(), 0)
        self.assertEqual(session.feed(b""), 0)
        self.assertLess(self.lib.ew_esp_stream_feed(None, None, 0), 0)
        self.assertLess(self.lib.ew_esp_stream_feed(session.pointer, None, 1), 0)
        self.assertLess(self.lib.ew_esp_stream_expire(None), 0)
        self.assertLess(self.lib.ew_esp_stream_init(session.pointer, 2, session.callback, None), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
