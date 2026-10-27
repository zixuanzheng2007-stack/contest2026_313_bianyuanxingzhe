#!/usr/bin/env bash
# Build sealed Host inputs without writing to the existing Guest workspace.
set -euo pipefail
ORIGINAL="${ORIGINAL:-$HOME/openvela}"
INPUT_DIR="${INPUT_DIR:-/mnt/hgfs/VMware_share/artifacts/full_firmware_20261025/input_lf}"
ARTIFACT_DIR="${ARTIFACT_DIR:-/mnt/hgfs/VMware_share/artifacts/full_firmware_20261025/build}"
EXPECTED_ARCHIVE_SHA256="${EXPECTED_ARCHIVE_SHA256:-29b46bbf5c58bb279f73a21c0b464f363965ba38f1265006f215a90378cc72b0}"
EW_BUILD_JOBS="${EW_BUILD_JOBS:-8}"
export EW_BUILD_JOBS
[[ "$EW_BUILD_JOBS" =~ ^[1-8]$ ]] || { echo 'EW_BUILD_JOBS must be 1..8'; exit 2; }
[[ -d "$ORIGINAL/nuttx" && -f "$INPUT_DIR/input_manifest.json" ]] || exit 2
[[ ! -e "$ARTIFACT_DIR" ]] || { echo 'Refusing to overwrite an existing build artifact directory'; exit 2; }
mkdir -p "$ARTIFACT_DIR"
if [[ -n "${REUSE_RUN_ROOT:-}" ]]; then
  RUN_ROOT=$(realpath "$REUSE_RUN_ROOT")
  [[ "$RUN_ROOT" == "$HOME"/ew_isolated_20261025.* && -d "$RUN_ROOT/workspace/nuttx" ]] || {
    echo 'Refusing to reuse a workspace outside the private build directories'; exit 2;
  }
else
  RUN_ROOT=$(mktemp -d "$HOME/ew_isolated_20261025.XXXXXX")
fi
WORKSPACE="$RUN_ROOT/workspace"
export ORIGINAL RUN_ROOT WORKSPACE INPUT_DIR ARTIFACT_DIR EXPECTED_ARCHIVE_SHA256
printf '%s\n' "$RUN_ROOT" > "$ARTIFACT_DIR/private_workspace.txt"
exec > >(tee "$ARTIFACT_DIR/driver.log") 2>&1
trap 'rc=$?; trap - ERR; printf "ISOLATED_BUILD_FAILED exit=%s line=%s\n" "$rc" "$LINENO"; if declare -F snapshot_original >/dev/null; then snapshot_original "$ARTIFACT_DIR/original_after_failure.json"; fi; exit "$rc"' ERR
cp "$0" "$ARTIFACT_DIR/build_ew_isolated.sh"
sha256sum "$0" > "$ARTIFACT_DIR/driver.sha256"

# Hash only selected existing source/configuration paths; never print credentials.
snapshot_original() {
  python3 - "$1" <<'PY'
import os, json, hashlib, subprocess, sys
from pathlib import Path
root=Path(os.environ['ORIGINAL'])
paths=[root/'contest2026_313_bianyuanxingzhe/app/edge_walker',
 root/'vendor/sifli/boards/sf32lb52/sf32lb52_devkit_lcd',
 root/'vendor/sifli/drivers',root/'packages/ai_agent',
 root/'cmake_out/sf32lb52_devkit_lcd/.config',
 root/'cmake_out/sf32lb52_devkit_lcd/nuttx.bin']
files={}
for base in paths:
 for p in ([base] if base.is_file() else sorted(base.rglob('*'))):
  if p.is_file() and not p.is_symlink() and '.git' not in p.parts:
   files[str(p.relative_to(root))]=hashlib.sha256(p.read_bytes()).hexdigest()
status={}
for d in ('contest2026_313_bianyuanxingzhe','vendor/sifli','packages/ai_agent'):
 r=subprocess.run(['git','-C',str(root/d),'status','--porcelain','--untracked-files=all'],capture_output=True,text=True)
 status[d]={'code':r.returncode,'status':r.stdout}
Path(sys.argv[1]).write_text(json.dumps({'files':files,'git_status':status},indent=2))
PY
}
snapshot_original "$ARTIFACT_DIR/original_before.json"
echo "[isolation] preparing writable source trees in $WORKSPACE"
mkdir -p "$WORKSPACE"
if [[ -z "${REUSE_RUN_ROOT:-}" ]]; then
  for d in nuttx apps vendor packages external frameworks build; do
    rsync -a --exclude=.git "$ORIGINAL/$d" "$WORKSPACE/"
  done
