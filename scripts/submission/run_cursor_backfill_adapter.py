#!/usr/bin/env python3
"""Invoke the official Cursor adapter directly when its wrapper lacks bash."""

import argparse
import sys
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("adapter_dir", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument("team_id")
    parser.add_argument("github_login")
    args = parser.parse_args()

    sys.path.insert(0, str(args.adapter_dir))
    import backfill_cursor  # type: ignore[import-not-found]

    count = backfill_cursor.backfill(
        args.destination, args.team_id, args.github_login
    )
    print(f"exported={count}")


if __name__ == "__main__":
    main()
