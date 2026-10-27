#!/usr/bin/env python3
"""Seal and verify the final Edge Walker delivery package.

The package contains the main firmware, an optional independent ai_agent
firmware, a rollback image, source input, tools, checksums, and a status file.
It never marks flash, physical, demo, or long-run checks as passed.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from prepare_firmware_candidate import seal as seal_source
from verify_firmware_candidate import verify as verify_firmware

VERSION_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
FLASH_ADDRESS = "0x12010000"
STATUS_FILE = "acceptance_status.json"
MANIFEST_FILE = "delivery_manifest.json"
CHECKSUM_FILE = "SHA256SUMS"
TOOL_FILES = (
    "scripts/host/stage3_delivery.py",
    "scripts/host/stage3_demo_acceptance.py",
    "scripts/host/verify_firmware_candidate.py",
    "scripts/host/prepare_firmware_candidate.py",
    "scripts/host/serial_common.py",
    "scripts/guest/build_stage3_release.sh",
    "requirements-test.txt",
)
DOC_FILES = (
    "docs/复赛/阶段三_封版交付.md",
    "docs/复赛/阶段三_连续三次演示记录.csv",
    "docs/烧录/烧录与调试.md",
    "docs/提交材料/Demo脚本与验收步骤.md",
)


class DeliveryError(RuntimeError):
    """The package is incomplete, inconsistent, or unsafe to publish."""


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _required_file(path: Path, label: str) -> Path:
    path = path.expanduser().resolve()
    if not path.is_file() or path.stat().st_size == 0:
        raise DeliveryError(f"{label} is missing or empty: {path}")
    return path


def _build_files(directory: Path) -> tuple[Path, Path, Path]:
    directory = directory.expanduser().resolve()
    files = (directory / "nuttx.bin", directory / "nuttx", directory / ".config")
    labels = ("nuttx.bin", "nuttx ELF", ".config")
    return tuple(_required_file(path, labels[index]) for index, path in enumerate(files))


def _copy_file(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def _copy_repo_file(relative: str, destination: Path) -> None:
    source = ROOT / relative
    if not source.is_file():
        raise DeliveryError(f"Required repository file is missing: {relative}")
    _copy_file(source, destination)


def _firmware_report(binary: Path, elf: Path, config: Path, kind: str) -> dict:
    try:
        report = verify_firmware(
            elf.read_bytes(), binary.read_bytes(),
            config.read_bytes().decode("utf-8"), kind,
        )
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        raise DeliveryError(f"{kind} firmware verification failed: {exc}") from exc
    if report.get("flash_address") != FLASH_ADDRESS:
        raise DeliveryError(f"{kind} firmware has unexpected flash address")
    if report.get("board_tested") is not False:
        raise DeliveryError(f"{kind} firmware report made an invalid board claim")
    return report


def _write_json(path: Path, value: dict) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _write_status(path: Path) -> None:
    _write_json(path, {
        "schema": 1,
        "scope": "final_delivery",
        "host_delivery_verification": "PASS",
        "offline_firmware_verification": "PASS",
        "flash": "PENDING",
        "physical_screen_buzzer": "PENDING",
        "three_consecutive_demos": "PENDING",
        "thirty_page_switches": "PENDING",
        "two_hour_stability": "PENDING",
        "board_tested": False,
        "note": "Host and offline checks do not prove physical board behavior.",
    })


def _write_readme(path: Path, version: str, has_agent: bool, has_apk: bool) -> None:
    agent_note = (
        "`firmware/agent/nuttx.bin` 与主固件是二选一镜像，不是两个同时烧录的分区。\n"
        if has_agent else "本包未包含独立 ai_agent 镜像。\n"
    )
    apk_note = "`mobile/edge-walker-companion.apk` 为可选手机端，不参与板端烧录。\n" if has_apk else ""
    path.write_text(
        f"""# 边缘行者封版交付包 {version}

本包由 `stage3_delivery.py` 生成。先核对 `SHA256SUMS`，再烧录。

## 产物

- `firmware/main/nuttx.bin`：主固件，烧录地址 `{FLASH_ADDRESS}`。
- `rollback/nuttx.bin`：留存回退镜像，烧录地址同样为 `{FLASH_ADDRESS}`。
{agent_note}{apk_note}- `source/`：本次构建源码输入和清单。
- `{STATUS_FILE}`：实板项目保持 `PENDING`，不能把主机通过写成真机通过。

## 烧录主固件

