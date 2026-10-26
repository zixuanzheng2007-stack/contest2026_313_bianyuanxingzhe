#!/usr/bin/env bash
# PR 前必跑：同步 upstream、检测 merge 冲突
set -eu
BASE="${1:-dev-ai-contest-2026}"
BRANCH="${2:-$(git rev-parse --abbrev-ref HEAD)}"
ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

echo "== pre_pr_check =="
echo "branch: $BRANCH -> upstream/$BASE"

git fetch upstream "$BASE"
git fetch origin "$BRANCH" 2>/dev/null || true

if [ -n "$(git status --porcelain | grep -v '^??' || true)" ]; then
  echo "FAIL: tracked files modified/staged"
  git status -sb
  exit 2
fi

MB="$(git merge-base HEAD "upstream/$BASE")"
if git merge-tree "$MB" HEAD "upstream/$BASE" | grep -q "changed in both"; then
  echo "FAIL: merge conflicts with upstream/$BASE"
  git merge-tree "$MB" HEAD "upstream/$BASE" | grep "changed in both" | head -20
  echo "Run: git merge upstream/$BASE && resolve && push"
  exit 1
fi

echo "OK: no merge conflict with upstream/$BASE"
echo "ahead:  $(git rev-list --count "upstream/$BASE..HEAD")"
echo "behind: $(git rev-list --count "HEAD..upstream/$BASE")"
echo "pre_pr_check passed."