fi
# Toolchains are reused, while build output and all writable source are private.
if [[ ! -L "$WORKSPACE/prebuilts" ]]; then
  ln -s "$ORIGINAL/prebuilts" "$WORKSPACE/prebuilts"
fi
python3 <<'PY'
import os,json,hashlib,tarfile,re
from pathlib import Path
old=Path(os.environ['ORIGINAL']).resolve(); new=Path(os.environ['WORKSPACE']).resolve()
out=Path(os.environ['ARTIFACT_DIR']); inputs=Path(os.environ['INPUT_DIR'])
archive=inputs/'source_input.tgz'
assert hashlib.sha256(archive.read_bytes()).hexdigest()==os.environ['EXPECTED_ARCHIVE_SHA256']
manifest=json.loads((inputs/'input_manifest.json').read_text())
contest=new/'contest2026_313_bianyuanxingzhe'; contest.mkdir(exist_ok=True)
with tarfile.open(archive,'r:gz') as t:
 for m in t.getmembers():
  p=Path(m.name)
  assert not p.is_absolute() and '..' not in p.parts and m.isfile(),m.name
 t.extractall(contest,filter='data')
for name,metadata in manifest['files'].items():
 assert hashlib.sha256((contest/name).read_bytes()).hexdigest()==metadata['sha256'],name
rewritten=[]
for d in ('nuttx','apps','vendor','packages','external','frameworks','build'):
 for p in (new/d).rglob('*'):
  if p.is_symlink():
   target=os.readlink(p)
   if target.startswith(str(old)+'/'):
    replacement=str(new)+target[len(str(old)):]
    p.unlink(); p.symlink_to(replacement); rewritten.append(str(p.relative_to(new)))
# The existing demo is a link, and its target is replaced only in this workspace.
demo=new/'packages/demos/contest2026_313_edge_walker'
if demo.is_symlink(): demo.unlink()
assert not demo.exists(), 'Private demo unexpectedly is a real directory'
demo.symlink_to(contest/'app/edge_walker')
bad=[]
for d in ('nuttx','apps','vendor','packages','external','frameworks','build'):
 for p in (new/d).rglob('*'):
  if p.is_symlink():
   resolved=p.resolve()
   if resolved.is_relative_to(old): bad.append(str(p.relative_to(new)))
assert not bad, 'Writable source links escape to original workspace: '+repr(bad)
forbidden={'ew_mimo_bootstrap.h','ew_wifi_secret.h','.env','credentials.json'}
assert not any(p.name in forbidden for p in (contest/'app/edge_walker').rglob('*'))
build=new/'cmake_out/sf32lb52_devkit_lcd'; build.mkdir(parents=True,exist_ok=True)
seed=(old/'cmake_out/sf32lb52_devkit_lcd/.config').read_text()
sanitized=[]; lines=[]
pattern=r'(?:API_KEY|ACCESS_TOKEN|WIFI_.*(?:SSID|PASS|SECRET)|MIMO_.*(?:KEY|TOKEN)|PASSWORD|PASSPHRASE|CLIENT_SECRET)'
for line in seed.splitlines():
 if '=' in line:
  key,value=line.split('=',1)
  if re.search(pattern,key) and value not in ('n','""','0'):
   sanitized.append(key); line=key+'=""'
 lines.append(line)
