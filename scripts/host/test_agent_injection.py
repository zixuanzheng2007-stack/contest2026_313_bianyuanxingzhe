"""Verify real Tool injection, repeatability, and missing-anchor rejection."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]


def shell_path(path: Path) -> str:
    value = path.resolve().as_posix()
    return "/" + value[0].lower() + value[2:] if os.name == "nt" else value


def main() -> None:
    bash = shutil.which("bash")
    if os.name == "nt":
        bash = next((str(p) for p in (
            Path("C:/msys64/usr/bin/bash.exe"),
            Path("C:/Program Files/Git/bin/bash.exe"),
        ) if p.is_file()), None)
    if not bash:
        raise RuntimeError("Bash required (Windows: MSYS2 or Git Bash)")
    with tempfile.TemporaryDirectory(prefix="ew_injection_") as directory:
        workspace = Path(directory)
        package = workspace / "packages/ai_agent"
        tools = package / "src/tools"
        tools.mkdir(parents=True)
        cmake = package / "CMakeLists.txt"
        make = package / "Makefile"
        registry = tools / "tool_registry.c"
        cmake.write_text("src/tools/tool_control.c\n", encoding="utf-8")
        make.write_text("CSRCS += src/tools/tool_control.c\n", encoding="utf-8")
        registry.write_text('#include "tools/tool_control.h"\nvoid init(void) {\n'
                            'tool_launch_quickapp_execute);\n}\n', encoding="utf-8")
        env = os.environ.copy()
        env["PATH"] = str(Path(bash).parent) + os.pathsep + env.get("PATH", "")
        env.update(OPENVELA=shell_path(workspace), CONTEST=shell_path(ROOT),
                   EW_PATCH_ONLY="1", SKIP_REPO_SYNC="1")
        command = [bash, shell_path(ROOT / "app/edge_walker/sync_and_build.sh")]
        def inject():
            return subprocess.run(command, env=env, capture_output=True, text=True, timeout=30)
        first = inject()
        assert first.returncode == 0, first.stdout + first.stderr
        files = [cmake, make, registry, tools / "tool_approach_alert_ipc.c",
                 tools / "tool_approach_alert.h", tools / "ew_alert_ipc.h"]
        before = [p.read_bytes() for p in files]
        second = inject()
        assert second.returncode == 0, second.stdout + second.stderr
        assert before == [p.read_bytes() for p in files]
        assert registry.read_text(encoding="utf-8").count('"approach_alert"') == 1
        assert 'TOOL_PARAM_STR("event_id"' in registry.read_text(encoding="utf-8")
        # An earlier managed version must receive the new schema too.
        registry.write_text(registry.read_text(encoding="utf-8").replace(
            'TOOL_PARAM_STR("event_id"', 'TOOL_PARAM_STR("old_event_id"'), encoding="utf-8")
        upgraded = inject()
        assert upgraded.returncode == 0, upgraded.stdout + upgraded.stderr
        assert before == [p.read_bytes() for p in files]
        stamp = workspace / "cmake_out/sf32lb52_devkit_lcd_ai_agent/.ew_agent_patch_stamp"
        assert len(stamp.read_text().splitlines()) == 6
        # Simulate an interrupted build: .config already contains the required
        # settings, but the generated C header still has UART3 disabled.
        fake = workspace / "fake-bin"
        fake.mkdir()
        (fake / "git").write_text("#!/usr/bin/env bash\nexit 0\n", newline="\n")
        (fake / "olddefconfig").write_text(
            '#!/usr/bin/env bash\necho olddefconfig >> "$TEST_CONFIG_LOG"\n', newline="\n")
        (fake / "cmake").write_text(r'''#!/usr/bin/env bash
echo "$*" >> "$TEST_CONFIG_LOG"
if [[ "$1" == -E ]]; then
  rm -f "$4"
elif [[ "$1" == -B ]]; then
  mkdir -p "$2/include/nuttx" "$OPENVELA/nuttx"
  if [[ ! -f "$2/.config" ]]; then
    cat > "$2/.config" <<'CONFIG'
CONFIG_EXAMPLES_AI_AGENT_VELA=y
CONFIG_LVX_USE_DEMO_CONTEST2026_313_EDGE_WALKER=y
CONFIG_BSP_USING_UART3=y
CONFIG_BSP_UART3_RX_USING_DMA=y
CONFIG_LV_USE_NUTTX=y
CONFIG
    echo '#define CONFIG_LV_USE_NUTTX 1' > "$2/include/nuttx/config.h"
  fi
elif [[ "$1" == --build && "$*" == *nuttx_context* ]]; then
  sed -n 's/^\(CONFIG_[^=]*\)=y/#define \1 1/p' "$2/.config" > "$2/include/nuttx/config.h"
elif [[ "$1" == --build ]]; then
  printf 'fixture image' > "$2/nuttx.bin"
else
  exit 23
fi
''', newline="\n")
        for executable in fake.iterdir():
            executable.chmod(0o755)
        config_log = workspace / "config.log"
        env.update(EW_PATCH_ONLY="0", TEST_CONFIG_LOG=shell_path(config_log))
        env["PATH"] = str(fake) + os.pathsep + env["PATH"]
        env["EW_TEST_FAKE_BIN"] = shell_path(fake)
        # Bash functions outrank any user tool wrappers in ~/bin, which the
        # production script intentionally puts before PATH entries.
        command = [bash, "-c", '''
git() { "$EW_TEST_FAKE_BIN/git" "$@"; }
cmake() { "$EW_TEST_FAKE_BIN/cmake" "$@"; }
olddefconfig() { "$EW_TEST_FAKE_BIN/olddefconfig" "$@"; }
env() {
  if [[ "${@: -1}" == olddefconfig ]]; then
    "$EW_TEST_FAKE_BIN/olddefconfig"
  else
    command env "$@"
  fi
}
export -f git cmake olddefconfig env
exec bash "$1"
''', "fixture", shell_path(ROOT / "app/edge_walker/sync_and_build.sh")]
        resumed = inject()
        assert resumed.returncode == 0, resumed.stdout + resumed.stderr
        assert config_log.read_text().count("olddefconfig") == 1
        config_log.write_text("")
        repeated = inject()
        assert repeated.returncode == 0, repeated.stdout + repeated.stderr
        assert "olddefconfig" not in config_log.read_text()
        env["EW_PATCH_ONLY"] = "1"
        cmake.write_text("# missing source anchor\n", encoding="utf-8")
        failed = inject()
        assert failed.returncode != 0 and "check injection anchors" in failed.stderr
    print("PASS: registry injected, idempotent schema, hashes, missing anchor and stale config header recovery")


if __name__ == "__main__":
    main()
