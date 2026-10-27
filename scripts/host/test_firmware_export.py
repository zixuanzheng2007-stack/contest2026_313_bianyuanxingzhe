# SPDX-License-Identifier: Apache-2.0
"""Source delivery must bind exact bytes and omit credential/generated files."""
import hashlib
import json
from pathlib import Path
import tarfile
import tempfile
import unittest

from prepare_firmware_candidate import SOURCE_DIRECTORIES, TEST_SUPPORT, seal


class FirmwareExport(unittest.TestCase):
    def test_archive_matches_manifest_without_credentials_or_objects(self):
        with tempfile.TemporaryDirectory(prefix="ew_export_") as directory:
            root = Path(directory)
            for name in SOURCE_DIRECTORIES:
                (root / name).mkdir(parents=True)
            source = root / "app/edge_walker"
            (source / "main.c").write_bytes(b"/* stable source */\n")
            for name in ("ew_mimo_bootstrap.h", "ew_wifi_secret.h", "old.o", "old.bin"):
                (source / name).write_bytes(b"must not export")
            output = root / "delivery"
            manifest = seal(root, output, "test-version")
            self.assertEqual(set(manifest["files"]), {"app/edge_walker/main.c"})
            archive = output / "source_input.tgz"
            self.assertEqual(hashlib.sha256(archive.read_bytes()).hexdigest(), manifest["archive_sha256"])
            with tarfile.open(archive, "r:gz") as packed:
                self.assertEqual(packed.getnames(), ["app/edge_walker/main.c"])
                data = packed.extractfile(packed.getmembers()[0]).read()
                self.assertEqual(hashlib.sha256(data).hexdigest(), manifest["files"][packed.getnames()[0]]["sha256"])
            self.assertEqual(json.loads((output / "input_manifest.json").read_text())["version"], "test-version")

    def test_missing_input_does_not_replace_previous_delivery(self):
        with tempfile.TemporaryDirectory(prefix="ew_export_failure_") as directory:
            root = Path(directory)
            output = root / "delivery"
            output.mkdir()
            (output / "source_input.tgz").write_bytes(b"previous")
            (output / "input_manifest.json").write_bytes(b"previous metadata")
            with self.assertRaises(ValueError):
                seal(root, output, "bad")
            self.assertEqual((output / "source_input.tgz").read_bytes(), b"previous")
            self.assertEqual((output / "input_manifest.json").read_bytes(), b"previous metadata")
            self.assertEqual(len(list(output.iterdir())), 2)

    def test_test_support_and_nested_fixture_survive_export(self):
        with tempfile.TemporaryDirectory(prefix="ew_export_support_") as directory:
            root = Path(directory)
            for name in SOURCE_DIRECTORIES:
                (root / name).mkdir(parents=True)
            for name in TEST_SUPPORT:
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"test-support\n")
            roadtest = root / "scripts/host/test_roadtest_capture.py"
            roadtest.parent.mkdir(parents=True, exist_ok=True)
            roadtest.write_bytes(b"test-support\n")
            manifest = seal(root, root / "delivery", "with-test-support")
            self.assertEqual(set(manifest["files"]), set(TEST_SUPPORT) | {
                "scripts/host/test_roadtest_capture.py"})

    def test_crlf_shell_cannot_be_published_as_linux_build_input(self):
        with tempfile.TemporaryDirectory(prefix="ew_export_crlf_") as directory:
            root = Path(directory)
            for name in SOURCE_DIRECTORIES:
                (root / name).mkdir(parents=True)
            (root / "scripts/patches/fix.sh").write_bytes(b"#!/bin/bash\r\nset -e\r\n")
            output = root / "delivery"
            with self.assertRaisesRegex(ValueError, "LF line endings"):
                seal(root, output, "invalid-shell")
            self.assertEqual(list(output.iterdir()), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
