# SPDX-License-Identifier: Apache-2.0
"""Final delivery packages must be verifiable, versioned, and tamper evident."""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import tempfile
import unittest
import uuid

from stage3_delivery import DeliveryError, ROOT, seal_release, verify_package, _parse_checksums
import hashlib
import zipfile
from test_firmware_candidate import fixture
from firmware_provenance import receipt, source_digest


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
        receipt(ROOT, directory, source_digest(ROOT))
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

    def test_windows_absolute_unc_and_ads_paths_rejected_before_io(self):
        for name in ['C:/outside.txt', 'C:\\outside.txt', r'\\server\share\secret',
                     '../outside', 'folder/../outside', 'file:stream', 'CON', 'a\\b', '/absolute']:
            with self.subTest(name=name), self.assertRaises(DeliveryError):
                _parse_checksums(('0'*64+'  '+name+'\n').encode())

    def test_empty_self_consistent_package_is_rejected(self):
        package = self.base / 'empty'
        package.mkdir()
        data = json.dumps({'board_tested':False,'flash_address':'0x12010000','files':[]}).encode()
        (package/'delivery_manifest.json').write_bytes(data)
        (package/'SHA256SUMS').write_text(hashlib.sha256(data).hexdigest()+'  delivery_manifest.json\n')
        archive = self.base/'empty.zip'
        with zipfile.ZipFile(archive,'w') as output:
            for path in package.iterdir(): output.write(path,'empty/'+path.name)
        for path in [package,archive]:
            with self.subTest(path=str(path)), self.assertRaises(DeliveryError): verify_package(path)

    def test_secret_configuration_cannot_be_published(self):
        main = self.build_dir('secret','main')
        with (main/'.config').open('a') as stream: stream.write('CONFIG_REVIEW_API_KEY="SYNTHETIC_NOT_A_REAL_KEY"\n')
        rollback = self.base/'rollback.bin';rollback.write_bytes(b'fixture')
        with self.assertRaisesRegex((ValueError,DeliveryError),'Sensitive'):
            seal_release(version='secret',main_build_dir=main,agent_build_dir=None,
                         rollback_bin=rollback,output=self.output)
        self.assertFalse((self.output/'secret.zip').exists())

    def test_stale_source_receipt_cannot_label_current_source(self):
        main = self.build_dir('old','main')
        record = json.loads((main/'source_receipt.json').read_text())
        record['source_tree_sha256'] = '0'*64
        (main/'source_receipt.json').write_text(json.dumps(record))
        rollback = self.base/'rollback.bin';rollback.write_bytes(b'fixture')
        with self.assertRaisesRegex(DeliveryError,'provenance'):
            seal_release(version='stale',main_build_dir=main,agent_build_dir=None,
                         rollback_bin=rollback,output=self.output)
        self.assertFalse((self.output/'stale.zip').exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
