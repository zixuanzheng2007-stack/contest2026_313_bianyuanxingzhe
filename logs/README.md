# logs/ — AI Coding 日志目录

按[《AI Coding 日志归集与提交手册》](https://github.com/open-vela/docs/blob/dev-ai-contest-2026/zh-cn/contest_2026/ai_coding_log_guide.md)存放，与作品代码一并提交。

## 本队当前布局

官方 `logs/` 仅保留通过 schema 校验的 Codex 会话：

```text
logs/
└── zixuanzheng2007-stack/
    ├── manifest.json
    └── 2026-09-18/codex__01a0b20d-669b-7502-9e56-9fc0dc3502d7.jsonl
```

当前 manifest 只有 1 条 Codex Desktop 会话（2484 个事件）。历史 Cursor Agent transcript 已原样放在 `docs/提交材料/archive/supplemental_cursor_logs/`，不属于官方 `logs/` 校验范围，也不标记为 `backfill-cursor`。

Codex Desktop 增量归档脚本：`python scripts/submission/archive_codex_logs.py <session-id> --title <title>`。

## 字段说明

每行 JSON 遵循手册 `schema_version: 1.0`（`role` / `text` / `tool_name` / `seq` 等）。  
`raw/` 为 Cursor Agent 原始 `.jsonl`。
