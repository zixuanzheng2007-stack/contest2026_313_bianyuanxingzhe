#!/bin/bash
export PATH="$HOME/bin:$PATH"
echo "=== curl github ==="
curl -I -m 15 https://github.com 2>&1 | head -5
echo "=== curl ghproxy ==="
curl -I -m 15 https://ghproxy.net/https://github.com/open-vela/nuttx 2>&1 | head -8
echo "=== curl gitclone ==="
curl -I -m 15 https://gitclone.com/github.com/open-vela/nuttx 2>&1 | head -8
echo "=== curl ghfast ==="
curl -I -m 15 https://ghfast.top/https://github.com/open-vela/nuttx 2>&1 | head -8
echo "=== missing arm gcc dir? ==="
ls -la ~/openvela/prebuilts/gcc/linux-x86_64/
ls ~/openvela/.repo/projects/prebuilts/gcc/linux-x86_64/ 2>/dev/null