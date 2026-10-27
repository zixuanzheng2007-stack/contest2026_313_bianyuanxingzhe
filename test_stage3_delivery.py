# SPDX-License-Identifier: Apache-2.0
"""Final delivery packages must be verifiable, versioned, and tamper evident."""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import tempfile
import unittest
import uuid

from stage3_delivery import DeliveryError, ROOT, seal_release, verify_package
from test_firmware_candidate import fixture


class Stage3DeliveryTests(unittest.TestCase):
    def setUp(self):
        self.output = ROOT / "output" / ("stage3_test_" + uuid.uuid4().hex)
        self.base = Path(tempfile.mkdtemp(prefix="stage3_fixture_"))

    def tearDown(self):
        if self.output.exists():
            resolved = self.output.resolve()
            self.assertTrue(resolved.is_relative_to((ROOT / "output").resolve()))
            shutil.rmtree(self.output)
        shutil.rmtree(self.base, ignore_errors=True)

    def build_dir(self, name: str, kind: str) -> Path:
        directory = self.base / name
        directory.mkdir()
        elf, image, config = fixture(kind)
        (directory / "nuttx").write_bytes(elf)
        (directory / "nuttx.bin").write_bytes(image)
        (directory / ".config").write_text(config, encoding="utf-8")
        return directory

    def test_seal_and_verify_directory_and_zip(self):
        main = self.build_dir("main", "main")
        agent = self.build_dir("agent", "agent")
        rollback = self.base / "rollback.bin"
        rollback.write_bytes(b"known-good-rollback")
        apk = self.base / "app.apk"
        apk.write_bytes(b"fixture-apk")

        result = seal_release(
            version="ew-test-final",
            main_build_dir=main,
            agent_build_dir=agent,
            rollback_bin=rollback,
            apk=apk,
            output=self.output,
            created_at="2026-10-27T00:00:00+00:00",
        )
        directory = Path(result["output"])
        archive = Path(result["zip"])
        self.assertTrue(directory.is_dir())
        self.assertTrue(archive.is_file())
        self.assertEqual(verify_package(directory)["files"], verify_package(archive)["files"])
        self.assertFalse(verify_package(archive)["board_tested"])
        manifest = json.loads((directory / "delivery_manifest.json").read_text(encoding="utf-8"))
        self.assertFalse(manifest["board_tested"])
        self.assertEqual(manifest["flash_address"], "0x12010000")
        status = json.loads((directory / "acceptance_status.json").read_text(encoding="utf-8"))
        for key in ("flash", "physical_screen_buzzer", "three_consecutive_demos"):
            self.assertEqual(status[key], "PENDING")
        self.assertTrue((directory / "firmware/main/nuttx.bin").is_file())
        self.assertTrue((directory / "firmware/agent/nuttx.bin").is_file())
        self.assertTrue((directory / "rollback/nuttx.bin").is_file())
        self.assertTrue((directory / "source/source_input.tgz").is_file())

    def test_tampering_and_overwrite_are_rejected(self):
        main = self.build_dir("main", "main")
        rollback = self.base / "rollback.bin"
        rollback.write_bytes(b"known-good-rollback")
        result = seal_release(
            version="ew-test-tamper",
            main_build_dir=main,
            agent_build_dir=None,
            rollback_bin=rollback,
            output=self.output,
            created_at="2026-10-27T00:00:00+00:00",
        )
        with self.assertRaises(DeliveryError):
            seal_release(
                version="ew-test-tamper",
                main_build_dir=main,
                agent_build_dir=None,
                rollback_bin=rollback,
                output=self.output,
                created_at="2026-10-27T00:00:00+00:00",
            )
        manifest = Path(result["output"]) / "delivery_manifest.json"
        original_manifest = manifest.read_bytes()
        manifest.write_bytes(original_manifest + b"tamper")
        with self.assertRaises(DeliveryError):
            verify_package(Path(result["output"]))
        manifest.write_bytes(original_manifest)
        binary = Path(result["output"]) / "firmware/main/nuttx.bin"
        binary.write_bytes(binary.read_bytes() + b"tamper")
        with self.assertRaises(DeliveryError):
            verify_package(Path(result["output"]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
