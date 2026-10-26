#!/usr/bin/env bash
# One-time: enable pre-push rebase hook for this repo
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

git config core.hooksPath .githooks
chmod +x .githooks/pre-push scripts/git/pre_push_rebase.sh 2>/dev/null || true
chmod +x .cursor/hooks/before-push-rebase.sh 2>/dev/null || true

echo "OK: core.hooksPath=.githooks"
echo "Pre-push will run: scripts/git/pre_push_rebase.sh"
