#!/usr/bin/env python3
"""Windows-friendly wrapper: load contest-collector.env without bash."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[2].parent / ".claude/skills/contest-log-collector/tools"
if not TOOLS.is_dir():
    TOOLS = Path.home() / "openvela/.claude/skills/contest-log-collector/tools"
sys.path.insert(0, str(TOOLS.parent / "adapters" / "cursor"))
sys.path.insert(0, str(TOOLS))

import backfill_cursor  # noqa: E402


def load_env() -> tuple[str, str]:
    env_path = Path.home() / ".claude" / "contest-collector.env"
    data: dict[str, str] = {}
    if env_path.is_file():
        for line in env_path.read_text(encoding="utf-8-sig").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                data[k.strip()] = v.strip()
    team = data.get("TEAM_ID", "")
    login = data.get("GITHUB_LOGIN", "")
    if not team or not login:
        raise SystemExit(
            f"Missing TEAM_ID/GITHUB_LOGIN in {env_path}. Run install.sh first."
        )
    return team, login


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--dest", required=True)
    p.add_argument("--github-login")
    p.add_argument("--confirm", action="store_true")
    args = p.parse_args()
    dest = Path(args.dest)
    team_id, login = load_env()
    if args.github_login:
        login = args.github_login
    print(f"Destination: {dest}/logs/")
    print(f"GitHub login: {login}")
    if not args.confirm:
        print("[preview] pass --confirm to write")
        return 0
    n = backfill_cursor.backfill(dest, team_id, login)
    print(f"\nBackfill done: {n} session(s) imported.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
