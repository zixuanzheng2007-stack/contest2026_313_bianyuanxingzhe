#!/bin/bash
set -e
mkdir -p ~/.ssh && chmod 700 ~/.ssh
curl -fsSL http://192.168.126.1:8765/windows_host.pub >> ~/.ssh/authorized_keys
sort -u ~/.ssh/authorized_keys -o ~/.ssh/authorized_keys
chmod 600 ~/.ssh/authorized_keys
mkdir -p ~/openvela-handoff
curl -fsSL http://192.168.126.1:8765/UBUNTU_CURSOR_HANDOFF.md -o ~/openvela-handoff/UBUNTU_CURSOR_HANDOFF.md
echo "=== whoami ==="; whoami
echo "=== IP ==="; hostname -I
echo "=== last key ==="; tail -1 ~/.ssh/authorized_keys
echo OK