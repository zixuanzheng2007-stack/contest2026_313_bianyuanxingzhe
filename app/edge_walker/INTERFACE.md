# 边缘行者 · F→A 告警接口（冻结）

> 改名须 H/F/A 三人同意。实现：`app/edge_walker/`

## 等级

```text
alert_level: NONE | SOFT | STRONG | EMERGENCY
```

C 枚举：`EW_ALERT_NONE / SOFT / STRONG / EMERGENCY`（`alert_output.h`）

## A 侧安全判决（不扩字段）

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

阶段 1：F 直接 `alert_output(level, reason)`。  
阶段 2：A 的 Tool `haptic_alert` 只执行已判决等级，不得改写判决。

> 复赛阶段一后，业务入口统一调用 `ew_agent_emit_decision()`；
> `alert_output(level, reason)` 仍保留为最终出口兼容接口。

## B 侧事件信封（复赛冻结）

```text
event_id    string   evt-<source-tag>-<time>-<seq>
source      enum     radar | fake | manual | serial | agent
```

- `event_id/source` 由 B 生成，不允许 A 的安全判决重新计算这些内容。
- fake、真实雷达、手工和串口入口必须通过同一分发函数。
- Tool JSON 可携带 `event_id/source`；省略时回退为 `evt-agt-* / agent`。
- 跨进程请求文件格式：`<level> <event_id> <source> <reason>`。

完整验收规则见 `docs/复赛/阶段一_接口冻结与验收.md`。

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
