# 边缘行者板上应用

映射到 openvela 后作为 NSH 命令 `ew`。板子上由 `rcS` 启动 `ew boot`，其余子命令只用于台架调试。

## 模块划分

| 文件 | 职责 | 负责人 |
|------|------|--------|
| `ew_main.c` | 命令行入口，只做参数分派 | 郑子轩 |
| `alert_output.*` | 提醒出口：日志 + 蜂鸣 + 屏色，一处调用三处生效 | 郑子轩 |
| `alert_buzzer.*` | PA28 无源蜂鸣，后台 worker 持续发波 | 郑子轩 |
| `alert_lcd.*` | 预警页与 LVGL 启动 | 郑子轩 |
| `ew_ld2451.*` | LD2451 帧解码 + `ew_decide` 门限 | 王筠昊 |
| `ew_chat.*` | UI 主循环 + 智能体对话页 | 韦政宇 |
| `ew_wifi_at.*` | ESP AT 猫：扫描 / 连接 / 凭证 / HTTPS | 郑子轩 |
| `ew_wifi_ui.*` | WiFi 配网页 | 郑子轩 |
| `ew_llm.*` | 走 AT HTTPS 问大模型 | 韦政宇 |
| `ew_agent.*` | Skill `approach-warn` + Tool `approach_alert` | 韦政宇 |
| `skills/` | Skill 文档模板 | 韦政宇 |
| `ai_agent_ext/` | ai_agent 进程侧 Tool 注入 | 韦政宇 |
| `host_smoke.c` | 主机侧解码与策略回归，不上板 | 王筠昊 |

## 三个页面

`ew_ui_loop()` 是唯一的 LVGL 主循环，页面靠 `ew_ui_goto()` 切换，各页只实现
`build / tick / teardown` 三个钩子：

| 页面 | 进入方式 | 钩子 |
|------|----------|------|
| 预警 `EW_PAGE_WARN` | 开机默认；其他页点「预警」；Esc 键 | `alert_lcd_attach_warn_ui` / `alert_lcd_warn_tick` / `alert_lcd_detach_warn_ui` |
| 对话 `EW_PAGE_CHAT` | 预警页点屏幕或「Agent」；回车键 | `build_ui` / `poll_reply` / `hide_kb` |
| 配网 `EW_PAGE_WIFI` | 预警页点「WiFi」或左上角网络状态；W 键 | `ew_wifi_ui_*` |

每帧最长睡 `EW_UI_FRAME_MS`（8 ms），保证雷达变色跟得上。新建页面后
`EW_UI_GATE_MS`（400 ms）内忽略切页请求，避开上一页松手时的触摸抖动。

## 联网

外挂 ESP AT 猫走 `/dev/ttyS2` @115200。凭证保存在板上 `/data/ew_wifi.conf`，
**不做编译期硬编码**，换网络不用重新编译。

屏上操作：预警页点「WiFi」→ 自动扫描 → 点一行 → 输密码 → connect。
开放网络直接连；连上后状态栏显示 `ONLINE <ip>`（公网可达）或 `LAN ONLY <ip>`
（连上了路由器但出不了公网）。已保存的那个网络在列表里带 `*`。

开机时 `ew_wifi_bringup()` 先问模组自己是不是已经连着（ESP 会记住上次的 AP），
没连再用 `/data/ew_wifi.conf` 里的凭证连一次；都没有就显示 `NO WIFI`，等人去配网页。

命令行等价操作：

```text
ew wifi                     链路状态 + 已保存的 SSID
ew wifi scan                列出周边网络
ew wifi join <ssid> [pass]  连接并记住
ew wifi forget              断开并清除凭证
ew wifi ping                AT 握手
ew at AT+CIFSR              原始 AT
```

## 其他命令

```text
ew                          读 /dev/ttyS1 雷达并走判断→提醒
ew boot                     LVGL UI 主循环（rcS 用）
ew chat                     直接进对话页
ew alert none|soft|strong|crit [reason]
ew fake [range_m] [speed]   假目标走完整条链
ew buzz [freq_hz] [ms]      PA28 蜂鸣点测
ew screen [info]            屏色自检 / 分辨率
ew ask <text>               不开 UI 问一次大模型
```

`ew alert` 在没有常驻 UI 的进程里跑时，会把请求写到 `/data/ew_alert.req`，
由 `ew boot` 那边的预警页下一拍取走。

## ai_agent Skill 演示

```text
ew boot                  # 安装 /data/ai_agent/skills/approach-warn.md
ew fake 10 20            # 应见 [ew_agent] proactive … [alert_output] …
ew alert strong test     # 手动 Tool 链
```

独立 ai_agent 固件：`sync_and_build.sh` → `artifacts/nuttx_ai_agent.bin`

## 开发辅助（非赛题必测）

| 模块 | 说明 |
|------|------|
| `ew_serial_ctl.c` | 串口 `@goto` / `@fake` / `@join` 等遥控（PC 调试） |
| `ew_mirror.c` | LVGL 快照经串口输出 RGB565 帧（PC `ew_panel.py` 可选） |

## 改完代码怎么验

```bash
# 主机侧回归，不需要板子
gcc -O2 -Wall -Wextra -o /tmp/host_smoke host_smoke.c ew_ld2451.c && /tmp/host_smoke

# 增量编译
ninja -C ~/openvela/cmake_out/sf32lb52_devkit_lcd
```

产物 `cmake_out/sf32lb52_devkit_lcd/nuttx.bin`，烧录地址 `0x12010000`。

屏接线说明见 `docs/DevKit-LCD_屏幕接线与自检.md`。
