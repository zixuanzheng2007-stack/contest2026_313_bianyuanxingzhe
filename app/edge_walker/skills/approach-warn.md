# 接近提醒

毫米波雷达端侧判决后，由 ai_agent 主动调用 Tool `approach_alert` 执行蜂鸣与 LCD 变色。LLM 不参与测距与门限计算。

## When to use

当 LD2451 检测到侧后靠近目标且 ew_decide 输出 SOFT/STRONG/EMERGENCY 时；或用户询问「接近预警怎么工作」「告警档位」时说明流程。

## How to use

1. 判决已在 ew_ld2451 + ew_decide 完成，禁止用 LLM 估算距离或 TTC。
2. 主动执行 Tool `approach_alert`，参数示例：
   `{"level":"strong","reason":"R 12.3m approaching"}`
3. level 取值：none | soft | strong | emergency（或 0–3）。
4. Tool 内部只调用 alert_output(level, reason)，串口应出现 `[alert_output] level=...`。
5. 解除告警时 level=none。

## Example

雷达 latch STRONG @ 12m → 主动 approach_alert {"level":"strong","reason":"R 12.0m approaching"}
→ 屏橙 WARN + 蜂鸣 + 日志 `[alert_output] level=STRONG ...`
