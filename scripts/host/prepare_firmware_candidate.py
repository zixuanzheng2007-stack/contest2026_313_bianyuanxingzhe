# SPDX-License-Identifier: Apache-2.0
"""Seal a minimal build source archive without credential headers or generated files."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import os
import subprocess
import tarfile
import uuid

ROOT = Path(__file__).resolve().parents[2]
EXCLUDED_NAMES = {"ew_mimo_bootstrap.h", "ew_wifi_secret.h", ".env", "credentials.json"}
EXCLUDED_SUFFIXES = {".o", ".elf", ".bin", ".exe", ".pyc", ".log", ".pem"}
SOURCE_DIRECTORIES = ("app/edge_walker", "board_overlay/sf32lb52_devkit_lcd",
                      "scripts/guest", "scripts/patches")
TEST_SUPPORT = ("tools/ew_panel.py", "scripts/host/board_snapshot_acceptance.py",
                "scripts/host/verify_firmware_candidate.py",
                "scripts/host/fixtures/radar_safety/synthetic_sequence.csv")


def collect_files(root: Path) -> list[Path]:
    selected = []
    for relative in SOURCE_DIRECTORIES:
        folder = root / relative
        if not folder.is_dir():
            raise ValueError("Required source directory missing: " + relative)
        selected.extend(path for path in folder.rglob("*") if path.is_file())
    for name in ("LICENSE", "NOTICE", ".gitattributes", "requirements-test.txt",
                 "scripts/host/prepare_firmware_candidate.py", "scripts/host/run_tests.py",
                 *TEST_SUPPORT):
        path = root / name
        if path.is_file():
            selected.append(path)
    selected.extend((root / "scripts/host").glob("test_*.py"))
    # Selected modules are needed by Linux software regressions, not by firmware.
    for name in ("mobile_device_simulator.py", "mobile_serial_gateway.py", "mobile_prototype_gateway.py", "radar_replay.py",
                 "serial_common.py", "generate_mimo_bootstrap.py", "stage3_delivery.py",
                 "stage3_demo_acceptance.py", "firmware_provenance.py"):
        path = root / "scripts/host" / name
        if path.is_file():
            selected.append(path)
    files = []
    for path in sorted(set(selected)):
        if (path.name in EXCLUDED_NAMES or path.suffix.lower() in EXCLUDED_SUFFIXES
                or any(part in (".git", "__pycache__") for part in path.parts)):
            continue
        if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
            raise ValueError("Source links must be reviewed explicitly: " + path.relative_to(root).as_posix())
        files.append(path)
    return files


def seal(root: Path, output: Path, version: str, git_head: str | None = None) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    stage = output / (".source-" + uuid.uuid4().hex + ".tgz")
    manifest_stage = output / (".manifest-" + uuid.uuid4().hex + ".json")
    entries = {}
    try:
        with tarfile.open(stage, "w:gz") as archive:
            for path in collect_files(root):
                relative = path.relative_to(root).as_posix()
                data = path.read_bytes()
                if path.suffix in {".sh", ".patch"} and b"\r\n" in data:
                    raise ValueError("Linux build input requires LF line endings: " + relative)
                entries[relative] = {"sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}
                info = tarfile.TarInfo(relative)
                info.size = len(data)
                info.mode = 0o755 if path.suffix == ".sh" else 0o644
                info.mtime = int(path.stat().st_mtime)
                archive.addfile(info, io.BytesIO(data))
        # Do not claim an in-progress source edit was the source we sealed.
        for relative, entry in entries.items():
            if hashlib.sha256((root / relative).read_bytes()).hexdigest() != entry["sha256"]:
                raise RuntimeError("Source changed during export: " + relative)
        canonical = json.dumps(entries, sort_keys=True, separators=(",", ":")).encode()
        manifest = {
            "version": version, "sealed_at_utc": datetime.now(timezone.utc).isoformat(),
            "git_head": git_head, "source_tree_sha256": hashlib.sha256(canonical).hexdigest(),
            "archive": "source_input.tgz", "archive_sha256": hashlib.sha256(stage.read_bytes()).hexdigest(),
            "files": entries, "excluded_credential_headers": sorted(EXCLUDED_NAMES),
            "scope": "contest_firmware_and_host_test_sources_requires_existing_openvela_sdk",
            "board_tested": False,
        }
        manifest_stage.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(stage, output / "source_input.tgz")
        os.replace(manifest_stage, output / "input_manifest.json")
        return manifest
    finally:
        if stage.exists():
            stage.unlink()  # Only this invocation's exact temporary file.
        if manifest_stage.exists():
            manifest_stage.unlink()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path,
                        default=ROOT / "VMware_share/artifacts/full_firmware_20261024/input")
    parser.add_argument("--version", default="ew-main-20261024-snapshot1")
    args = parser.parse_args()
    output = args.output.resolve()
    if not any(output.is_relative_to((ROOT / name).resolve())
               for name in ("output", "VMware_share/artifacts")):
        parser.error("Output must stay inside project output/ or VMware_share/artifacts/")
    result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True,
                            text=True, timeout=10)
    manifest = seal(ROOT, output, args.version, result.stdout.strip() if result.returncode == 0 else None)
    print(json.dumps({"output": str(output), "version": manifest["version"],
                      "source_files": len(manifest["files"]),
                      "archive_sha256": manifest["archive_sha256"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
