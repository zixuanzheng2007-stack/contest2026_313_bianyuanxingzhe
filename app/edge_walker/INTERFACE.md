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

阶段 1：F 直接 `alert_output(level, reason)`。  
阶段 2：A 的 Tool `haptic_alert` 只执行已判决等级，不得改写判决。

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
