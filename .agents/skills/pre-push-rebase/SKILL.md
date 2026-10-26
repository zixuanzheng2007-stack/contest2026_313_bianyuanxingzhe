---
name: pre-push-rebase
description: >-
  Rebase feature branch onto upstream before git push and resolve merge conflicts
  using project conventions. Use when the user asks to push, before git push, when
  PR shows conflicts, or when pre-push rebase hook fails.
---

# Push 前 Rebase 与冲突处理

> **本 Skill 仅本地**（`.cursor/` 不入仓）。仓内脚本： `scripts/git/` + `.githooks/`。

## 自动触发

| 机制 | 行为 |
|------|------|
| **Git pre-push** | `.githooks/pre-push` → `scripts/git/pre_push_rebase.sh` |
| **Codex hook（本地）** | `.cursor/hooks.json` 匹配 `git push` 时先跑同一脚本 |

首次克隆后执行一次：

```bash
bash scripts/git/setup_hooks.sh
```

## 脚本流程

1. `git fetch upstream dev-ai-contest-2026`
2. 若已基于最新 upstream → 直接通过
3. 否则 `git rebase upstream/dev-ai-contest-2026`
4. 冲突 → 退出 1，列出 `git diff --name-only --diff-filter=U`

日志：Codex 拦截时见 `.cursor/hooks/pre-push-last.log`

## Agent 执行 push 的固定顺序

```
1. bash scripts/git/pre_push_rebase.sh
2. 若 exit 1 → 按下方规则解冲突 → git add → git rebase --continue → 重复 1
3. git push origin <branch>   # 若 rebase 改写历史，用 --force-with-lease
4. gh pr view <n> --json mergeable   # 确认 PR 无 CONFLICTING
```

**禁止**：冲突未清时 `git push`；未请求时 `push --force`（rebase 后用 `--force-with-lease`）。

## 冲突裁决（本仓）

优先 **保留 feature 分支的目录整理**，吸收 upstream 的**内容更新**：

| 区域 | 保留 | 说明 |
|------|------|------|
| `docs/` 子目录 | **HEAD（feature）** | `方案/` `硬件/` `烧录/` 结构 |
| `scripts/submission/pack_submission.py` | **HEAD** | 非根目录 `scripts/pack_submission.py` |
| `scripts/guest/` `scripts/host/` | **HEAD** | 脚本分层 |
| `VMware_share/mailbox/` | **删除** | 已归档，`.gitignore` 忽略 |
| 提交索引 / 清单 | **合并** | 更新 PR 号、勾选状态，路径用新结构 |
| `app/edge_walker/` 源码 | **合并** | 以功能完整为准 |
| `logs/` | **合并** | 保留双方日志目录 |

### 常见文件

- `docs/00_提交材料索引.md`：保留精简结构 + upstream 的 PR/待办状态
- `docs/提交材料/photos/README.md`：路径用 `scripts/submission/pack_submission.py`
- `docs/提交材料/上交材料清单.md`：同上
- 重复文件：upstream 根目录旧路径 vs feature 新路径 → **只留新路径**

## 冲突解决命令模板

```bash
git status
git diff --name-only --diff-filter=U

# 编辑后
git add <files>
git rebase --continue

# 搞砸了
git rebase --abort
```

## 配置

- 仓内：`scripts/git/rebase.config.env`
- 本地覆盖：`.cursor/skills/pre-push-rebase/config.env`（可选，不 push）