关闭 PuTTY 和其他串口工具，在仓库根目录确认实际 COM 口。
把 `<release>` 替换为本包目录：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/host/flash_sf32.ps1 `
  -Port COM7 `
  -Firmware "<release>/firmware/main/nuttx.bin@{FLASH_ADDRESS}"
```

不要整片擦除，不要把 ELF 入口地址当成烧录地址。

## 连续三次演示

烧录并重启后执行：

```powershell
python scripts/host/stage3_demo_acceptance.py --port COM7 --runs 3
```

脚本只判软件日志链。屏幕、蜂鸣和真实雷达仍需人工观察，并在
`docs/复赛/阶段三_连续三次演示记录.csv` 记录。

## 回退

```powershell
powershell -ExecutionPolicy Bypass -File scripts/host/flash_sf32.ps1 `
  -Port COM7 `
  -Firmware "<release>/rollback/nuttx.bin@{FLASH_ADDRESS}"
```

源码回退以 Git 提交、`source/input_manifest.json` 和 PR Revert 为准，不强推。
""",
        encoding="utf-8",
    )


def _package_files(package_dir: Path, *, include_manifest: bool) -> list[Path]:
    excluded = {CHECKSUM_FILE}
    if not include_manifest:
        excluded.add(MANIFEST_FILE)
    return sorted(
        path for path in package_dir.rglob("*")
        if path.is_file() and path.name not in excluded
    )


def _entry(path: Path, root: Path) -> dict:
    return {
        "path": path.relative_to(root).as_posix(),
        "sha256": sha256_file(path),
        "bytes": path.stat().st_size,
    }


def _write_manifest(
    package_dir: Path,
    *,
    version: str,
    created_at: str,
    git_head: str | None,
    main_report: dict,
    agent_report: dict | None,
    rollback_hash: str,
    apk_hash: str | None,
    source_manifest: dict,
) -> dict:
    payload = {
        "schema": 1,
        "kind": "edge_walker_final_delivery",
        "version": version,
        "sealed_at_utc": created_at,
        "git_head": git_head,
        "board": "sf32lb52_devkit_lcd",
        "flash_address": FLASH_ADDRESS,
        "board_tested": False,
        "firmware": {
            "main": main_report,
            "agent": agent_report,
        },
        "rollback_sha256": rollback_hash,
        "apk_sha256": apk_hash,
        "source": {
            "source_tree_sha256": source_manifest["source_tree_sha256"],
            "archive_sha256": source_manifest["archive_sha256"],
        },
        "files": [
            _entry(path, package_dir)
            for path in _package_files(package_dir, include_manifest=False)
        ],
    }
    _write_json(package_dir / MANIFEST_FILE, payload)
    return payload


def _write_checksums(package_dir: Path) -> None:
    lines = [
        f"{sha256_file(path)}  {path.relative_to(package_dir).as_posix()}"
        for path in _package_files(package_dir, include_manifest=True)
    ]
    (package_dir / CHECKSUM_FILE).write_text("\n".join(lines) + "\n", encoding="utf-8")


def _zip_package(package_dir: Path, zip_path: Path) -> None:
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED,
                         compresslevel=6) as archive:
        for path in sorted(package_dir.rglob("*")):
            if not path.is_file():
                continue
            relative = (Path(package_dir.name) / path.relative_to(package_dir)).as_posix()
            info = zipfile.ZipInfo(relative, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (path.stat().st_mode & 0xFFFF) << 16
            archive.writestr(info, path.read_bytes())


def _allowed_output(output: Path) -> bool:
    resolved = output.expanduser().resolve()
    return any(
        resolved != base.resolve() and resolved.is_relative_to(base.resolve())
        for base in (ROOT / "output", ROOT / "VMware_share/artifacts")
    )


def seal_release(
    *,
    version: str,
    main_build_dir: Path,
    agent_build_dir: Path | None,
    rollback_bin: Path,
    output: Path,
    apk: Path | None = None,
    created_at: str | None = None,
) -> dict:
    """Create a new versioned directory and ZIP; never overwrite an old one."""
    if not VERSION_PATTERN.fullmatch(version):
        raise DeliveryError("Version must use 1-64 letters, digits, dot, dash, or underscore")
    output = output.expanduser().resolve()
    if not _allowed_output(output):
        raise DeliveryError("Output must stay inside output/ or VMware_share/artifacts/")

    main_bin, main_elf, main_config = _build_files(main_build_dir)
    agent_files = _build_files(agent_build_dir) if agent_build_dir else None
    rollback_bin = _required_file(rollback_bin, "rollback image")
    apk = _required_file(apk, "APK") if apk else None
    main_report = _firmware_report(main_bin, main_elf, main_config, "main")
    agent_report = (
        _firmware_report(*agent_files, "agent") if agent_files is not None else None
    )

    output.mkdir(parents=True, exist_ok=True)
    final_dir = output / version
    final_zip = output / f"{version}.zip"
    final_zip_hash = output / f"{version}.zip.sha256"
    for path in (final_dir, final_zip, final_zip_hash):
        if path.exists():
            raise DeliveryError(f"Refusing to overwrite existing output: {path}")

    stage = Path(tempfile.mkdtemp(prefix=".stage3-", dir=output))
    package_dir = stage / version
    try:
        _copy_file(main_bin, package_dir / "firmware/main/nuttx.bin")
        _copy_file(main_elf, package_dir / "firmware/main/nuttx")
        _copy_file(main_config, package_dir / "firmware/main/.config")
        if agent_files is not None:
            agent_bin, agent_elf, agent_config = agent_files
            _copy_file(agent_bin, package_dir / "firmware/agent/nuttx.bin")
            _copy_file(agent_elf, package_dir / "firmware/agent/nuttx")
            _copy_file(agent_config, package_dir / "firmware/agent/.config")
        _copy_file(rollback_bin, package_dir / "rollback/nuttx.bin")
        if apk is not None:
            _copy_file(apk, package_dir / "mobile/edge-walker-companion.apk")

        source_manifest = seal_source(ROOT, package_dir / "source", version, _git_head())
        for relative in TOOL_FILES:
            _copy_repo_file(relative, package_dir / "tools" / Path(relative).name)
        for relative in DOC_FILES:
            source = ROOT / relative
            if source.is_file():
                _copy_file(source, package_dir / "docs" / Path(relative).name)

        _write_status(package_dir / STATUS_FILE)
        _write_readme(
            package_dir / "README.md",
            version,
            agent_report is not None,
            apk is not None,
        )
        _write_manifest(
            package_dir,
            version=version,
            created_at=created_at or datetime.now(timezone.utc).isoformat(),
            git_head=_git_head(),
            main_report=main_report,
            agent_report=agent_report,
            rollback_hash=sha256_file(rollback_bin),
            apk_hash=sha256_file(apk) if apk is not None else None,
            source_manifest=source_manifest,
        )
        _write_checksums(package_dir)

        _zip_package(package_dir, stage / final_zip.name)
        (stage / final_zip_hash.name).write_text(
            f"{sha256_file(stage / final_zip.name)}  {final_zip.name}\n",
            encoding="utf-8",
        )
        package_dir.rename(final_dir)
        (stage / final_zip.name).rename(final_zip)
        (stage / final_zip_hash.name).rename(final_zip_hash)
    finally:
        if stage.exists():
            shutil.rmtree(stage)

    result = verify_package(final_dir)
    if not result["passed"]:
        raise DeliveryError("Self-verification failed after sealing")
    return {
        "output": str(final_dir),
        "zip": str(final_zip),
        "zip_sha256": sha256_file(final_zip),
        "files": result["files"],
        "board_tested": False,
        "physical_acceptance": "PENDING",
    }


def _git_head() -> str | None:
    marker = ROOT / ".git"
    if not marker.exists():
        return None
    try:
        import subprocess
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT, capture_output=True, text=True, timeout=10, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return result.stdout.strip() if result.returncode == 0 else None


def _parse_checksums(data: bytes) -> dict[str, str]:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise DeliveryError("SHA256SUMS is not UTF-8") from exc
    entries: dict[str, str] = {}
    for number, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        match = re.fullmatch(r"([0-9a-f]{64})  ([^\r\n]+)", line)
        if not match:
            raise DeliveryError(f"Malformed SHA256SUMS line {number}")
        digest, relative = match.groups()
        if relative in entries:
            raise DeliveryError(f"Duplicate SHA256SUMS path: {relative}")
        if relative.startswith("/") or ".." in Path(relative).parts:
            raise DeliveryError(f"Unsafe package path: {relative}")
        entries[relative] = digest
    if not entries:
        raise DeliveryError("SHA256SUMS is empty")
    return entries


def _verify_directory(package_dir: Path) -> dict:
    checksum_path = package_dir / CHECKSUM_FILE
    manifest_path = package_dir / MANIFEST_FILE
    if not checksum_path.is_file() or not manifest_path.is_file():
        raise DeliveryError("Package lacks SHA256SUMS or delivery_manifest.json")
    sums = _parse_checksums(checksum_path.read_bytes())
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DeliveryError("delivery_manifest.json is invalid") from exc
    if manifest.get("board_tested") is not False:
        raise DeliveryError("Manifest must keep board_tested=false")
    if manifest.get("flash_address") != FLASH_ADDRESS:
        raise DeliveryError("Manifest has an unexpected flash address")
    for relative, expected in sums.items():
        path = package_dir / relative
        if not path.is_file():
            raise DeliveryError(f"Checksummed file is missing: {relative}")
        if sha256_file(path) != expected:
            raise DeliveryError(f"Checksum mismatch: {relative}")
    listed = {entry["path"]: entry["sha256"] for entry in manifest.get("files", [])}
    checksummed_without_manifest = {
        path: digest for path, digest in sums.items() if path != MANIFEST_FILE
    }
    if listed != checksummed_without_manifest:
        raise DeliveryError("Manifest file list does not match SHA256SUMS")
    return {
        "passed": True,
        "version": manifest.get("version"),
        "files": len(sums),
        "board_tested": False,
        "physical_acceptance": "PENDING",
    }


def _verify_zip(package_zip: Path) -> dict:
    with zipfile.ZipFile(package_zip) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise DeliveryError("ZIP contains duplicate names")
        roots = {name.split("/", 1)[0] for name in names if "/" in name}
        if len(roots) != 1:
            raise DeliveryError("ZIP must contain one top-level version directory")
        prefix = roots.pop() + "/"
        checksum_name = prefix + CHECKSUM_FILE
        if checksum_name not in names:
            raise DeliveryError("ZIP lacks SHA256SUMS")
        sums = _parse_checksums(archive.read(checksum_name))
        for relative, expected in sums.items():
            member = prefix + relative
            if member not in names:
                raise DeliveryError(f"ZIP member is missing: {member}")
            if sha256_bytes(archive.read(member)) != expected:
                raise DeliveryError(f"ZIP checksum mismatch: {member}")
        if prefix + MANIFEST_FILE not in names:
            raise DeliveryError("ZIP lacks delivery_manifest.json")
        try:
            manifest = json.loads(archive.read(prefix + MANIFEST_FILE).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise DeliveryError("ZIP delivery_manifest.json is invalid") from exc
        if manifest.get("board_tested") is not False:
            raise DeliveryError("Manifest must keep board_tested=false")
        listed = {entry["path"]: entry["sha256"] for entry in manifest.get("files", [])}
        checksummed_without_manifest = {
            path: digest for path, digest in sums.items() if path != MANIFEST_FILE
        }
        if listed != checksummed_without_manifest:
            raise DeliveryError("ZIP manifest file list does not match SHA256SUMS")
    return {"passed": True, "version": manifest.get("version"),
            "files": len(sums), "board_tested": False,
            "physical_acceptance": "PENDING"}


def verify_package(package: Path) -> dict:
    package = package.expanduser().resolve()
    if package.is_dir():
        return _verify_directory(package)
    if package.is_file() and package.suffix.lower() == ".zip":
        return _verify_zip(package)
    raise DeliveryError(f"Package is neither a directory nor ZIP: {package}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    seal = commands.add_parser("seal", help="Create a versioned delivery package")
    seal.add_argument("--version", required=True)
    seal.add_argument("--main-build-dir", required=True, type=Path)
    seal.add_argument("--agent-build-dir", type=Path)
    seal.add_argument("--rollback-bin", required=True, type=Path)
    seal.add_argument("--apk", type=Path)
    seal.add_argument("--output", default=ROOT / "output/stage3", type=Path)
    seal.add_argument("--created-at")

    verify = commands.add_parser("verify", help="Verify a directory or ZIP")
    verify.add_argument("--package", required=True, type=Path)

    args = parser.parse_args()
    try:
        if args.command == "seal":
            result = seal_release(
                version=args.version,
                main_build_dir=args.main_build_dir,
                agent_build_dir=args.agent_build_dir,
                rollback_bin=args.rollback_bin,
                apk=args.apk,
                output=args.output,
                created_at=args.created_at,
            )
        else:
            result = verify_package(args.package)
    except (DeliveryError, OSError, ValueError, json.JSONDecodeError, zipfile.BadZipFile) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
