# Stage1 历史设计归档

原分支 `feat/stage1-interface-freeze`，末提交 `ab9553f`，2026-10-26 由 fork PR #1 合入默认分支 `3d731ed`。

这里保留原始接口说明、10 事件验收模板、主机自测记录，以及旧 `ew_event.[ch]`、`event_chain_smoke.c`、Skill，供追溯设计和作者贡献。原来带空格的 `docs 复赛/`、`app edge_walker skills/` 路径不再用作活动入口。原提交历史完整保留。

**这些是历史资料，不是当前可编译模块或当前验收结论。** 原模板中的 PENDING 保持原样；旧 Skill 的字符串 ID/source JSON 与当前严格数字 ID/EWA1 协议不兼容，不能重新安装。

已采用的增量：统一接收 `ew_decision_t`、本地 source 追踪、人工/串口/fake 入口统一分发、10 事件链验证和 A/B 边界说明。当前实现位于 `app/edge_walker/ew_agent.[ch]`，回归位于 `scripts/host/test_agent_chain.py`。原独立 Tool 的明文单槽覆盖实现被严格 IPC/ACK 实现代替。

当前接口请阅读 [INTERFACE.md](../../../../app/edge_walker/INTERFACE.md) 和 [approach-warn.md](../../../../app/edge_walker/skills/approach-warn.md)。