(build/'.config').write_text('\n'.join(lines)+'\n')
(out/'isolation.json').write_text(json.dumps({'private_workspace':str(new),'rewritten_links':rewritten,
 'sanitized_config_fields':sanitized,'input_archive_sha256':os.environ['EXPECTED_ARCHIVE_SHA256'],
 'source_tree_sha256':manifest['source_tree_sha256'],
 'prebuilts_reused':True,'board_tested':False},indent=2))
PY
export OPENVELA="$WORKSPACE" CONTEST="$WORKSPACE/contest2026_313_bianyuanxingzhe"
export PATH="$HOME/bin:$HOME/.local/bin:$WORKSPACE/prebuilts/gcc/linux-x86_64/arm-none-eabi/bin:$WORKSPACE/prebuilts/build-tools/linux-x86_64/bin:$PATH"
export SKIP_REPO_SYNC=1
SOURCE_INPUT_SHA=$(python3 "$CONTEST/scripts/host/firmware_provenance.py" digest --root "$CONTEST")

collect_image() {
  local kind="$1" build="$2" dest="$ARTIFACT_DIR/$1"
  mkdir -p "$dest"
  python3 "$CONTEST/scripts/host/firmware_provenance.py" record --root "$CONTEST" \
    --build-dir "$build" --expected "$SOURCE_INPUT_SHA"
  cp "$build/source_receipt.json" "$dest/source_receipt.json"
  cp "$build/nuttx.bin" "$dest/nuttx.bin"
  cp "$build/nuttx" "$dest/nuttx"
  cp "$build/.config" "$dest/.config"
  if [[ -f "$build/nuttx.map" ]]; then cp "$build/nuttx.map" "$dest/nuttx.map"; fi
  arm-none-eabi-nm -an "$build/nuttx" > "$dest/symbols.txt"
  arm-none-eabi-readelf -lW "$build/nuttx" > "$dest/program_headers.txt"
  arm-none-eabi-size "$build/nuttx" > "$dest/size.txt"
  python3 - "$kind" "$dest" <<'PY'
import json,hashlib,os,sys
from pathlib import Path
d=Path(sys.argv[2]); names=('nuttx.bin','nuttx','.config','symbols.txt','program_headers.txt','build.log')
files={n:{'sha256':hashlib.sha256((d/n).read_bytes()).hexdigest(),'bytes':(d/n).stat().st_size} for n in names if (d/n).is_file()}
config=(d/'.config').read_text()
assert ('CONFIG_EXAMPLES_AI_AGENT_VELA=y' in config)==(sys.argv[1]=='agent')
(d/'build_manifest.json').write_text(json.dumps({'kind':sys.argv[1],'status':'pass','board_tested':False,
 'input_archive_sha256':os.environ['EXPECTED_ARCHIVE_SHA256'],
 'source_tree_sha256':manifest['source_tree_sha256'],'files':files},indent=2))
PY
}
mkdir -p "$ARTIFACT_DIR/main" "$ARTIFACT_DIR/agent"
echo '[isolation] main full build'
BUILD_DIR="$WORKSPACE/cmake_out/sf32lb52_devkit_lcd" \
 ARTIFACT_DIR="$ARTIFACT_DIR/main" bash "$CONTEST/scripts/guest/build_ew_main.sh" \
 > "$ARTIFACT_DIR/main/build.log" 2>&1
collect_image main "$WORKSPACE/cmake_out/sf32lb52_devkit_lcd"
echo '[isolation] independent ai_agent full build'
bash "$CONTEST/app/edge_walker/sync_and_build.sh" > "$ARTIFACT_DIR/agent/build.log" 2>&1
collect_image agent "$WORKSPACE/cmake_out/sf32lb52_devkit_lcd_ai_agent"
snapshot_original "$ARTIFACT_DIR/original_after.json"
cmp "$ARTIFACT_DIR/original_before.json" "$ARTIFACT_DIR/original_after.json"
printf 'ISOLATED_BUILD_OK original_unchanged=yes board_tested=no\n'
