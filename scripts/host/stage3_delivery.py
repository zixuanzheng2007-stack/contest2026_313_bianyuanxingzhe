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
import io
import tarfile
import stat
from pathlib import PurePosixPath, PureWindowsPath
from firmware_provenance import check_config, source_digest, digest

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
    "scripts/host/firmware_provenance.py",
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
            check_config(config.read_bytes()), kind,
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

    # Refuse secrets before copying anything into a distributable directory.
    check_config(main_config.read_bytes())
    if agent_files is not None: check_config(agent_files[2].read_bytes())
    _check_build_receipt(main_build_dir, source_digest(ROOT))
    if agent_build_dir is not None: _check_build_receipt(agent_build_dir, source_digest(ROOT))
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
        _copy_file(main_build_dir / "source_receipt.json", package_dir / "firmware/main/source_receipt.json")
        if agent_files is not None:
            agent_bin, agent_elf, agent_config = agent_files
            _copy_file(agent_bin, package_dir / "firmware/agent/nuttx.bin")
            _copy_file(agent_elf, package_dir / "firmware/agent/nuttx")
            _copy_file(agent_config, package_dir / "firmware/agent/.config")
            _copy_file(agent_build_dir / "source_receipt.json", package_dir / "firmware/agent/source_receipt.json")
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
        verify_package(package_dir)  # Verify before publishing any final path.
        verify_package(stage / final_zip.name)
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


def _safe_name(relative: str) -> str:
    if (not isinstance(relative, str) or not relative or "\\" in relative
            or ":" in relative or any(ord(c) < 32 for c in relative)
            or PureWindowsPath(relative).anchor or PurePosixPath(relative).is_absolute()
            or any(p in {"", ".", ".."} or p.endswith((" ", "."))
                   or p.split(".")[0].upper() in {"CON", "PRN", "AUX", "NUL", *('COM'+str(i) for i in range(1,10)), *('LPT'+str(i) for i in range(1,10))}
                   for p in relative.split("/"))):
        raise DeliveryError("Unsafe package path")
    return relative


def _json(data: bytes) -> dict:
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result: raise DeliveryError("Duplicate JSON key")
            result[key] = value
        return result
    value = json.loads(data.decode("utf-8"), object_pairs_hook=unique)
    if not isinstance(value, dict): raise DeliveryError("Expected JSON object")
    return value


def _parse_checksums(data: bytes) -> dict[str, str]:
    entries = {}
    for line in data.decode("utf-8").splitlines():
        match = re.fullmatch(r"([0-9a-f]{64})  ([^\r\n]+)", line)
        if not match: raise DeliveryError("Malformed SHA256SUMS")
        value, name = match.groups()
        _safe_name(name)
        if name in entries: raise DeliveryError("Duplicate checksum path")
        entries[name] = value
    if not entries: raise DeliveryError("Empty SHA256SUMS")
    return entries


def _check_build_receipt(build: Path, expected: str) -> None:
    payload = _json((build / "source_receipt.json").read_bytes())
    if payload.get("source_tree_sha256") != expected:
        raise DeliveryError("Build/source provenance mismatch")
    if payload.get("files") != {n: digest((build/n).read_bytes()) for n in ('nuttx.bin','nuttx','.config')}:
        raise DeliveryError("Build receipt does not match firmware inputs")


