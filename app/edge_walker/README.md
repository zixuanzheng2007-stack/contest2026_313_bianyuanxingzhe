# 边缘行者板上应用 `ew`

映射：`packages/demos/contest2026_313_edge_walker` → NSH 命令 `ew`。

## 分工

| 文件 | 负责人 |
|------|--------|
| `ew_ld2451.*`（解析 + policy） | **F 王筠昊** |
| `ew_main.c` `alert_output.*` `alert_lcd.*` `alert_buzzer.*` `ew_wifi_at.*` | **H 郑子轩**（主程序/出口/蜂鸣/AT；F 已对齐四级等级） |
| Tool 调 `alert_output` | **A 韦政宇** |

接口说明见 [INTERFACE.md](./INTERFACE.md)。

## 无板冒烟（主机）

```bash
cd contest2026_313_bianyuanxingzhe/app/edge_walker
gcc -O2 -Wall -o host_smoke host_smoke.c ew_ld2451.c
./host_smoke
```

期望输出末行：`ALL PASS`。

## NSH 用法

```text
ew help
ew parse                         # 官方协议示例帧
ew fixture soft|strong|emergency|away|empty
ew fake 20 30                    # 20m @ 30km/h → policy → alert
ew alert soft|strong|emergency|none
ew                               # 读 /dev/ttyS1（UART2 雷达）
ew lcd info|selftest|boot
ew boot                          # LVGL「EW READY」+ PA28 自检（rcS 调用）
ew buzz                          # 无源蜂鸣器自检
ew buzz 2500 800
ew wifi ping                     # ESP AT 模块 /dev/ttyS2
ew at AT
```

- `ew boot`：保持 CO5300 常亮（LVGL `/dev/lcd0`），并做 PA28 蜂鸣自检。  
- `ew buzz`：无源蜂鸣器（VCC=40P.2，GND=40P.14，IO=PA28/40P.23，2~5 kHz）。  
- `ew alert`：串口 + 四级屏色 + PA28 蜂鸣。  
- `ew wifi ping` / `ew at`：ESP AT（PA24/PA25 → `/dev/ttyS2` @115200）。SSID 不进仓，空 SSID 只测 AT / SmartConfig。

## 接入编译

1. 确认软链：`packages/demos/contest2026_313_edge_walker` → 本目录  
2. `menuconfig` 打开 `Contest 2026 team 313 edge_walker`  
3. 编 `sf32lb52_devkit_lcd`，烧录后跑上面命令  

雷达口：`/dev/ttyS1`（PA20 RX / PA27 TX），115200 8N1。控制台 UART1 禁止接雷达。  
开机：`board_overlay/sf32lb52_devkit_lcd/etc/init.d/rcS.user` 会执行 `ew boot`。
