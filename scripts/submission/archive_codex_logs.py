#!/usr/bin/env python3
"""Archive a Codex Desktop thread using the contest schema 1.0 format.

The official collector currently expects the Codex CLI hook payload format.
Codex Desktop stores paginated ``rollout-*.jsonl`` files instead, so this
adapter combines the pages belonging to one thread without changing them.
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


TEAM_ID = "contest2026_313_bianyuanxingzhe"
GITHUB_LOGIN = "zixuanzheng2007-stack"
SCHEMA_VERSION = "1.0"
REPO_ROOT = Path(__file__).resolve().parents[2]

REDACTIONS = (
    (re.compile(r"\bsk-[A-Za-z0-9_-]{12,}\b"), "[REDACTED_API_KEY]"),
    (re.compile(r"\bghp_[A-Za-z0-9]{20,}\b"), "[REDACTED_GITHUB_TOKEN]"),
    (re.compile(r"(?i)(Bearer\s+)[A-Za-z0-9._~+/=-]+"), r"\1[REDACTED]"),
    (re.compile(r"(?i)(@mimo-set\s+)\S+"), r"\1[REDACTED]"),
    (re.compile(r"(?i)(MIMO_API_KEY\s*[=:]\s*)\S+"), r"\1[REDACTED]"),
    (re.compile(r"(?i)((?:hotspotPass|wifiPass|password|passwd|pwd)\s*=\s*['\"]?)[^'\";\s]+"),
     r"\1[REDACTED]"),
    (re.compile(r"(?i)(@join\s+(?:\"[^\"]*\"|\S+)\s+)(?:\"[^\"]*\"|\S+)"),
     r"\1[REDACTED]"),
    (re.compile(r"((?:热点|WiFi|WIFI)?密码(?:已改为|与此前的|为|[:：=])?\s*[`'\"]*)[^\s`'\",;，。]+"),
     r"\1[REDACTED]"),
    (re.compile(r"(?i)(AT\+CWJAP=).*"), r"\1[REDACTED]"),
    (re.compile(r"\b\d{8}\b"), "[REDACTED_8_DIGIT]"),
)
UNICODE_LINE_BREAKS = re.compile(r"[\x0b\x0c\x1c-\x1e\x85\u2028\u2029]")


def redact(value: Any) -> Any:
    if isinstance(value, str):
        value = UNICODE_LINE_BREAKS.sub("\n", value)
        for pattern, replacement in REDACTIONS:
            value = pattern.sub(replacement, value)
        return value
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, dict):
        return {key: redact(item) for key, item in value.items()}
    return value


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    with path.open(encoding="utf-8", errors="replace") as stream:
        for line in stream:
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def matching_rollouts(source_root: Path, session_id: str) -> list[Path]:
    matches = []
    for path in source_root.rglob("rollout-*.jsonl"):
        try:
            first = next(iter(read_jsonl(path)), {})
        except OSError:
            continue
        if first.get("type") != "session_meta":
            continue
        if (first.get("payload") or {}).get("session_id") == session_id:
            matches.append(path)
    return sorted(matches)


def text_from_message(payload: dict[str, Any]) -> str:
    chunks = []
    for block in payload.get("content") or []:
        if not isinstance(block, dict):
            continue
        if block.get("type") in ("input_text", "output_text", "text"):
            text = block.get("text")
            if isinstance(text, str) and text:
                chunks.append(text)
    return "\n".join(chunks)


def decode_arguments(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def convert(rows: list[dict[str, Any]], session_id: str) -> tuple[list[dict], str | None]:
    events = []
    model = None
    seen = set()
    rows.sort(key=lambda row: (row.get("ordinal", -1), row.get("timestamp", "")))
    for row in rows:
        payload = row.get("payload") or {}
        if row.get("type") == "turn_context" and isinstance(payload.get("model"), str):
            model = payload["model"]
        if row.get("type") != "response_item":
            continue
        event_key = (row.get("ordinal"), payload.get("id"), payload.get("type"))
        if event_key in seen:
            continue
        seen.add(event_key)
        ts = row.get("timestamp") or datetime.now(timezone.utc).isoformat()
        kind = payload.get("type")
        if kind == "message" and payload.get("role") in ("user", "assistant"):
            text = text_from_message(payload)
            if text:
                event = {"ts": ts, "role": payload["role"], "text": text}
                if payload["role"] == "assistant" and model:
                    event["model"] = model
                events.append(event)
        elif kind in ("function_call", "custom_tool_call"):
            events.append({
                "ts": ts,
                "role": "tool",
                "tool_name": payload.get("name") or kind,
                "tool_call_id": payload.get("call_id") or payload.get("id") or "unknown",
                "input": decode_arguments(payload.get("arguments") or payload.get("input")),
                "output": None,
            })
        elif kind in ("function_call_output", "custom_tool_call_output"):
            events.append({
                "ts": ts,
                "role": "tool",
                "tool_name": "<result>",
                "tool_call_id": payload.get("call_id") or payload.get("id") or "unknown",
                "input": None,
                "output": payload.get("output"),
            })

    output = []
    for seq, event in enumerate(events):
        output.append(redact({
            "schema_version": SCHEMA_VERSION,
            "session_id": session_id,
            "team_id": TEAM_ID,
            "github_login": GITHUB_LOGIN,
            "tool": "codex",
            "seq": seq,
            **event,
        }))
    return output, model


def update_manifest(log_path: Path, session_id: str, title: str,
                    events: list[dict], model: str | None, raw_count: int) -> None:
    member_dir = REPO_ROOT / "logs" / GITHUB_LOGIN
    manifest_path = member_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    rel_path = log_path.relative_to(REPO_ROOT).as_posix()
    entry = {
        "session_id": session_id,
        "tool": "codex",
        "title": title,
        "started_at": events[0]["ts"],
        "last_event_at": events[-1]["ts"],
        "event_count": len(events),
        "raw_event_count": raw_count,
        "file_path": rel_path,
        "collection_mode": "vscode_extension",
        "health": "ok",
    }
    if model:
        entry["model"] = model
    sessions = manifest.setdefault("sessions", [])
    existing = next((item for item in sessions if item.get("session_id") == session_id), None)
    if existing:
        raise SystemExit(f"session already archived: {session_id}")
    sessions.append(entry)
    manifest["generator"] = "cursor-and-codex-archive"
    manifest["updated_at"] = datetime.now(timezone.utc).isoformat()
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("session_id")
    parser.add_argument("--title", required=True)
    parser.add_argument(
        "--source-root", type=Path,
        default=Path.home() / ".codex" / "sessions",
    )
    args = parser.parse_args()

    paths = matching_rollouts(args.source_root, args.session_id)
    if not paths:
        raise SystemExit(f"no Codex Desktop rollouts found for {args.session_id}")
    rows = []
    for path in paths:
        rows.extend(read_jsonl(path))
    events, model = convert(rows, args.session_id)
    if not events:
        raise SystemExit("no contest events found")

    date = events[0]["ts"][:10]
    log_path = REPO_ROOT / "logs" / GITHUB_LOGIN / date / f"codex__{args.session_id}.jsonl"
    if log_path.exists():
        raise SystemExit(f"refusing to overwrite existing log: {log_path}")
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("w", encoding="utf-8", newline="\n") as stream:
        for event in events:
            stream.write(json.dumps(event, ensure_ascii=False) + "\n")
    update_manifest(log_path, args.session_id, args.title, events, model, len(rows))
    print(f"rollouts={len(paths)} raw_events={len(rows)} contest_events={len(events)}")
    print(f"log={log_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
