# -*- coding: utf-8 -*-
"""Convert Cursor agent transcripts to contest AI Coding log schema."""
import json
import re
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

login = "zixuanzheng2007-stack"
team = "contest2026_313_bianyuanxingzhe"
logs_root = Path(r"e:\openvela\contest2026_313_bianyuanxingzhe\logs") / login

sessions = [
    {
        "id": "6e5f1783-58c7-482e-8811-248998f1ee8c",
        "src": Path(
            r"C:\Users\15568\.cursor\projects\e-openvela\agent-transcripts"
            r"\6e5f1783-58c7-482e-8811-248998f1ee8c"
            r"\6e5f1783-58c7-482e-8811-248998f1ee8c.jsonl"
        ),
        "title": "openvela母目录-竞赛硬件资料与选型",
        "date": "2026-07-19",
    },
    {
        "id": "c06c0b41-3b5e-4e46-a14d-1a09679677b2",
        "src": Path(
            r"C:\Users\15568\.cursor\projects"
            r"\e-openvela-contest2026-313-bianyuanxingzhe\agent-transcripts"
            r"\c06c0b41-3b5e-4e46-a14d-1a09679677b2"
            r"\c06c0b41-3b5e-4e46-a14d-1a09679677b2.jsonl"
        ),
        "title": "专属仓fork与分支确认",
        "date": "2026-08-06",
    },
    {
        "id": "df773b3a-7f00-4cb4-a0df-96892eb25e81",
        "src": Path(
            r"C:\Users\15568\.cursor\projects"
            r"\e-openvela-contest2026-313-bianyuanxingzhe\agent-transcripts"
            r"\df773b3a-7f00-4cb4-a0df-96892eb25e81"
            r"\df773b3a-7f00-4cb4-a0df-96892eb25e81.jsonl"
        ),
        "title": "边缘行者主开发会话-方案到板端联调",
        "date": "2026-08-06",
    },
]

TS_RE = re.compile(r"<timestamp>([^<]+)</timestamp>")
TZ8 = timezone(timedelta(hours=8))


def content_text(content):
    if not content:
        return ""
    if isinstance(content, str):
        return content
    parts = []
    for c in content:
        if isinstance(c, dict) and c.get("type") == "text" and c.get("text"):
            parts.append(c["text"])
        elif isinstance(c, str):
            parts.append(c)
    return "\n".join(parts)


def extract_ts(text, fallback_iso):
    m = TS_RE.search(text or "")
    if not m:
        return fallback_iso
    raw = m.group(1).strip().replace("  ", " ")
    core = raw.replace("(UTC+8)", "").strip()
    for fmt in ("%A, %b %d, %Y, %I:%M %p", "%A, %B %d, %Y, %I:%M %p"):
        try:
            dt = datetime.strptime(core, fmt).replace(tzinfo=TZ8).astimezone(timezone.utc)
            return dt.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
        except ValueError:
            continue
    return fallback_iso


def clean_text(text):
    if not text:
        return ""
    text = TS_RE.sub("", text)
    text = re.sub(r"</?user_query>", "", text).strip()
    if len(text) > 200000:
        text = text[:200000] + "\n...[truncated]"
    return text


def convert(src: Path, session_id: str, out: Path):
    seq = 0
    started = None
    last = None
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
    out.parent.mkdir(parents=True, exist_ok=True)
    with src.open("r", encoding="utf-8", errors="replace") as fin, out.open(
        "w", encoding="utf-8", newline="\n"
    ) as fout:
        for line in fin:
            line = line.strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            role = ev.get("role")
            if role not in ("user", "assistant"):
                continue
            msg = ev.get("message") or {}
            content = msg.get("content")
            text = content_text(content)
            ts = extract_ts(text, now)
            if started is None:
                started = ts
            last = ts
            obj = {
                "schema_version": "1.0",
                "session_id": session_id,
                "team_id": team,
                "github_login": login,
                "tool": "cursor",
                "seq": seq,
                "ts": ts,
                "role": role,
                "text": clean_text(text),
                "source": "cursor-agent-transcript",
            }
            if role == "assistant":
                obj["model"] = "cursor-grok-4.5"
            fout.write(json.dumps(obj, ensure_ascii=False) + "\n")
            seq += 1

            if isinstance(content, list):
                for c in content:
                    if not isinstance(c, dict) or c.get("type") != "tool_use":
                        continue
                    tin = c.get("input")
                    try:
                        s = json.dumps(tin, ensure_ascii=False)
                        if len(s) > 50000:
                            tin = {"truncated": True, "preview": s[:50000]}
                    except TypeError:
                        tin = {"note": "input_serialize_failed"}
                    tobj = {
                        "schema_version": "1.0",
                        "session_id": session_id,
                        "team_id": team,
                        "github_login": login,
                        "tool": "cursor",
                        "seq": seq,
                        "ts": ts,
                        "role": "tool",
                        "tool_name": str(c.get("name") or ""),
                        "tool_call_id": str(c.get("id") or ""),
                        "input": tin,
                        "output": {"status": "recorded_in_cursor_transcript"},
                        "source": "cursor-agent-transcript",
                    }
                    fout.write(json.dumps(tobj, ensure_ascii=False) + "\n")
                    seq += 1
    return {"event_count": seq, "started_at": started, "last_event_at": last}


def main():
    manifest_sessions = []
    for s in sessions:
        if not s["src"].exists():
            raise SystemExit(f"missing {s['src']}")
        day = logs_root / s["date"]
        raw_dir = day / "raw"
        raw_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(s["src"], raw_dir / f"{s['id']}.jsonl")
        out = day / f"cursor__{s['id']}.jsonl"
        meta = convert(s["src"], s["id"], out)
        with out.open(encoding="utf-8") as f:
            json.loads(f.readline())
        print(f"OK {s['id']} events={meta['event_count']}")
        manifest_sessions.append(
            {
                "session_id": s["id"],
                "tool": "cursor",
                "title": s["title"],
                "started_at": meta["started_at"],
                "last_event_at": meta["last_event_at"],
                "event_count": meta["event_count"],
                "file_path": f"logs/{login}/{s['date']}/cursor__{s['id']}.jsonl",
                "raw_file_path": f"logs/{login}/{s['date']}/raw/{s['id']}.jsonl",
                "collection_mode": "manual-cursor-archive",
                "health": "ok",
                "note": "Cursor 非官方自动采集；已转竞赛 schema 并保留 raw",
            }
        )

    manifest = {
        "schema_version": "1.0",
        "team_id": team,
        "github_login": login,
        "generator": "manual-cursor-archive",
        "source_note": (
            "官方采集器支持 Claude Code / OpenCode / Codex / AIoT-IDE。"
            "本批为 Cursor Agent 开发全过程原始日志归档（含 openvela 母目录会话）。"
        ),
        "sessions": manifest_sessions,
        "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f") + "+00:00",
    }
    (logs_root / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print("manifest written")


if __name__ == "__main__":
    main()
