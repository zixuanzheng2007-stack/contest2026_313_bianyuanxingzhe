"""Bind a successful build to unchanged, credential-free source inputs."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import re
import secrets

from prepare_firmware_candidate import collect_files

SENSITIVE = re.compile(r'API_KEY|ACCESS_TOKEN|PASSWORD|PASSPHRASE|CLIENT_SECRET|WIFI_.*(?:SSID|PASS|SECRET)|MIMO_.*(?:KEY|TOKEN)')


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def check_config(data: bytes) -> str:
    config = data.decode('utf-8')
    for line in config.splitlines():
        if '=' not in line or line.lstrip().startswith('#'):
            continue
        key, value = line.split('=', 1)
        if SENSITIVE.search(key.upper()) and value.strip() not in {'n', '0', '""', ''}:
            raise ValueError('Sensitive build configuration must be cleared and rebuilt: ' + key)
    return config


def source_digest(root: Path) -> str:
    entries = {}
    for path in collect_files(root):
        data = path.read_bytes()
        if path.suffix in {'.sh', '.patch'} and b'\r\n' in data:
            raise ValueError('Build input requires LF: ' + path.relative_to(root).as_posix())
        entries[path.relative_to(root).as_posix()] = {'sha256': digest(data), 'bytes': len(data)}
    return digest(json.dumps(entries, sort_keys=True, separators=(',', ':')).encode())


def receipt(root: Path, build: Path, expected: str) -> dict:
    actual = source_digest(root)
    if actual != expected:
        raise ValueError('Source changed during build')
    values = {name: digest((build / name).read_bytes()) for name in ('nuttx.bin', 'nuttx', '.config')}
    check_config((build / '.config').read_bytes())
    payload = {'schema': 1, 'source_tree_sha256': actual, 'files': values, 'board_tested': False}
    target = build / 'source_receipt.json'
    temporary = target.with_name(target.name + '.' + secrets.token_hex(8))
    try:
        temporary.write_text(json.dumps(payload, indent=2) + '\n', encoding='utf-8')
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)
    return payload


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['digest', 'record'])
    parser.add_argument('--root', required=True, type=Path)
    parser.add_argument('--build-dir', type=Path)
    parser.add_argument('--expected')
    args = parser.parse_args()
    if args.command == 'digest':
        print(source_digest(args.root.resolve()))
    else:
        if args.build_dir is None or args.expected is None:
            parser.error('record requires --build-dir and --expected')
        receipt(args.root.resolve(), args.build_dir.resolve(), args.expected)


if __name__ == '__main__':
    main()