def _validate_contents(names: set[str], read) -> dict:
    for name in names: _safe_name(name)
    required = {MANIFEST_FILE, CHECKSUM_FILE, STATUS_FILE, 'source/source_input.tgz',
                'source/input_manifest.json', 'rollback/nuttx.bin', 'firmware/main/nuttx.bin',
                'firmware/main/nuttx', 'firmware/main/.config', 'firmware/main/source_receipt.json'}
    if not required <= names: raise DeliveryError("Package missing required contents")
    sums = _parse_checksums(read(CHECKSUM_FILE))
    if set(sums) != names - {CHECKSUM_FILE}: raise DeliveryError("Unchecked or missing package contents")
    for name, value in sums.items():
        if digest(read(name)) != value: raise DeliveryError("Checksum mismatch: " + name)
    manifest = _json(read(MANIFEST_FILE))
    if (manifest.get('board_tested') is not False or manifest.get('flash_address') != FLASH_ADDRESS
            or manifest.get('schema') != 1 or manifest.get('kind') != 'edge_walker_final_delivery'
            or not isinstance(manifest.get('version'), str) or not VERSION_PATTERN.fullmatch(manifest['version'])):
        raise DeliveryError("Invalid delivery manifest")
    listed = {}
    for entry in manifest.get('files', []):
        name = _safe_name(entry['path'])
        if name in listed or entry.get('bytes') != len(read(name)):
            raise DeliveryError("Invalid manifest entry")
        listed[name] = entry['sha256']
    if listed != {n:v for n,v in sums.items() if n != MANIFEST_FILE}:
        raise DeliveryError("Manifest/checksum mismatch")
    status = _json(read(STATUS_FILE))
    if status.get('board_tested') is not False or any(status.get(n) != 'PENDING' for n in
        ('flash','physical_screen_buzzer','three_consecutive_demos','thirty_page_switches','two_hour_stability')):
        raise DeliveryError("Invalid physical acceptance claim")
    source = _json(read('source/input_manifest.json'))
    entries = source.get('files', {})
    expected = digest(json.dumps(entries, sort_keys=True, separators=(',', ':')).encode())
    archive = read('source/source_input.tgz')
    if (not isinstance(entries, dict) or not entries or source.get('source_tree_sha256') != expected
            or source.get('archive_sha256') != digest(archive)
            or manifest.get('source') != {'source_tree_sha256': expected, 'archive_sha256': digest(archive)}):
        raise DeliveryError("Invalid source provenance")
    with tarfile.open(fileobj=io.BytesIO(archive), mode='r:gz') as stream:
        found = set(); total = 0
        for member in stream:
            _safe_name(member.name)
            total += member.size
            if (not member.isfile() or member.name in found or member.name not in entries
                    or member.size > 64*1024*1024 or total > 512*1024*1024):
                raise DeliveryError("Invalid source archive member")
            data = stream.extractfile(member).read()
            if entries[member.name] != {'sha256':digest(data),'bytes':len(data)}:
                raise DeliveryError("Source archive/manifest mismatch")
            found.add(member.name)
        if found != set(entries): raise DeliveryError("Incomplete source archive")
    for kind in ('main','agent'):
        prefix = 'firmware/' + kind + '/'
        present = any(n.startswith(prefix) for n in names)
        if kind == 'agent' and not present:
            if manifest.get('firmware',{}).get('agent') is not None: raise DeliveryError("Missing Agent firmware")
            continue
        if not {prefix+n for n in ('nuttx.bin','nuttx','.config','source_receipt.json')} <= names:
            raise DeliveryError("Incomplete firmware set")
        config = check_config(read(prefix+'.config'))
        report = verify_firmware(read(prefix+'nuttx'),read(prefix+'nuttx.bin'),config,kind)
        if manifest.get('firmware',{}).get(kind) != report: raise DeliveryError("Firmware report mismatch")
        receipt = _json(read(prefix+'source_receipt.json'))
        if (receipt.get('source_tree_sha256') != expected or receipt.get('files') !=
                {n:digest(read(prefix+n)) for n in ('nuttx.bin','nuttx','.config')}):
            raise DeliveryError("Firmware/source receipt mismatch")
    if not read('rollback/nuttx.bin') or manifest.get('rollback_sha256') != digest(read('rollback/nuttx.bin')):
        raise DeliveryError("Invalid rollback image")
    return {'passed':True,'version':manifest['version'],'files':len(sums),
            'board_tested':False,'physical_acceptance':'PENDING'}


def _verify_directory(package_dir: Path) -> dict:
    # lstat every component before following anything: junctions may target UNC.
    def regular(path):
        info = path.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info,'st_file_attributes',0) & 0x400:
            raise DeliveryError("Package links/reparse points are forbidden")
    import os
    names = set()
    for directory, folders, files in os.walk(package_dir, followlinks=False):
        for name in folders: regular(Path(directory)/name)
        for name in files:
            path = Path(directory)/name; regular(path)
            names.add(path.relative_to(package_dir).as_posix())
    def read(name):
        _safe_name(name)
        path = package_dir
        for part in name.split('/'):
            path = path/part; regular(path)
        if path.stat().st_size > 512*1024*1024: raise DeliveryError("Package member too large")
        return path.read_bytes()
    return _validate_contents(names,read)


def _verify_zip(package_zip: Path) -> dict:
    with zipfile.ZipFile(package_zip) as archive:
        members = archive.infolist()
        if len(members)>4096: raise DeliveryError("Too many ZIP members")
        mapping = {}; prefix = None; total = 0
        for info in members:
            _safe_name(info.filename.rstrip('/'))
            if info.is_dir(): continue
            if stat.S_ISLNK(info.external_attr >> 16): raise DeliveryError("ZIP links forbidden")
            parts = info.filename.split('/',1)
            if len(parts)!=2: raise DeliveryError("ZIP must have one version directory")
            if prefix is None: prefix = parts[0]
            if prefix != parts[0] or parts[1] in mapping: raise DeliveryError("Invalid ZIP layout")
            total += info.file_size
            if info.file_size>512*1024*1024 or total>1024*1024*1024: raise DeliveryError("ZIP too large")
            mapping[parts[1]] = info.filename
        return _validate_contents(set(mapping),lambda n:archive.read(mapping[_safe_name(n)]))


def verify_package(package: Path) -> dict:
    package = package.expanduser().resolve()
    try:
        if package.is_dir(): return _verify_directory(package)
        if package.is_file() and package.suffix.lower()=='.zip': return _verify_zip(package)
        raise DeliveryError("Package is neither a directory nor ZIP")
    except (KeyError, TypeError, ValueError, OSError, tarfile.TarError) as exc:
        raise DeliveryError(str(exc)) from exc


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
