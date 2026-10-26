"""A failed configure/build must never publish an old firmware as new."""
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]


def shell_path(path: Path) -> str:
    value = path.resolve().as_posix()
    return '/' + value[0].lower() + value[2:] if os.name == 'nt' else value


def main() -> None:
    bash = shutil.which('bash')
    if os.name == 'nt':
        bash = next((str(p) for p in (
            Path('C:/msys64/usr/bin/bash.exe'), Path('C:/Program Files/Git/bin/bash.exe'),
        ) if p.is_file()), None)
    assert bash, 'Bash is required'
    with tempfile.TemporaryDirectory(prefix='ew_delivery_') as directory:
        base = Path(directory)
        workspace, contest, build, artifacts = (base / n for n in (
            'workspace', 'contest', 'build', 'artifacts'))
        source = contest / 'app/edge_walker'
        source.mkdir(parents=True)
        (source / 'test.c').write_text('/* fixture */\n')
        board = workspace / 'vendor/sifli/boards/sf32lb52/sf32lb52_devkit_lcd'
        config = board / 'configs/nsh/defconfig'
        config.parent.mkdir(parents=True)
        config.write_text('CONFIG_LVX_USE_DEMO_CONTEST2026_313_EDGE_WALKER=y\n')
        (workspace / 'nuttx').mkdir()
        build.mkdir()
        (build / '.config').write_text(config.read_text())
        (build / 'nuttx.bin').write_bytes(b'old build image')
        artifacts.mkdir()
        published = {
            'nuttx.bin': b'previous known good image',
            'nuttx.bin.sha256': b'previous hash',
            'nuttx.build.txt': b'previous metadata',
        }
        for name, content in published.items():
            (artifacts / name).write_bytes(content)
        # The wrapper places a fixture cmake first without changing the user's PATH.
        fake = base / 'bin'
        fake.mkdir()
        (fake / 'cmake').write_text('''#!/usr/bin/env bash
if [[ "$1" == "--build" ]]; then
  [[ "${FAIL_PHASE:-}" != build ]] || exit 17
  printf 'fresh firmware' > "$2/nuttx.bin"
else
  [[ "${FAIL_PHASE:-}" != configure ]] || exit 18
fi
''', newline='\n')
        (fake / 'cmake').chmod(0o755)
        # Fail only metadata hashing, after cmake has succeeded.
        hash_env = os.environ.copy()
        hash_env['PATH'] = str(Path(bash).parent) + os.pathsep + hash_env.get('PATH', '')
        real_hash = subprocess.check_output([bash, '-c', 'command -v sha256sum'],
                                            env=hash_env, text=True).strip()
        (fake / 'sha256sum').write_text(
            '#!/usr/bin/env bash\n'
            'if [[ "${FAIL_PHASE:-}" == hash && "${1:-}" == */.config ]]; then exit 19; fi\n'
            'exec "' + real_hash + '" "$@"\n', newline='\n')
        (fake / 'sha256sum').chmod(0o755)
        wrapper = base / 'run.sh'
        wrapper.write_text(
            '#!/usr/bin/env bash\nexport PATH="' + shell_path(fake) + ':$PATH"\n'
            'exec bash "' + shell_path(ROOT / 'scripts/guest/build_ew_main.sh') + '"\n',
            newline='\n')
        env = os.environ.copy()
        env['PATH'] = str(Path(bash).parent) + os.pathsep + env.get('PATH', '')
        env.update(OPENVELA=shell_path(workspace), CONTEST=shell_path(contest),
                   BUILD_DIR=shell_path(build), ARTIFACT_DIR=shell_path(artifacts))
        def run(phase: str):
            # MSYS2 may copy directories when native symlinks are unavailable.
            # Reset only that disposable fixture between independent scenarios.
            demo = workspace / 'packages/demos/contest2026_313_edge_walker'
            if demo.is_symlink():
                demo.unlink()
            elif demo.exists():
                assert demo.resolve().is_relative_to(base.resolve())
                shutil.rmtree(demo)
            return subprocess.run([bash, shell_path(wrapper)], env={**env, 'FAIL_PHASE': phase},
                                  capture_output=True, text=True, timeout=30)
        for phase in ('configure', 'build', 'hash'):
            result = run(phase)
            assert result.returncode != 0, result.stdout + result.stderr
            assert result.returncode == {'configure': 18, 'build': 17, 'hash': 19}[phase], result.stdout + result.stderr
            assert 'BUILD_OK' not in result.stdout
            assert {name: (artifacts / name).read_bytes() for name in published} == published
        overlay = contest / 'board_overlay/sf32lb52_devkit_lcd'
        overlay.mkdir(parents=True)
        required = 'CONFIG_BSP_UART3_RX_USING_DMA=y\n'
        (overlay / 'wifi_dma.config').write_text(required)
        result = run('')
        assert result.returncode == 3 and 'Existing build config lacks' in result.stdout
        assert {name: (artifacts / name).read_bytes() for name in published} == published
        # The script must preserve this configuration until the caller fixes it.
        assert required not in (build / '.config').read_text()
        (build / '.config').write_text(config.read_text() + required)
        result = run('')
        assert result.returncode == 0, result.stdout + result.stderr
        assert 'BUILD_OK' in result.stdout
        assert (artifacts / 'nuttx.bin').read_bytes() == b'fresh firmware'
        digest = hashlib.sha256(b'fresh firmware').hexdigest()
        assert (artifacts / 'nuttx.bin.sha256').read_text().split()[0] == digest
        metadata = (artifacts / 'nuttx.build.txt').read_text()
        assert digest in metadata and 'source_sha256=' in metadata and 'config_sha256=' in metadata
        assert not list(artifacts.glob('.ew_release.*'))
    print('PASS: configure/build failures preserve delivery; success publishes image, hash and metadata')


if __name__ == '__main__':
    main()
