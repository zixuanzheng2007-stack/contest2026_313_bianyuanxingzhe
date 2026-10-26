# Git · push 前 rebase

## Fork 开发与竞赛提交

- `origin`：个人 fork；默认 `dev-ai-contest-2026` 用作待审核的 dev 集成分支，可以包含正在开发的代码。
- `upstream`：`open-vela/contest2026_313_bianyuanxingzhe`；只拉取竞赛基线，审核通过后通过 PR 提交。
- 同步时先保留工作区与分支历史，再吸收 upstream 的有效更新；有用的新开发必须按接口兼容性整合，不能使用 `reset --hard upstream/...` 覆盖 fork。
- `pre-push` 拒绝直接推送 upstream 或竞赛仓 URL；新克隆需先启用下方 hooks。该保护是本地约定，不能代替 GitHub 的仓库权限和审核。
- 提交竞赛前，从最新 upstream 建立独立候选分支，按功能选择已审核改动；不把整个 dev 分支无差别交付。运行主机回归、真实固件构建，并补齐对应板端验收证据后再由审核人确认。

本次整合见 [Fork 同步记录](../../docs/协作/Fork同步与开发仓约定_2026-10-26.md)。

## 启用（每人一次）

```powershell
powershell -ExecutionPolicy Bypass -File scripts/git/setup_hooks.ps1
```

## 手动 rebase

```bash
bash scripts/git/pre_push_rebase.sh
git push origin <branch>   # rebase 后可能需要 --force-with-lease
```

## 冲突惯例

- 保留 feature 的 `docs/` 子目录结构（`方案/` `硬件/` `烧录/`）
- 路径用 `scripts/submission/pack_submission.py`，不要根目录旧路径
- 不要恢复 `VMware_share/mailbox/`
- 提交清单：合并 upstream 的 PR/待办状态 + feature 的新路径

冲突后：`git add` → `git rebase --continue`
