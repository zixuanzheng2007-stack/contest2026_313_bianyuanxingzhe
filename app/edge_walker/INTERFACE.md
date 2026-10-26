# 边缘行者 · F→A 告警接口（冻结）

> 改名须 H/F/A 三人同意。实现：`app/edge_walker/`

## 等级

```text
alert_level: NONE | SOFT | STRONG | EMERGENCY
```

C 枚举：`EW_ALERT_NONE / SOFT / STRONG / EMERGENCY`（`alert_output.h`）

## 事件

```text
event: approach_threshold_exceeded
payload:
  range_m      float
  speed_kmh    float
  azimuth_deg  float
  ttc_s        float   # <0 无效
  alert_level  enum
  reason       string  # 调试用
```

常驻 `ew_safety` 运行端侧雷达判决并维护蜂鸣安全下限。业务通知入口为
`ew_agent_emit_decision()` / `ew_agent_emit_decision_event()`，本地 Tool 为
`approach_alert`；人工和 Agent 告警不得降低当前雷达安全等级。

## 事件追踪（2026-10-26 开发契约）

- 接收完整 `ew_decision_t`，保留非空 `reason`，不由 LLM 重算距离、TTC 或告警等级。
- `event_id` 是本次运行中的非零数字；本地 `source` 为 `radar/fake/manual/serial/agent`。
- `source` 属于本地追踪信封；独立 Agent Tool JSON 仅接受 `level/reason/event_id`。
- 独立 Tool 使用 `EWA1 <numeric-id> <level> <hex-reason>` IPC；发布成功返回 `queued`，消费完成才产生带 ID 的 `applied/rejected` ACK。
- `queued`、软件 `applied`、实际声音/画面及道路验收分别留证；本地 C 调用不能证明独立 Agent registry 已被调用。
- fork 旧版字符串 `evt-*` ID、明文 source IPC 和旧函数签名已归档，不能与本协议混用。

当前完整说明见 [approach-warn](skills/approach-warn.md)；旧版设计与验收记录见
[历史归档](../../docs/复赛/archive/stage1-20261019/README.md)。

## 初值门限

| 等级 | 距离或 TTC |
|------|------------|
| SOFT | ≤25 m 或 TTC ≤5 s |
| STRONG | ≤15 m 或 TTC <3 s |
| EMERGENCY | ≤8 m 或 TTC <1.5 s |

过滤：只靠近；速度 ≥5 km/h。TTC = `range_m / (speed_kmh / 3.6)`。

## 无板自测

```bash
cd contest2026_313_bianyuanxingzhe/app/edge_walker
gcc -O2 -Wall -o host_smoke host_smoke.c ew_ld2451.c
./host_smoke
```

板上（启用 Kconfig 后）：

```text
ew parse
ew fixture soft|strong|emergency|away
ew fake 20 30
ew alert soft
```
