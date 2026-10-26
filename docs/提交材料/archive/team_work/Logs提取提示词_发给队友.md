# AI Coding 日志提取 · 发给队友（整段复制）

> **截止 2026-09-20** · 与源码同仓提交 `logs/<你的GitHub用户名>/`  
> 官方手册：[AI Coding 日志归集与提交手册](https://github.com/open-vela/docs/blob/dev-ai-contest-2026/zh-cn/contest_2026/ai_coding_log_guide.md)  
> 本队样例：`logs/zixuanzheng2007-stack/`（郑子轩已归档 6 会话）

**禁止：** 删 Cursor 对话后再开发；改已 push 的 `logs/*.jsonl` 内容；用他人 GitHub 账号冒充。

---

## 一、发给王筠昊（GitHub: `wjh669939-cmd`）

### A. 粘贴给 Ubuntu VM 里的 Cursor（开聊第一句）

```
你是边缘行者竞赛的 AI 日志归档助手。仓库：~/openvela/contest2026_313_bianyuanxingzhe。

我的 GitHub：wjh669939-cmd。我负责 ew_ld2451.c、host_smoke、LD2451 数据策略文档。

请按官方 contest-log-collector 流程，帮我把本机 Cursor 历史对话导出到 logs/wjh669939-cmd/ 并准备 git commit：

1. 读 VMware_share/mailbox/host_to_guest/TASK_029_CURSOR_LOGS_BACKFILL.md 和 TASK_028_LOGS_RECORDING.md
2. 在 ~/openvela/.claude 执行 install.sh（GITHUB_LOGIN 必须是 wjh669939-cmd，不能写 zixuanzheng2007-stack）
3. 运行 contest-snapshot --backfill --source cursor（先 preview，再 --confirm）
4. 若 backfill 找不到 transcript：把 ~/.cursor/projects/*/agent-transcripts/*/*.jsonl 原样复制到
   logs/wjh669939-cmd/<日期>/raw/<session-uuid>.jsonl，并参照 logs/zixuanzheng2007-stack/manifest.json 写 manifest.json
5. git add logs/wjh669939-cmd/ && git commit -s -m "logs: backfill cursor (wjh669939-cmd)" && git push
6. 写回执 VMware_share/mailbox/guest_to_host/REPLY_028_LOGS.md 和 REPLY_029_CURSOR_BACKFILL.md

不要删 Cursor 原对话。不要改已 push 的 jsonl 内容。代码任务仍以 CURRENT.json 为准。
```

### B. 终端一键（不用 AI 时，Guest SSH 整段 bash）

```bash
cd ~/openvela/.claude && git checkout dev-ai-contest-2026 && git pull
cd ~/openvela/contest2026_313_bianyuanxingzhe && git pull

bash ~/openvela/.claude/skills/contest-log-collector/onboarding/install.sh \
  --team-id contest2026_313_bianyuanxingzhe \
  --github-login wjh669939-cmd

export PATH="$HOME/.local/bin:$PATH"
contest-snapshot --backfill --source cursor
contest-snapshot --backfill --source cursor --confirm

git add logs/
git commit -s -m "logs: backfill cursor history (wjh669939-cmd)"
git push
```

### C. 回执模板（填完贴到 mailbox）

```markdown
# REPLY_028 / REPLY_029 · 王筠昊 logs

- GitHub：wjh669939-cmd
- logs 目录：logs/wjh669939-cmd/ （是/否）
- backfill preview 行数：
- 导出 session 数：
- commit hash：
- 覆盖模块：ew_ld2451、host_smoke、LD2451数据与策略复现.md
```

---

## 二、发给韦政宇（GitHub: `<填你的账号>`）

### A. 粘贴给 Cursor（开聊第一句）

```
你是边缘行者竞赛的 AI 日志归档助手。仓库：~/openvela/contest2026_313_bianyuanxingzhe。

我的 GitHub：<填你的GitHub用户名>。我负责 ew_chat.c、ew_llm.c、ew_agent*.c、Skill approach-warn、ai_agent_ext/。

请帮我把 Cursor AI 对话归档到 logs/<填你的GitHub用户名>/ 并 push：

1. 读 TASK_028_LOGS_RECORDING.md、TASK_029_CURSOR_LOGS_BACKFILL.md
2. install.sh 的 --github-login 必须是我的账号，不能写 zixuanzheng2007-stack 或 wjh669939-cmd
3. contest-snapshot --backfill --source cursor（preview → --confirm）
4. 若官方 backfill 失败：原样保存 raw jsonl 到 logs/<login>/<日期>/raw/，并写 manifest.json（字段参考 logs/zixuanzheng2007-stack/manifest.json）
5. git add logs/ && commit && push
6. 写 REPLY_028_LOGS.md

今后每次用 AI 改 Agent/Skill 代码，阶段完工都要更新 logs/，不删 Cursor 对话。
```

### B. 终端一键（把 `<GITHUB_LOGIN>` 换成你的）

```bash
cd ~/openvela/.claude && git checkout dev-ai-contest-2026 && git pull
cd ~/openvela/contest2026_313_bianyuanxingzhe && git pull

bash ~/openvela/.claude/skills/contest-log-collector/onboarding/install.sh \
  --team-id contest2026_313_bianyuanxingzhe \
  --github-login <GITHUB_LOGIN>

export PATH="$HOME/.local/bin:$PATH"
contest-snapshot --backfill --source cursor
contest-snapshot --backfill --source cursor --confirm

git add logs/
git commit -s -m "logs: backfill cursor history (<GITHUB_LOGIN>)"
git push
```

---

## 三、发给郑子轩（Windows Host · 已有 logs，补增量）

### A. 粘贴给 Cursor

```
仓库 e:\openvela\contest2026_313_bianyuanxingzhe。请更新 AI Coding 日志：

1. 扫描 C:\Users\15568\.cursor\projects\ 下 agent-transcripts，找出尚未进入 logs/zixuanzheng2007-stack/manifest.json 的新 session
2. 运行 python scripts/archive_cursor_logs.py（或按脚本内 sessions 列表增补新 UUID、title、date 后重跑）
3. 确认 logs/zixuanzheng2007-stack/ 含 schema 1.0 的 cursor__*.jsonl 与 raw/*.jsonl
4. git add logs/ && commit -s -m "logs: archive cursor sessions" && push

不要修改已 push 的 jsonl 正文。参考 logs/README.md。
```

### B. 本机命令

```powershell
cd e:\openvela\contest2026_313_bianyuanxingzhe
python scripts\archive_cursor_logs.py
git add logs/
git status
git commit -s -m "logs: archive cursor sessions"
git push
```

---

## 四、日常：每次 AI 改完代码后（三人通用 · 贴 Cursor）

```
本次开发结束前，请把当前 Cursor 对话归档进 logs/<我的GitHub>/：

- 若已装 contest-log-collector：contest-snapshot（按官方手册）
- 若用 Cursor：至少把 agent-transcripts 下本 session 的 .jsonl 复制到 logs/<login>/<YYYY-MM-DD>/raw/<uuid>.jsonl
- 更新 manifest.json 一条 session 记录（tool=cursor, title=本次任务简述）
- git add logs/ && commit -s -m "logs: <模块名> session" && push

禁止删除 Cursor 原 transcript；禁止篡改已提交 jsonl 序号或内容。
```

---

## 五、验收对照

| 成员 | logs 目录 | 应覆盖的开发内容 |
|------|-----------|------------------|
| 郑子轩 | `logs/zixuanzheng2007-stack/` | 集成、UI、WiFi、烧录、提交材料 |
| 王筠昊 | `logs/wjh669939-cmd/` | ew_ld2451、host_smoke、数据文档 |
| 韦政宇 | `logs/<韦的GitHub>/` | ew_agent、Skill、ew_chat/llm |

评委 clone 后应能在三人目录各自看到 AI 辅助开发过程。

---

## 六、微信/群消息（可直接转发）

**王筠昊：**
> 竞赛 P0：请把 Cursor 日志导出到 `logs/wjh669939-cmd/` 并 push。VM 里 Cursor 开聊粘贴 `docs/提交材料/Logs提取提示词_发给队友.md` 第一节 A 段；或 SSH 跑第一节 B 段 bash。回执 REPLY_028/029。

**韦政宇：**
> 竞赛 P0：请把 Agent/Skill 相关 Cursor 日志导出到 `logs/<你的GitHub>/` 并 push。粘贴同文档第二节 A 段（先改 GitHub 名）。回执 REPLY_028。

**郑子轩：**
> 本机跑 `python scripts/archive_cursor_logs.py` 补 9 月新会话，push logs/，PR 已含则只补 commit。
