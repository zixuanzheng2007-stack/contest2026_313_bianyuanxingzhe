# logs/ — AI Coding 日志目录

按[《AI Coding 日志归集与提交手册》](https://github.com/open-vela/docs/blob/dev-ai-contest-2026/zh-cn/contest_2026/ai_coding_log_guide.md)存放，与作品代码一并提交。

## 本队当前布局

```text
logs/
└── zixuanzheng2007-stack/          # GitHub: zixuanzheng2007-stack
    ├── manifest.json               # 会话清单
    ├── 2026-07-19/
    │   ├── cursor__6e5f1783-….jsonl   # 转换后的竞赛 schema
    │   └── raw/6e5f1783-….jsonl       # Cursor 原始 transcript
    └── 2026-08-06/
        ├── cursor__c06c0b41-….jsonl
        ├── cursor__df773b3a-….jsonl
        └── raw/…
```

| session_id | 内容 |
|------------|------|
| `6e5f1783-58c7-482e-8811-248998f1ee8c` | openvela 母目录：竞赛硬件资料与选型 |
| `c06c0b41-3b5e-4e46-a14d-1a09679677b2` | 专属仓 fork / 分支确认 |
| `df773b3a-7f00-4cb4-a0df-96892eb25e81` | 主开发：方案→雷达→板端→提交整理 |

## 字段说明

转换后的每行 JSON 遵循手册 `schema_version: 1.0`（`role` / `text` / `tool_name` / `seq` 等）。  
额外字段 `source: cursor-agent-transcript` 标明来源。  
`raw/` 为未改动的 Cursor Agent 原始 `.jsonl`，便于核对。

## 重要合规提示

官方自动采集支持：**Claude Code / OpenCode / Codex / AIoT-IDE**（见手册 Q9）。  
**Cursor 不在官方自动采集列表**。本批为开发全过程手工归档，供评委追溯；`repo sync` 后请安装 `contest-log-collector`，后续优先用官方工具开发。

## 后续自动入仓（Ubuntu / Git Bash）

```bash
cd contest2026_313_bianyuanxingzhe
bash ../.claude/skills/contest-log-collector/onboarding/install.sh \
  --team-id contest2026_313_bianyuanxingzhe \
  --github-login zixuanzheng2007-stack
```

队友各自改 `GITHUB_LOGIN` 为自己的用户名，日志按账号分目录。
