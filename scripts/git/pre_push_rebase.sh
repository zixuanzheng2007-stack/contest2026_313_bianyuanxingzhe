#!/usr/bin/env bash
# Rebase current branch onto upstream base before push.
# Called by .githooks/pre-push and Cursor beforeShellExecution hook.
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel 2>/dev/null || true)"
if [[ -z "$ROOT" ]]; then
  echo "pre_push_rebase: not inside a git repository" >&2
  exit 1
fi
cd "$ROOT"

CONFIG="${ROOT}/scripts/git/rebase.config.env"
UPSTREAM_REMOTE="${UPSTREAM_REMOTE:-upstream}"
BASE_BRANCH="${BASE_BRANCH:-dev-ai-contest-2026}"
if [[ -f "$CONFIG" ]]; then
  # shellcheck disable=SC1090
  source "$CONFIG"
fi
# Local-only override (not in git)
LOCAL_CONFIG="${ROOT}/.cursor/skills/pre-push-rebase/config.env"
if [[ -f "$LOCAL_CONFIG" ]]; then
  # shellcheck disable=SC1090
  source "$LOCAL_CONFIG"
fi

BASE_REF="${UPSTREAM_REMOTE}/${BASE_BRANCH}"

if [[ -d .git/rebase-merge || -d .git/rebase-apply ]]; then
  echo "pre_push_rebase: rebase already in progress — run 'git rebase --continue' or 'git rebase --abort'" >&2
  git diff --name-only --diff-filter=U 2>/dev/null || true
  exit 1
fi

if ! git remote get-url "$UPSTREAM_REMOTE" &>/dev/null; then
  echo "pre_push_rebase: remote '$UPSTREAM_REMOTE' not configured — skip rebase" >&2
  exit 0
fi

echo "pre_push_rebase: fetch ${UPSTREAM_REMOTE} ${BASE_BRANCH}..."
git fetch "$UPSTREAM_REMOTE" "$BASE_BRANCH" --quiet

if ! git rev-parse --verify "$BASE_REF" &>/dev/null; then
  echo "pre_push_rebase: ${BASE_REF} not found after fetch" >&2
  exit 1
fi

UPSTREAM_TIP="$(git rev-parse "$BASE_REF")"
MERGE_BASE="$(git merge-base HEAD "$BASE_REF" 2>/dev/null || echo "")"

if [[ "$MERGE_BASE" == "$UPSTREAM_TIP" ]]; then
  echo "pre_push_rebase: already rebased on ${BASE_REF}"
  exit 0
fi

CURRENT="$(git branch --show-current)"
echo "pre_push_rebase: rebasing ${CURRENT:-HEAD} onto ${BASE_REF}..."

if ! git rebase "$BASE_REF"; then
  echo "" >&2
  echo "pre_push_rebase: CONFLICT — resolve files below, then:" >&2
  echo "  git add <resolved>" >&2
  echo "  git rebase --continue" >&2
  echo "  git push --force-with-lease" >&2
  echo "" >&2
  echo "Conflicted files:" >&2
  git diff --name-only --diff-filter=U >&2 || true
  echo "" >&2
  echo "See scripts/git/README.md for resolution rules." >&2
  exit 1
fi

echo "pre_push_rebase: rebase OK onto ${BASE_REF}"
exit 0
