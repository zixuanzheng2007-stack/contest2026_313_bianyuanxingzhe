#!/bin/bash
export PATH="$HOME/bin:$PATH"
cd ~/openvela
echo "=== list configs ==="
./nuttx/tools/configure.sh -L sf32lb52 2>&1 | head -80
echo "=== tree ==="
find vendor/sifli/boards/sf32lb52 -maxdepth 4 -type d 2>/dev/null | head -60
echo "=== defconfigs ==="
find vendor/sifli/boards/sf32lb52 -name defconfig 2>/dev/null | head -40
echo "=== build.sh help snippet ==="
grep -A30 'function usage\|Usage\|usage()' build.sh | head -50
# how other boards are invoked
grep -RIn "sf32lb52_devkit" --include='*.md' --include='*.sh' vendor/sifli 2>/dev/null | head -20